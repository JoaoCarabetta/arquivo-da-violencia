#!/usr/bin/env python3
"""
Advanced database recovery using multiple methods.
Attempts to extract as much data as possible from corrupted database.
"""
import sqlite3
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

def method1_sqlite_recover(db_path, output_path):
    """Method 1: Use sqlite3 .recover command."""
    print(f"\n[Method 1] Using sqlite3 .recover command...")
    try:
        # Try using sqlite3 command line tool
        result = subprocess.run(
            ['sqlite3', db_path, '.recover'],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0 and result.stdout:
            # Write recovered SQL to new database
            conn = sqlite3.connect(output_path)
            # Split by semicolons and execute statements
            statements = result.stdout.split(';')
            for stmt in statements:
                stmt = stmt.strip()
                if stmt and not stmt.startswith('--'):
                    try:
                        conn.executescript(stmt + ';')
                    except Exception as e:
                        print(f"   ⚠️  Skipped statement: {str(e)[:50]}")
            conn.close()
            print(f"   ✅ Recovered SQL written to: {output_path}")
            return True
        else:
            print(f"   ❌ Command failed: {result.stderr[:200]}")
            return False
    except FileNotFoundError:
        print("   ⚠️  sqlite3 command not found")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def method2_python_dump(db_path, output_path):
    """Method 2: Try to read database with Python and dump what we can."""
    print(f"\n[Method 2] Attempting Python-based recovery...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Try to get table names
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"   Found {len(tables)} tables")
        except:
            print("   ⚠️  Could not read table list")
            tables = []
        
        # Create new database
        new_conn = sqlite3.connect(output_path)
        new_cursor = new_conn.cursor()
        
        recovered_count = 0
        
        for (table_name,) in tables:
            try:
                # Try to get schema
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                schema = cursor.fetchone()
                if schema and schema[0]:
                    new_cursor.execute(schema[0])
                    print(f"   ✅ Recreated table: {table_name}")
                
                # Try to read data
                try:
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchmany(1000)  # Read in chunks
                    if rows:
                        # Get column names
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = [col[1] for col in cursor.fetchall()]
                        
                        # Insert data
                        placeholders = ','.join(['?' for _ in columns])
                        insert_sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
                        
                        for row in rows:
                            try:
                                new_cursor.execute(insert_sql, row)
                                recovered_count += 1
                            except:
                                pass
                        
                        # Continue reading
                        while True:
                            more_rows = cursor.fetchmany(1000)
                            if not more_rows:
                                break
                            for row in more_rows:
                                try:
                                    new_cursor.execute(insert_sql, row)
                                    recovered_count += 1
                                except:
                                    pass
                        
                        new_conn.commit()
                        print(f"   ✅ Recovered {recovered_count} rows from {table_name}")
                except Exception as e:
                    print(f"   ⚠️  Could not recover data from {table_name}: {str(e)[:50]}")
            except Exception as e:
                print(f"   ⚠️  Could not recover table {table_name}: {str(e)[:50]}")
        
        new_conn.close()
        conn.close()
        
        if recovered_count > 0:
            print(f"   ✅ Total rows recovered: {recovered_count}")
            return True
        else:
            print("   ❌ No data could be recovered")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def method3_hex_recovery(db_path, output_path):
    """Method 3: Try to read raw database pages."""
    print(f"\n[Method 3] Attempting raw database reading...")
    try:
        # This is a last resort - try to read the database file directly
        # and extract any readable SQL statements
        with open(db_path, 'rb') as f:
            data = f.read()
        
        # Look for SQL-like patterns in the binary data
        # This is very basic and may not work
        text_data = data.decode('utf-8', errors='ignore')
        
        # Try to find CREATE TABLE statements
        create_statements = []
        for line in text_data.split('\n'):
            if 'CREATE TABLE' in line.upper():
                create_statements.append(line)
        
        if create_statements:
            conn = sqlite3.connect(output_path)
            for stmt in create_statements[:10]:  # Limit to avoid errors
                try:
                    conn.execute(stmt)
                except:
                    pass
            conn.close()
            print(f"   ✅ Found {len(create_statements)} CREATE statements")
            return len(create_statements) > 0
        
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def verify_recovered_db(db_path):
    """Verify recovered database integrity."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check integrity
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        
        # Count tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        # Count total rows
        total_rows = 0
        for (table_name,) in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                total_rows += count
            except:
                pass
        
        conn.close()
        
        if result[0] == 'ok':
            print(f"   ✅ Database integrity: OK")
            print(f"   ✅ Tables: {len(tables)}")
            print(f"   ✅ Total rows: {total_rows}")
            return True
        else:
            print(f"   ⚠️  Database integrity: {result[0][:100]}")
            print(f"   ⚠️  Tables: {len(tables)}")
            print(f"   ⚠️  Total rows: {total_rows}")
            return len(tables) > 0
        
    except Exception as e:
        print(f"   ❌ Verification failed: {e}")
        return False

def main():
    """Main recovery function."""
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '').replace('sqlite:////', '/')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return
    
    print("=" * 70)
    print("Advanced Database Recovery")
    print("=" * 70)
    print(f"Source database: {db_path}")
    print(f"Size: {os.path.getsize(db_path) / 1024 / 1024:.2f} MB")
    print()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    recovery_paths = []
    
    # Try Method 1
    recovery_path1 = f"{db_path}.recovered_method1_{timestamp}"
    if method1_sqlite_recover(db_path, recovery_path1):
        recovery_paths.append(recovery_path1)
    
    # Try Method 2
    recovery_path2 = f"{db_path}.recovered_method2_{timestamp}"
    if method2_python_dump(db_path, recovery_path2):
        recovery_paths.append(recovery_path2)
    
    # Try Method 3 (only if others failed)
    if not recovery_paths:
        recovery_path3 = f"{db_path}.recovered_method3_{timestamp}"
        if method3_hex_recovery(db_path, recovery_path3):
            recovery_paths.append(recovery_path3)
    
    print("\n" + "=" * 70)
    print("Recovery Results")
    print("=" * 70)
    
    if recovery_paths:
        print(f"\n✅ Successfully created {len(recovery_paths)} recovery attempt(s):")
        best_path = None
        best_score = 0
        
        for path in recovery_paths:
            print(f"\nVerifying: {os.path.basename(path)}")
            if verify_recovered_db(path):
                # Score based on integrity and data
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                table_count = len(cursor.fetchall())
                
                total_rows = 0
                for (table_name,) in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        total_rows += cursor.fetchone()[0]
                    except:
                        pass
                
                conn.close()
                score = table_count * 100 + total_rows
                
                if score > best_score:
                    best_score = score
                    best_path = path
                
                print(f"   Score: {score} (tables: {table_count}, rows: {total_rows})")
        
        if best_path:
            print(f"\n✅ Best recovery: {os.path.basename(best_path)}")
            print(f"\nTo use the recovered database:")
            print(f"  1. Stop the application")
            print(f"  2. Backup current: mv {db_path} {db_path}.old")
            print(f"  3. Use recovered: cp {best_path} {db_path}")
            print(f"  4. Remove WAL files: rm -f {db_path}-wal {db_path}-shm")
            print(f"  5. Restart the application")
        else:
            print("\n⚠️  Recovered databases have issues. Manual review recommended.")
    else:
        print("\n❌ All recovery methods failed.")
        print("The database is too corrupted for automatic recovery.")
        print("Options:")
        print("  1. Restore from a previous backup")
        print("  2. Use professional SQLite recovery tools")
        print("  3. Recreate the database (data loss)")

if __name__ == '__main__':
    main()

