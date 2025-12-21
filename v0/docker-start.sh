#!/bin/bash
# Quick start script for Docker deployment

set -e

echo "🚀 Starting Arquivo da Violência..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cat > .env << EOF
# Database Configuration
DATABASE_URL=sqlite:///app/instance/violence.db

# Application Mode
PUBLIC_MODE=false

# Google Maps API Key (optional)
GOOGLE_MAPS_API_KEY=

# Logging Configuration
LOG_LEVEL=INFO
LOG_ROTATION_SIZE=10 MB
LOG_RETENTION_DAYS=30

# Pipeline Configuration
PIPELINE_INTERVAL_MINUTES=30
PIPELINE_WORKERS=10
EOF
    echo "✅ Created .env file. Please edit it if needed."
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p instance logs
chmod 755 instance logs

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Initialize database
echo "🗄️  Initializing database..."
docker-compose exec -T web python entrypoints/manage.py db_upgrade || echo "⚠️  Database migration may have failed, but continuing..."

echo ""
echo "✅ Setup complete!"
echo ""
echo "📊 Services are running:"
echo "   - Web server: http://localhost:5000"
echo "   - Scheduler: Running pipeline every 30 minutes"
echo ""
echo "📝 Useful commands:"
echo "   - View logs: docker-compose logs -f"
echo "   - Stop services: docker-compose stop"
echo "   - Restart services: docker-compose restart"
echo "   - View scheduler logs: docker-compose logs -f scheduler"
echo ""

