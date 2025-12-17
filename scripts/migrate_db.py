import sys
import os
import sqlite3
from loguru import logger

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config

def migrate():
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
    logger.info(f"Migrating database at {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE source ADD COLUMN resolved_url TEXT")
        conn.commit()
        logger.info("Successfully added 'resolved_url' column.")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            logger.info("Column 'resolved_url' already exists.")
        else:
            logger.error(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
