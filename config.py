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