#!/bin/bash
# Helper script to ensure Docker Compose uses the correct .env file

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory (v1/)
cd "$SCRIPT_DIR"

echo "📂 Working directory: $(pwd)"
echo "📄 Checking .env file..."

if [ -f .env ]; then
    echo "✅ .env file found"
    echo ""
    echo "🔑 Environment variables loaded:"
    grep -v "^#" .env | grep -v "^$" | sed 's/=.*/=***/' | head -5
    echo ""
else
    echo "❌ .env file not found!"
    echo "📝 Copy env.example to .env and configure it:"
    echo "   cp env.example .env"
    exit 1
fi

echo "🐳 Starting Docker Compose..."
docker compose --env-file .env up -d --build "$@"

echo ""
echo "✅ Done! Services are starting..."
echo "🌐 Frontend: http://localhost:80"
echo "🔧 Backend API: http://localhost:8000"
echo "📊 Admin: http://localhost:80/admin"

