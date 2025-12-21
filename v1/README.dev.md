# Development Setup with Auto-Reload

## Quick Start

### Option 1: Development Mode (Hot Reload - Recommended for Development)

Uses Vite dev server with instant hot-reload. No rebuild needed for code changes.

```bash
# Start with development config
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Or with watch mode (auto-rebuilds on config changes)
docker compose -f docker-compose.yml -f docker-compose.dev.yml watch
```

Frontend will be available at: `http://localhost:5173`

### Option 2: Production Mode with Auto-Rebuild

For production builds with automatic rebuilds when files change:

1. Uncomment the `develop.watch` section in `docker-compose.yml` (frontend service)
2. Run:
   ```bash
   docker compose watch
   ```

Frontend will be available at: `http://localhost:80`

### Option 3: Manual Rebuild (Production)

For explicit control (recommended for production):

```bash
# Rebuild and restart frontend
docker compose up -d --build frontend

# Or rebuild all services
docker compose up -d --build
```

## How It Works

### Development Mode (`docker-compose.dev.yml`)
- Uses `Dockerfile.dev` which runs Vite dev server
- **File sync**: Source files are synced directly (instant changes, no rebuild)
- **Auto-rebuild**: Only rebuilds when `package.json`, `Dockerfile`, or config files change
- Hot module replacement (HMR) works automatically

### Production Mode with Watch
- Uses production `Dockerfile` (multi-stage build with nginx)
- **Auto-rebuild**: Rebuilds entire image when source files change
- Serves static files via nginx
- Takes longer than dev mode but matches production environment

## When to Use Each

- **Development**: Use `docker-compose.dev.yml` for active development
- **Production Testing**: Use production mode with watch to test production builds
- **Production Deployment**: Use manual rebuilds for explicit control

