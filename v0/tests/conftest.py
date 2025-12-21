import pytest
import tempfile
import os
from datetime import datetime
from flask import Flask
from app import create_app
from app.extensions import db
from app.models import Source
from config import Config


class TestConfig(Config):
    """Test configuration with in-memory SQLite database."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


@pytest.fixture
def app():
    """Create and configure a test Flask app."""
    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Provide a database session."""
    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture
def sample_feed_entry():
    """Create a sample RSS feed entry."""
    class MockEntry:
        def __init__(self):
            self.link = "https://news.google.com/articles/test123"
            self.title = "Test Article Title"
            self.published_parsed = (2024, 1, 15, 10, 30, 0, 0, 15, 0)
    
    return MockEntry()


@pytest.fixture
def sample_source_data():
    """Sample source data for testing."""
    return {
        'url': 'https://example.com/article',
        'title': 'Test Article',
        'source_type': 'news_article',
        'status': 'pending'
    }

