#!/usr/bin/env python3
"""
Database repair utility for SQLite corruption issues.
Attempts to recover data from a corrupted database.
"""
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

def check_database_integrity(db_path):
    """Check database integrity."""
    print(f"Checking database integrity: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        conn.close()
        
        if result[0] == 'ok':
            print("✅ Database integrity check passed")
            return True
        else:
            print(f"❌ Database integrity check failed: {result[0]}")
            return False
    except Exception as e:
        print(f"❌ Error checking integrity: {e}")
        return False

def recover_database(db_path, backup_path=None):
    """Attempt to recover database using SQLite's recovery mechanism."""
    if backup_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{db_path}.corrupted_{timestamp}"
    
    print(f"\nAttempting database recovery...")
    print(f"Original database: {db_path}")
    print(f"Backup location: {backup_path}")
    
    try:
        # First, backup the corrupted database
        print("\n1. Creating backup of corrupted database...")
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        
        # Try to dump and recreate
        print("\n2. Attempting to dump database...")
        dump_path = f"{db_path}.dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        
        # Connect to corrupted database and try to dump
        try:
            conn = sqlite3.connect(db_path)
            with open(dump_path, 'w') as f:
                for line in conn.iterdump():
                    f.write(f'{line}\n')
            conn.close()
            print(f"✅ Database dumped to: {dump_path}")
        except Exception as e:
            print(f"⚠️  Could not dump database: {e}")
            print("   Trying alternative recovery method...")
            dump_path = None
        
        # Try to recover using .recover
        print("\n3. Attempting SQLite recovery...")
        recovered_path = f"{db_path}.recovered_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Use sqlite3 command line tool if available
            import subprocess
            result = subprocess.run(
                ['sqlite3', db_path, '.recover'],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                # Write recovered data to new database
                conn = sqlite3.connect(recovered_path)
                conn.executescript(result.stdout)
                conn.close()
                print(f"✅ Recovered database created: {recovered_path}")
                
                # Verify recovered database
                if check_database_integrity(recovered_path):
                    print("\n✅ Recovery successful! Recovered database is valid.")
                    print(f"\nTo use the recovered database:")
                    print(f"  1. Stop the application")
                    print(f"  2. Backup current database: mv {db_path} {db_path}.old")
                    print(f"  3. Use recovered database: mv {recovered_path} {db_path}")
                    print(f"  4. Restart the application")
                    return recovered_path
                else:
                    print("❌ Recovered database failed integrity check")
            else:
                print(f"❌ Recovery command failed: {result.stderr}")
        except FileNotFoundError:
            print("⚠️  sqlite3 command-line tool not found. Trying Python-based recovery...")
        except Exception as e:
            print(f"❌ Recovery failed: {e}")
        
        # Alternative: Try to create new database and import what we can
        if dump_path and os.path.exists(dump_path):
            print("\n4. Attempting to recreate database from dump...")
            new_db_path = f"{db_path}.new_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                conn = sqlite3.connect(new_db_path)
                with open(dump_path, 'r') as f:
                    conn.executescript(f.read())
                conn.close()
                
                if check_database_integrity(new_db_path):
                    print(f"✅ New database created from dump: {new_db_path}")
                    return new_db_path
            except Exception as e:
                print(f"❌ Failed to recreate from dump: {e}")
        
        print("\n❌ Automatic recovery failed. Manual intervention required.")
        print("\nOptions:")
        print("  1. Restore from a backup if available")
        print("  2. Recreate the database (data will be lost)")
        print("  3. Contact database recovery specialist")
        
        return None
        
    except Exception as e:
        print(f"❌ Recovery process failed: {e}")
        return None

def recreate_database(db_path):
    """Recreate database from scratch (WARNING: Data loss)."""
    print(f"\n⚠️  WARNING: This will DELETE the current database and create a new empty one!")
    print(f"Database: {db_path}")
    
    response = input("Are you sure you want to proceed? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return False
    
    try:
        # Backup current database
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{db_path}.deleted_{timestamp}"
        import shutil
        if os.path.exists(db_path):
            shutil.move(db_path, backup_path)
            print(f"✅ Old database backed up to: {backup_path}")
        
        # Remove WAL and SHM files
        for ext in ['-wal', '-shm']:
            wal_path = f"{db_path}{ext}"
            if os.path.exists(wal_path):
                os.remove(wal_path)
                print(f"✅ Removed: {wal_path}")
        
        # Create new database
        conn = sqlite3.connect(db_path)
        conn.close()
        print(f"✅ New empty database created: {db_path}")
        
        print("\nNext steps:")
        print("  1. Run migrations: uv run python entrypoints/manage.py db_upgrade")
        print("  2. Restart the application")
        
        return True
    except Exception as e:
        print(f"❌ Failed to recreate database: {e}")
        return False

def main():
    """Main function."""
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '').replace('sqlite:////', '/')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return
    
    print("=" * 70)
    print("SQLite Database Repair Utility")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Size: {os.path.getsize(db_path) / 1024 / 1024:.2f} MB")
    print()
    
    # Check integrity
    is_ok = check_database_integrity(db_path)
    
    if is_ok:
        print("\n✅ Database appears to be healthy. No action needed.")
        return
    
    print("\n" + "=" * 70)
    print("Database is corrupted. Attempting recovery...")
    print("=" * 70)
    
    # Try recovery
    recovered_path = recover_database(db_path)
    
    if not recovered_path:
        print("\n" + "=" * 70)
        print("Recovery Options")
        print("=" * 70)
        print("\n1. Recreate database (WARNING: All data will be lost)")
        print("2. Exit and restore from backup manually")
        
        choice = input("\nEnter choice (1 or 2): ")
        if choice == '1':
            recreate_database(db_path)
        else:
            print("Exiting. Please restore from backup manually.")

if __name__ == '__main__':
    main()

