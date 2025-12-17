#!/bin/bash

# Run Flask app with ngrok tunnel
# Usage: ./run_with_ngrok.sh

set -e

PORT=${FLASK_PORT:-5001}
NGROK_TOKEN=${NGROK_AUTH_TOKEN:-}

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    if [ ! -z "$FLASK_PID" ]; then
        kill $FLASK_PID 2>/dev/null || true
    fi
    if [ ! -z "$NGROK_PID" ]; then
        kill $NGROK_PID 2>/dev/null || true
        pkill -f ngrok 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check if port is available
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}Port $PORT is in use. Trying to find another port...${NC}"
    for p in $(seq $PORT $((PORT + 10))); do
        if ! lsof -Pi :$p -sTCP:LISTEN -t >/dev/null 2>&1 ; then
            PORT=$p
            echo -e "${GREEN}Using port $PORT instead${NC}"
            break
        fi
    done
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${RED}Error: Could not find an available port${NC}"
        exit 1
    fi
fi

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}Error: ngrok is not installed${NC}"
    echo "Install it from: https://ngrok.com/download"
    exit 1
fi

# Set ngrok auth token if provided
if [ ! -z "$NGROK_TOKEN" ]; then
    ngrok config add-authtoken "$NGROK_TOKEN" >/dev/null 2>&1 || true
else
    echo -e "${YELLOW}Warning: NGROK_AUTH_TOKEN not set. Using free tier (may have limitations).${NC}"
    echo "Get your token from: https://dashboard.ngrok.com/get-started/your-authtoken"
    echo ""
fi

# Kill any existing ngrok processes
pkill -f ngrok 2>/dev/null || true
sleep 1

# Start Flask app in background
echo -e "${GREEN}Starting Flask app on port $PORT...${NC}"
export FLASK_APP=run.py
export FLASK_ENV=development

# Start Flask using uv run
uv run python -c "
from app import create_app
app = create_app()
app.run(host='0.0.0.0', port=$PORT, debug=True, use_reloader=False)
" &
FLASK_PID=$!

# Wait for Flask to be ready
echo "Waiting for Flask to start..."
for i in {1..30}; do
    if curl -s http://localhost:$PORT/ >/dev/null 2>&1; then
        echo -e "${GREEN}Flask app is ready on http://localhost:$PORT${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}Error: Flask server did not start on port $PORT${NC}"
        kill $FLASK_PID 2>/dev/null || true
        exit 1
    fi
    sleep 0.5
done

# Start ngrok
echo -e "${GREEN}Starting ngrok tunnel...${NC}"
ngrok http $PORT >/dev/null 2>&1 &
NGROK_PID=$!

# Wait a moment for ngrok to start
sleep 2

# Get ngrok public URL from ngrok API
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"[^"]*' | head -1 | cut -d'"' -f4)

if [ -z "$NGROK_URL" ]; then
    echo -e "${YELLOW}Could not automatically get ngrok URL. Check ngrok web interface at http://localhost:4040${NC}"
else
    echo ""
    echo "============================================================"
    echo -e "${GREEN}ngrok tunnel created!${NC}"
    echo -e "Public URL: ${GREEN}$NGROK_URL${NC}"
    echo -e "Local URL: http://localhost:$PORT"
    echo "============================================================"
    echo ""
fi

# Wait for user interrupt
echo "Press Ctrl+C to stop..."
wait

