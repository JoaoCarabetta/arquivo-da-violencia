import os

class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'violence.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Public mode: hide sources and extractions pages
    # Set PUBLIC_MODE=true to enable public mode (only incidents visible)
    # Set PUBLIC_MODE=false or leave unset for development mode (all pages visible)
    PUBLIC_MODE = os.environ.get('PUBLIC_MODE', 'false').lower() in ('true', '1', 'yes')
    
    # Google Maps API configuration
    GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.environ.get('LOG_FILE', os.path.join(BASE_DIR, 'logs', 'app.log'))
    LOG_ERROR_FILE = os.environ.get('LOG_ERROR_FILE', os.path.join(BASE_DIR, 'logs', 'errors.log'))
    LOG_ROTATION_SIZE = os.environ.get('LOG_ROTATION_SIZE', '10 MB')
    LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', '30'))