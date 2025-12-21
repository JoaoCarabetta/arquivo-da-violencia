from flask_sqlalchemy import SQLAlchemy

# Configure SQLAlchemy with better connection pool settings for parallel processing
db = SQLAlchemy(engine_options={
    'pool_size': 20,  # Increased from default 5
    'max_overflow': 40,  # Increased from default 10
    'pool_timeout': 60,  # Increased from default 30
    'pool_pre_ping': True,  # Verify connections before using
    'connect_args': {
        'check_same_thread': False,  # Allow multi-threaded access for SQLite
        'timeout': 30,  # SQLite busy timeout in seconds
    }
})
