# Deployment Guide

This guide explains how to deploy the Arquivo da Violência application using Docker.

## Prerequisites

- Docker and Docker Compose installed on your server
- (Optional) Google Maps API key if you want map features

## Quick Start

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd arquivo-da-violencia
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` file** with your configuration:
   ```bash
   nano .env
   ```
   
   Key settings:
   - `PUBLIC_MODE`: Set to `true` for production (hides admin pages)
   - `GOOGLE_MAPS_API_KEY`: Your Google Maps API key (optional)
   - `PIPELINE_INTERVAL_MINUTES`: How often to fetch new data (default: 30)

4. **Build and start the services**:
   ```bash
   docker-compose up -d
   ```

5. **Initialize the database** (first time only):
   ```bash
   docker-compose exec web python entrypoints/manage.py db_upgrade
   ```

6. **Check the logs**:
   ```bash
   # Web server logs
   docker-compose logs -f web
   
   # Scheduler logs
   docker-compose logs -f scheduler
   ```

## Services

The Docker Compose setup includes two services:

### 1. Web Service (`web`)
- Serves the Flask application on port 5000
- Uses Gunicorn as the WSGI server
- Automatically restarts on failure

### 2. Scheduler Service (`scheduler`)
- Runs the data pipeline every 30 minutes (configurable)
- Fetches new data, extracts events, and enriches incidents
- Runs independently from the web server

## Configuration

### Environment Variables

All configuration is done through environment variables in the `.env` file:

- `DATABASE_URL`: Database connection string (default: SQLite)
- `PUBLIC_MODE`: Enable public mode (hides admin pages)
- `GOOGLE_MAPS_API_KEY`: Google Maps API key for map features
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `PIPELINE_INTERVAL_MINUTES`: Minutes between pipeline runs (default: 30)
- `PIPELINE_WORKERS`: Number of parallel workers (default: 10)

### Port Configuration

The web service is exposed on port 5000 by default. To change it, modify the `ports` section in `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"  # Change 8080 to your desired port
```

## Data Persistence

The following directories are mounted as volumes to persist data:

- `./instance`: Database files
- `./logs`: Application logs

**Important**: Make sure these directories exist and have proper permissions:

```bash
mkdir -p instance logs
chmod 755 instance logs
```

## Database Migrations

When updating the application, run database migrations:

```bash
docker-compose exec web python entrypoints/manage.py db_upgrade
```

## Monitoring

### Check Service Status

```bash
docker-compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f scheduler
```

### Check Health

The web service includes a health check. You can verify it's running:

```bash
curl http://localhost:5000/
```

## Updating the Application

1. **Pull latest code**:
   ```bash
   git pull
   ```

2. **Rebuild containers**:
   ```bash
   docker-compose build
   ```

3. **Restart services**:
   ```bash
   docker-compose up -d
   ```

4. **Run migrations** (if needed):
   ```bash
   docker-compose exec web python entrypoints/manage.py db_upgrade
   ```

## Troubleshooting

### Services won't start

Check the logs:
```bash
docker-compose logs
```

### Database errors

Ensure the `instance` directory exists and is writable:
```bash
mkdir -p instance
chmod 755 instance
```

### Scheduler not running

Check scheduler logs:
```bash
docker-compose logs scheduler
```

The scheduler runs the pipeline immediately on startup, then every N minutes. Check the logs to see when the next run is scheduled.

### Port already in use

If port 5000 is already in use, change it in `docker-compose.yml`:
```yaml
ports:
  - "8080:5000"
```

## Production Recommendations

1. **Use a reverse proxy** (nginx, Traefik, etc.) in front of the application
2. **Set up SSL/TLS** certificates (Let's Encrypt)
3. **Use PostgreSQL** instead of SQLite for better performance and reliability
4. **Set up log rotation** and monitoring
5. **Configure backups** for the database
6. **Use environment-specific `.env` files** (don't commit `.env` to git)

## Backup

To backup the database:

```bash
# SQLite backup
docker-compose exec web cp instance/violence.db instance/violence.db.backup

# Or copy the entire instance directory
cp -r instance instance.backup
```

## Stopping the Application

```bash
# Stop services
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop and remove containers, volumes, and images
docker-compose down -v --rmi all
```
