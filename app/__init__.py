from flask import Flask
from config import Config
from app.extensions import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    with app.app_context():
        # Import models to ensure they are registered with SQLAlchemy
        from app import models
        # Note: Database tables are now managed by Alembic migrations
        # Run 'alembic upgrade head' to apply migrations

    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app
