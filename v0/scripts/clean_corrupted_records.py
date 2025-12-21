#!/usr/bin/env python3
"""
Clean corrupted records from the database.
Removes records that cause database errors.
"""
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

def find_corrupted_incidents(db_path):
    """Find incident IDs that cause errors."""
    corrupted_ids = []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all incident IDs
        cursor.execute("SELECT id FROM incident")
        all_ids = [row[0] for row in cursor.fetchall()]
        
        print(f"Checking {len(all_ids)} incidents for corruption...")
        
        # Test each incident
        for incident_id in all_ids:
            try:
                cursor.execute("SELECT * FROM incident WHERE id = ?", (incident_id,))
                row = cursor.fetchone()
                if row is None:
                    corrupted_ids.append(incident_id)
                    print(f"  ⚠️  Incident {incident_id}: Not found")
            except sqlite3.DatabaseError as e:
                corrupted_ids.append(incident_id)
                print(f"  ❌ Incident {incident_id}: {str(e)[:50]}")
            except Exception as e:
                corrupted_ids.append(incident_id)
                print(f"  ❌ Incident {incident_id}: {str(e)[:50]}")
        
        conn.close()
        return corrupted_ids
        
    except Exception as e:
        print(f"Error checking incidents: {e}")
        return []

def clean_corrupted_records(db_path, corrupted_ids):
    """Remove corrupted records from database."""
    if not corrupted_ids:
        print("No corrupted records found.")
        return
    
    print(f"\nFound {len(corrupted_ids)} corrupted incident(s): {corrupted_ids}")
    response = input(f"\nRemove these {len(corrupted_ids)} corrupted record(s)? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Remove corrupted incidents
        for incident_id in corrupted_ids:
            try:
                # First, unlink any related extracted_events
                cursor.execute("UPDATE extracted_event SET incident_id = NULL WHERE incident_id = ?", (incident_id,))
                
                # Then delete the incident
                cursor.execute("DELETE FROM incident WHERE id = ?", (incident_id,))
                print(f"  ✅ Removed incident {incident_id}")
            except Exception as e:
                print(f"  ⚠️  Could not remove incident {incident_id}: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ Removed {len(corrupted_ids)} corrupted record(s)")
        print("Database cleaned. You may need to run VACUUM to reclaim space.")
        
    except Exception as e:
        print(f"Error cleaning records: {e}")

def vacuum_database(db_path):
    """Run VACUUM to optimize and repair database."""
    print("\nRunning VACUUM to optimize database...")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
        print("✅ VACUUM completed")
        return True
    except Exception as e:
        print(f"❌ VACUUM failed: {e}")
        return False

def main():
    """Main function."""
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '').replace('sqlite:////', '/')
    
    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        return
    
    print("=" * 70)
    print("Database Corruption Cleanup")
    print("=" * 70)
    print(f"Database: {db_path}")
    print()
    
    # Find corrupted records
    corrupted_ids = find_corrupted_incidents(db_path)
    
    if corrupted_ids:
        # Clean corrupted records
        clean_corrupted_records(db_path, corrupted_ids)
        
        # Run VACUUM
        vacuum_database(db_path)
        
        # Verify integrity
        print("\nVerifying database integrity...")
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            conn.close()
            
            if result[0] == 'ok':
                print("✅ Database integrity: OK")
            else:
                print(f"⚠️  Database integrity: {result[0][:200]}")
        except Exception as e:
            print(f"❌ Integrity check failed: {e}")
    else:
        print("✅ No corrupted records found!")
        # Still run VACUUM to optimize
        vacuum_database(db_path)

if __name__ == '__main__':
    main()

