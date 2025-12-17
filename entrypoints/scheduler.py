#!/usr/bin/env python3
"""
Scheduler service that runs the data pipeline every N minutes.
This runs in a separate container to keep the pipeline independent from the web server.
"""
import os
import time
import signal
import sys
from datetime import datetime
from loguru import logger
from app import create_app
from app.extensions import db

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    colorize=True,
)
logger.add(
    'logs/scheduler.log',
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    rotation="10 MB",
    retention=30,
    compression="zip",
)

# Global flag for graceful shutdown
shutdown = False

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global shutdown
    logger.info("Received shutdown signal, finishing current task...")
    shutdown = True

def run_pipeline():
    """Run the full data pipeline."""
    app = create_app()
    with app.app_context():
        # Ensure database is initialized
        try:
            db.engine.connect()
            logger.info("Database connection verified")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
        
        # Run the full pipeline
        try:
            logger.info("=" * 70)
            logger.info("STARTING SCHEDULED PIPELINE RUN")
            logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 70)
            
            # Import the pipeline functions
            from app.services.ingestion import run_ingestion
            from app.services.extraction import run_extraction
            from app.services.enrichment import run_enrichment
            
            # Get number of workers from environment (default 10)
            workers = int(os.environ.get('PIPELINE_WORKERS', '10'))
            
            # STAGE 1: FETCH
            logger.info("\n=== STAGE 1: FETCH ===")
            run_ingestion(max_workers=workers)
            
            # STAGE 2: EXTRACT
            logger.info("\n=== STAGE 2: EXTRACT ===")
            run_extraction(max_workers=workers)
            
            # STAGE 3: ENRICH
            logger.info("\n=== STAGE 3: ENRICH ===")
            run_enrichment(max_workers=workers)
            
            logger.info("=" * 70)
            logger.info("PIPELINE RUN COMPLETE")
            logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 70)
            
            return True
        except Exception as e:
            logger.exception(f"Pipeline execution failed: {e}")
            return False

def main():
    """Main scheduler loop."""
    global shutdown
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Get interval from environment (default 30 minutes)
    interval_minutes = int(os.environ.get('PIPELINE_INTERVAL_MINUTES', '30'))
    interval_seconds = interval_minutes * 60
    
    logger.info("=" * 70)
    logger.info("SCHEDULER STARTING")
    logger.info(f"Pipeline interval: {interval_minutes} minutes ({interval_seconds} seconds)")
    logger.info("=" * 70)
    
    # Initial run
    logger.info("Running initial pipeline...")
    run_pipeline()
    
    # Main loop
    while not shutdown:
        try:
            # Wait for the interval
            logger.info(f"Waiting {interval_minutes} minutes until next run...")
            time.sleep(interval_seconds)
            
            if shutdown:
                break
            
            # Run pipeline
            run_pipeline()
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            shutdown = True
        except Exception as e:
            logger.exception(f"Unexpected error in scheduler loop: {e}")
            # Continue running even if one iteration fails
            logger.info("Continuing scheduler loop...")
    
    logger.info("Scheduler shutting down gracefully")

if __name__ == '__main__':
    main()

