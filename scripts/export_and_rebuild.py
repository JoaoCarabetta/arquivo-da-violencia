#!/usr/bin/env python3
"""
Export data from corrupted database and rebuild a clean one.
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

def export_table_data(conn, table_name, new_conn):
    """Export data from one table to another database."""
    try:
        cursor = conn.cursor()
        new_cursor = new_conn.cursor()
        
        # Get table schema
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        schema = cursor.fetchone()
        if not schema or not schema[0]:
            print(f"  ⚠️  No schema found for {table_name}")
            return 0
        
        # Create table in new database
        try:
            new_cursor.execute(schema[0])
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"  ⚠️  Could not create table {table_name}: {e}")
                return 0
        
        # Get column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        if not columns:
            return 0
        
        # Export data row by row
        exported = 0
        cursor.execute(f"SELECT * FROM {table_name}")
        
        placeholders = ','.join(['?' for _ in columns])
        insert_sql = f"INSERT OR IGNORE INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
        
        while True:
            try:
                rows = cursor.fetchmany(100)
                if not rows:
                    break
                
                for row in rows:
                    try:
                        # Handle None values and ensure proper types
                        clean_row = []
                        for val in row:
                            if val is None:
                                clean_row.append(None)
                            else:
                                clean_row.append(val)
                        
                        new_cursor.execute(insert_sql, clean_row)
                        exported += 1
                    except Exception as e:
                        # Skip problematic rows
                        continue
                
                new_conn.commit()
            except sqlite3.DatabaseError:
                # Can't read more from this table
                break
            except Exception:
                break
        
        return exported
        
    except Exception as e:
        print(f"  ❌ Error exporting {table_name}: {e}")
        return 0

def rebuild_database(old_db_path, new_db_path):
    """Rebuild database by exporting and importing data."""
    print(f"Exporting from: {old_db_path}")
    print(f"Creating new database: {new_db_path}")
    print()
    
    # Remove new database if exists
    if Path(new_db_path).exists():
        Path(new_db_path).unlink()
    
    # Connect to both databases
    try:
        old_conn = sqlite3.connect(old_db_path)
        new_conn = sqlite3.connect(new_db_path)
    except Exception as e:
        print(f"❌ Could not connect to databases: {e}")
        return False
    
    # Get list of tables
    try:
        cursor = old_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(tables)} tables: {', '.join(tables)}")
    except Exception as e:
        print(f"❌ Could not get table list: {e}")
        old_conn.close()
        new_conn.close()
        return False
    
    # Export each table
    total_exported = 0
    for table in tables:
        print(f"\nExporting {table}...")
        try:
            count = export_table_data(old_conn, table, new_conn)
            print(f"  ✅ Exported {count} rows from {table}")
            total_exported += count
        except Exception as e:
            print(f"  ❌ Failed to export {table}: {e}")
    
    old_conn.close()
    new_conn.close()
    
    print(f"\n✅ Total rows exported: {total_exported}")
    
    # Verify new database
    print("\nVerifying new database...")
    try:
        new_conn = sqlite3.connect(new_db_path)
        cursor = new_conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        new_conn.close()
        
        if result[0] == 'ok':
            print("✅ New database integrity: OK")
            return True
        else:
            print(f"⚠️  New database integrity: {result[0][:200]}")
            return False
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main function."""
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '').replace('sqlite:////', '/')
    
    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_db_path = f"{db_path}.rebuilt_{timestamp}"
    
    print("=" * 70)
    print("Database Rebuild Utility")
    print("=" * 70)
    print(f"Source: {db_path}")
    print(f"Target: {new_db_path}")
    print()
    
    # Rebuild database
    success = rebuild_database(db_path, new_db_path)
    
    if success:
        print("\n" + "=" * 70)
        print("Rebuild Successful!")
        print("=" * 70)
        print(f"\nTo use the rebuilt database:")
        print(f"  1. Stop the application")
        print(f"  2. Backup current: mv {db_path} {db_path}.old2")
        print(f"  3. Use rebuilt: mv {new_db_path} {db_path}")
        print(f"  4. Remove WAL files: rm -f {db_path}-wal {db_path}-shm")
        print(f"  5. Restart the application")
    else:
        print("\n⚠️  Rebuild completed but verification had issues.")
        print("The new database may still have some problems.")

if __name__ == '__main__':
    main()

