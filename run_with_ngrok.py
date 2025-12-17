#!/usr/bin/env python3
"""
Run the Flask app with ngrok tunnel.
This script starts the Flask app and automatically creates an ngrok tunnel.
"""

import os
import sys
import socket
import threading
import time
import requests
from pyngrok import ngrok, conf
from app import create_app

def find_free_port(start_port=5000, max_attempts=10):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find an available port starting from {start_port}")

def start_ngrok(port=5000):
    """Start ngrok tunnel for the Flask app."""
    # Get ngrok auth token from environment variable if set
    ngrok_token = os.environ.get('NGROK_AUTH_TOKEN')
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)
    else:
        print("Warning: NGROK_AUTH_TOKEN not set. Using free tier (may have limitations).")
        print("Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken\n")
    
    # Configure ngrok - disable web interface to avoid forbidden errors
    # The web interface requires authentication and can cause issues
    try:
        # Kill any existing ngrok tunnels
        ngrok.kill()
        
        # Create tunnel - use bind_tls=False for HTTP, or True for HTTPS
        # For development, HTTP is fine and avoids some auth issues
        tunnel = ngrok.connect(port, bind_tls=False)
        public_url = tunnel.public_url
        
        print(f"\n{'='*60}")
        print(f"ngrok tunnel created!")
        print(f"Public URL: {public_url}")
        print(f"Local URL: http://localhost:{port}")
        print(f"{'='*60}\n")
        return public_url
    except Exception as e:
        print(f"Error creating ngrok tunnel: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you have an ngrok account and set NGROK_AUTH_TOKEN")
        print("   Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken")
        print("   Then run: export NGROK_AUTH_TOKEN=your_token_here")
        print("2. Check if the port is already in use")
        print("3. Make sure pyngrok is installed: uv sync")
        raise

def wait_for_server(port, timeout=15):
    """Wait for the Flask server to be ready and responding."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # First check if port is open
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                if result == 0:
                    # Port is open, now verify Flask is actually responding
                    try:
                        response = requests.get(f'http://localhost:{port}/', timeout=2)
                        if response.status_code in [200, 404, 500]:  # Any HTTP response means Flask is running
                            return True
                    except requests.exceptions.RequestException:
                        # Flask might still be starting, wait a bit more
                        time.sleep(0.5)
                        continue
        except Exception:
            pass
        time.sleep(0.5)
    return False

def run_app(port=5000):
    """Run the Flask app in a thread."""
    app = create_app()
    # Bind to 0.0.0.0 to allow ngrok to connect properly
    # Use threaded=True to handle multiple requests
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False, threaded=True)

if __name__ == '__main__':
    # Get port from environment variable or use 5001 (5000 is often used by AirPlay on macOS)
    default_port = int(os.environ.get('FLASK_PORT', 5001))
    try:
        port = find_free_port(default_port)
        if port != default_port:
            print(f"Port {default_port} is in use. Using port {port} instead.")
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Get ngrok auth token from environment variable if set
    ngrok_token = os.environ.get('NGROK_AUTH_TOKEN')
    if ngrok_token:
        ngrok.set_auth_token(ngrok_token)
    else:
        print("Warning: NGROK_AUTH_TOKEN not set. Using free tier (may have limitations).")
        print("Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken\n")
    
    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=run_app, args=(port,), daemon=True)
    flask_thread.start()
    
    # Wait for Flask to be ready
    print(f"Starting Flask app on port {port}...")
    if not wait_for_server(port):
        print(f"Error: Flask server did not start on port {port}")
        sys.exit(1)
    
    print(f"Flask app is ready on http://localhost:{port}")
    
    # Now start ngrok after Flask is ready
    try:
        # Kill any existing ngrok tunnels
        ngrok.kill()
        
        # Create tunnel
        tunnel = ngrok.connect(port, bind_tls=False)
        public_url = tunnel.public_url
        
        print(f"\n{'='*60}")
        print(f"ngrok tunnel created!")
        print(f"Public URL: {public_url}")
        print(f"Local URL: http://localhost:{port}")
        print(f"{'='*60}\n")
    except Exception as e:
        print(f"Error creating ngrok tunnel: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you have an ngrok account and set NGROK_AUTH_TOKEN")
        print("   Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken")
        print("   Then run: export NGROK_AUTH_TOKEN=your_token_here")
        print("2. Check if the port is already in use")
        print("3. Make sure pyngrok is installed: uv sync")
        sys.exit(1)
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        ngrok.kill()
        sys.exit(0)

