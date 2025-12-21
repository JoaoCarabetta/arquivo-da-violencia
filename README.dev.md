# Development Setup

## Quick Start

```bash
# Start development environment
docker compose -f docker-compose.dev.yml up

# Or run in background
docker compose -f docker-compose.dev.yml up -d

# View logs
docker compose -f docker-compose.dev.yml logs -f

# Stop
docker compose -f docker-compose.dev.yml down
```

## Development Features

### ✅ No Authentication Required
- `ENABLE_AUTH=false` - No password needed to access admin panel
- Just go to http://localhost/admin and start working

### ✅ Frontend Hot-Reload
- Changes to files in `frontend/src/` automatically reload in the browser
- No need to rebuild the container
- Vite dev server with HMR (Hot Module Replacement)

### ✅ Backend Hot-Reload  
- Changes to `backend/app/` automatically reload the API
- Using `uvicorn --reload` flag
- No need to rebuild the container

### ✅ No Cron Jobs
- `ENABLE_CRON=false` - Pipeline doesn't run automatically
- Trigger jobs manually from the admin panel when needed

### ✅ Debug Mode
- `DEBUG=true` - More verbose logging
- Better error messages

## Access URLs

- **Frontend**: http://localhost (port 80)
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost/admin (no login required!)

## Environment Variables

Development uses `.env` file with these key settings:

```env
# Required
GEMINI_API_KEY=your-key-here

# Development settings (already configured in docker-compose.dev.yml)
DEBUG=true
ENABLE_AUTH=false
ENABLE_CRON=false
ADMIN_PASSWORD=
```

## File Structure

```
arquivo-da-violencia/
├── docker-compose.dev.yml    # Development configuration
├── docker-compose.yml         # Production configuration
├── docker-compose.staging.yml # Staging configuration
├── backend/
│   ├── app/                   # Backend code (hot-reload enabled)
│   └── Dockerfile
└── frontend/
    ├── src/                   # Frontend code (hot-reload enabled)
    ├── Dockerfile.dev         # Development Dockerfile with Vite
    └── Dockerfile             # Production Dockerfile with Nginx
```

## Development Workflow

1. **Start services**:
   ```bash
   docker compose -f docker-compose.dev.yml up
   ```

2. **Make changes**:
   - Edit files in `frontend/src/` → Browser auto-refreshes
   - Edit files in `backend/app/` → API auto-reloads

3. **Test the Gold Standard Editor**:
   - Go to http://localhost/admin/raw-events
   - Click any row to open the split-view editor
   - Edit JSON on the right, see original content on the left
   - Toggle gold standard, click save

4. **Run migrations** (if needed):
   ```bash
   docker compose -f docker-compose.dev.yml exec api alembic upgrade head
   ```

5. **Trigger pipeline manually**:
   - Go to http://localhost/admin
   - Use the pipeline controls to run jobs

## Differences from Production

| Feature | Development | Production |
|---------|-------------|------------|
| Authentication | Disabled | Required (JWT) |
| Frontend | Vite dev server | Nginx static files |
| Hot-reload | Enabled | Disabled |
| Cron jobs | Disabled | Optional |
| SSL/HTTPS | No | Yes |
| Debug logs | Verbose | Minimal |

## Troubleshooting

### Port already in use
```bash
# Stop all containers
docker compose -f docker-compose.dev.yml down

# Or kill process on port 80
sudo lsof -ti:80 | xargs kill -9
```

### Changes not reflecting
```bash
# Restart the service
docker compose -f docker-compose.dev.yml restart frontend
# or
docker compose -f docker-compose.dev.yml restart api
```

### Database issues
```bash
# Reset database
rm backend/app/instance/violence.db
docker compose -f docker-compose.dev.yml exec api alembic upgrade head
```

## Production Deployment

When ready to deploy to production, use the production compose file:

```bash
# Production
docker compose up -d

# Staging
docker compose -f docker-compose.staging.yml up -d
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full production setup instructions.
