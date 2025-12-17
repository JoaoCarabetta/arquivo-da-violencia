# Database Recovery Guide

## Current Situation

Your SQLite database (`instance/violence.db`) is corrupted and showing the error:
```
sqlite3.DatabaseError: database disk image is malformed
```

A backup of the corrupted database has been created automatically.

## Recovery Options

### Option 1: Restore from Backup (Recommended if you have one)

If you have a previous backup of the database:

```bash
# Stop the application first
docker-compose down  # if using Docker
# or stop your local server

# Restore from backup
cp instance/violence.db.backup instance/violence.db

# Remove WAL files
rm -f instance/violence.db-wal instance/violence.db-shm

# Restart application
docker-compose up -d  # if using Docker
```

### Option 2: Recreate Database (Data Loss)

If you don't have a backup or the data loss is acceptable:

**Using the script:**
```bash
./scripts/recreate_database.sh
```

**Or manually:**
```bash
# Backup corrupted database (already done, but double-check)
cp instance/violence.db instance/violence.db.corrupted_$(date +%Y%m%d_%H%M%S)

# Remove corrupted database and WAL files
rm -f instance/violence.db instance/violence.db-wal instance/violence.db-shm

# Create new empty database
touch instance/violence.db
chmod 666 instance/violence.db

# Run migrations to recreate schema
uv run python entrypoints/manage.py db_upgrade

# Restart application
```

### Option 3: Try Advanced Recovery

If the data is critical, you can try:

1. **Use sqlite3 command-line tool:**
   ```bash
   sqlite3 instance/violence.db ".recover" | sqlite3 instance/violence.db.recovered
   ```

2. **Use third-party tools:**
   - [SQLite Recovery](https://www.systoolsgroup.com/sqlite-recovery)
   - [Stellar SQLite Recovery](https://www.stellarinfo.com/sqlite-recovery.php)

## Prevention

To prevent future corruption:

1. **Regular Backups:**
   ```bash
   # Add to cron for daily backups
   0 2 * * * cp /opt/arquivo-da-violencia/instance/violence.db /opt/backups/violence.db.$(date +\%Y\%m\%d)
   ```

2. **Proper Shutdown:**
   - Always stop services gracefully: `docker-compose stop`
   - Don't kill processes abruptly
   - Don't remove database files while application is running

3. **Disk Space:**
   - Ensure adequate disk space
   - Monitor disk usage regularly

4. **Consider PostgreSQL:**
   - For production, consider migrating to PostgreSQL
   - Better concurrency and reliability
   - See PRODUCTION_TUTORIAL.md for setup

## Current Backup Files

The following backup files exist:
- `instance/violence.db.corrupted_20251217_160408` - Automatic backup created during repair attempt

## Next Steps

1. **Decide on recovery approach** (restore backup vs recreate)
2. **If recreating:** Run migrations to set up schema
3. **Restart application** and verify it works
4. **Set up regular backups** to prevent data loss

## Quick Recovery Commands

```bash
# Check database integrity
uv run python scripts/repair_database.py

# Recreate database (interactive)
./scripts/recreate_database.sh

# After recreation, run migrations
uv run python entrypoints/manage.py db_upgrade
```

