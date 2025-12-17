from flask import Flask
from config import Config
from app.extensions import db
from loguru import logger
import sys
import os

def setup_logging(app):
    """Configure loguru logging for the application."""
    # Remove default handler
    logger.remove()
    
    # Get log level from config
    log_level = app.config.get('LOG_LEVEL', 'INFO')
    
    # Ensure logs directory exists
    log_file = app.config.get('LOG_FILE', 'logs/app.log')
    log_error_file = app.config.get('LOG_ERROR_FILE', 'logs/errors.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Console handler with colorization
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_level,
        colorize=True,
    )
    
    # File handler with rotation
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        level=log_level,
        rotation=app.config.get('LOG_ROTATION_SIZE', '10 MB'),
        retention=app.config.get('LOG_RETENTION_DAYS', 30),
        compression="zip",
    )
    
    # Separate error log file (ERROR and above)
    logger.add(
        log_error_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        level="ERROR",
        rotation=app.config.get('LOG_ROTATION_SIZE', '10 MB'),
        retention=app.config.get('LOG_RETENTION_DAYS', 30),
        compression="zip",
    )
    
    logger.info(f"Logging configured: level={log_level}, log_file={log_file}")

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Setup logging
    setup_logging(app)

    db.init_app(app)

    with app.app_context():
        # Import models to ensure they are registered with SQLAlchemy
        from app import models
        # Note: Database tables are now managed by Alembic migrations
        # Run 'alembic upgrade head' to apply migrations

    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    # Make config available to templates
    @app.context_processor
    def inject_config():
        return dict(config=app.config)

    return app
