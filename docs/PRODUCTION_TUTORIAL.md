# Production Deployment Tutorial

Complete guide to deploy Arquivo da Violência to a production server and expose it to the internet.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [Application Deployment](#application-deployment)
4. [Reverse Proxy Setup (Nginx)](#reverse-proxy-setup-nginx)
5. [SSL/TLS with Let's Encrypt](#ssltls-with-lets-encrypt)
6. [Final Configuration](#final-configuration)
7. [Maintenance](#maintenance)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

- A Linux server (Ubuntu 20.04+ or Debian 11+ recommended)
- Root or sudo access
- A domain name pointing to your server's IP address
- Basic knowledge of Linux command line

## Server Setup

### 1. Update System Packages

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

**Important**: Log out and log back in for the docker group changes to take effect.

### 3. Install Nginx (for reverse proxy)

```bash
sudo apt install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx
```

### 4. Configure Firewall

```bash
# Allow SSH (important - don't lock yourself out!)
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

## Application Deployment

### 1. Clone the Repository

```bash
# Navigate to a suitable directory
cd /opt

# Clone your repository (replace with your actual repository URL)
sudo git clone <your-repository-url> arquivo-da-violencia
cd arquivo-da-violencia

# Or if you're uploading files manually, create the directory:
# sudo mkdir -p /opt/arquivo-da-violencia
# cd /opt/arquivo-da-violencia
# # Upload your files here
```

### 2. Create Environment File

Create a `.env` file with production settings:

```bash
sudo nano .env
```

Add the following configuration:

```bash
# Database Configuration
DATABASE_URL=sqlite:////app/instance/violence.db

# Application Mode - IMPORTANT: Set to true for production
PUBLIC_MODE=true

# Google Maps API Key (optional, for map features)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Logging Configuration
LOG_LEVEL=INFO
LOG_ROTATION_SIZE=10 MB
LOG_RETENTION_DAYS=30

# Pipeline Configuration
PIPELINE_INTERVAL_MINUTES=30
PIPELINE_WORKERS=10
```

**Critical**: Set `PUBLIC_MODE=true` to hide admin pages (sources and extractions) from public access in production.

Save and exit (Ctrl+X, then Y, then Enter).

### 3. Create Required Directories

```bash
sudo mkdir -p instance logs
sudo chmod 755 instance logs
```

### 4. Build and Start Services

```bash
# Build Docker images
sudo docker-compose build

# Start services in detached mode
sudo docker-compose up -d

# Check service status
sudo docker-compose ps

# View logs to verify everything is working
sudo docker-compose logs -f
```

### 5. Initialize Database

```bash
# Run database migrations
sudo docker-compose exec web python entrypoints/manage.py db_upgrade
```

### 6. Verify Services are Running

```bash
# Check if web service is responding (should return HTTP 200)
curl http://localhost:5001

# Check scheduler logs
sudo docker-compose logs scheduler
```

## Reverse Proxy Setup (Nginx)

### 1. Create Nginx Configuration

Create a new Nginx configuration file for your domain:

```bash
sudo nano /etc/nginx/sites-available/arquivo-violencia
```

Add the following configuration (replace `your-domain.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # Logging
    access_log /var/log/nginx/arquivo-violencia-access.log;
    error_log /var/log/nginx/arquivo-violencia-error.log;

    # Proxy settings
    location / {
        proxy_pass http://localhost:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Increase body size limit for file uploads (if needed)
    client_max_body_size 10M;
}
```

Save and exit.

### 2. Enable the Site

```bash
# Create symbolic link to enable the site
sudo ln -s /etc/nginx/sites-available/arquivo-violencia /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# If test is successful, reload Nginx
sudo systemctl reload nginx
```

### 3. Verify Nginx is Working

```bash
# Check Nginx status
sudo systemctl status nginx

# Test from your local machine (replace with your domain)
curl http://your-domain.com
```

## SSL/TLS with Let's Encrypt

### 1. Install Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 2. Obtain SSL Certificate

```bash
# Replace with your actual domain and email
sudo certbot --nginx -d your-domain.com -d www.your-domain.com --email your-email@example.com --agree-tos --non-interactive
```

Certbot will automatically:
- Obtain SSL certificates
- Configure Nginx to use HTTPS
- Set up automatic renewal

### 3. Verify SSL Certificate

```bash
# Test SSL configuration
sudo certbot certificates

# Test automatic renewal
sudo certbot renew --dry-run
```

### 4. Update Nginx Configuration (if needed)

After Certbot runs, your Nginx config will be updated automatically. You can verify:

```bash
sudo cat /etc/nginx/sites-available/arquivo-violencia
```

You should see SSL configuration and redirects from HTTP to HTTPS.

## Final Configuration

### 1. Update Docker Compose Port (Optional)

If you want to change the internal port, edit `docker-compose.yml`:

```yaml
ports:
  - "5001:5000"  # Change 5001 to your preferred port
```

Then update the Nginx `proxy_pass` URL accordingly and restart:

```bash
sudo docker-compose restart
sudo systemctl reload nginx
```

### 2. Set Up Automatic Startup

Create a systemd service to ensure Docker Compose starts on boot:

```bash
sudo nano /etc/systemd/system/arquivo-violencia.service
```

Add:

```ini
[Unit]
Description=Arquivo da Violencia Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/arquivo-da-violencia
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable arquivo-violencia.service
sudo systemctl start arquivo-violencia.service
```

### 3. Verify Everything is Working

```bash
# Check Docker containers
sudo docker-compose ps

# Check Nginx
sudo systemctl status nginx

# Check application logs
sudo docker-compose logs web --tail=50
sudo docker-compose logs scheduler --tail=50

# Test from browser
# Visit: https://your-domain.com
```

## Maintenance

### Viewing Logs

```bash
# Application logs
sudo docker-compose logs -f web
sudo docker-compose logs -f scheduler

# Nginx logs
sudo tail -f /var/log/nginx/arquivo-violencia-access.log
sudo tail -f /var/log/nginx/arquivo-violencia-error.log
```

### Updating the Application

```bash
cd /opt/arquivo-da-violencia

# Pull latest changes (if using git)
sudo git pull

# Rebuild and restart
sudo docker-compose build
sudo docker-compose up -d

# Run migrations if needed
sudo docker-compose exec web python entrypoints/manage.py db_upgrade
```

### Backing Up the Database

```bash
# Create backup
sudo docker-compose exec web cp /app/instance/violence.db /app/instance/violence.db.backup.$(date +%Y%m%d)

# Or copy to host
sudo docker cp arquivo-violencia-web:/app/instance/violence.db /opt/backups/violence.db.$(date +%Y%m%d)
```

### Restarting Services

```bash
# Restart all services
sudo docker-compose restart

# Restart specific service
sudo docker-compose restart web
sudo docker-compose restart scheduler

# Stop services
sudo docker-compose stop

# Start services
sudo docker-compose start
```

## Troubleshooting

### Services Won't Start

```bash
# Check Docker status
sudo systemctl status docker

# Check container logs
sudo docker-compose logs

# Check if ports are in use
sudo netstat -tulpn | grep 5001
```

### Database Issues

```bash
# Check database file permissions
sudo ls -la instance/

# Fix permissions if needed
sudo chmod 666 instance/violence.db
sudo chmod 755 instance/

# Check database connection
sudo docker-compose exec web python -c "from app import create_app; from app.extensions import db; app = create_app(); app.app_context().push(); db.engine.connect(); print('OK')"
```

### Nginx Issues

```bash
# Test Nginx configuration
sudo nginx -t

# Check Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Restart Nginx
sudo systemctl restart nginx
```

### SSL Certificate Renewal

Certbot automatically renews certificates. To manually renew:

```bash
sudo certbot renew
sudo systemctl reload nginx
```

### Can't Access Website

1. **Check firewall**: `sudo ufw status`
2. **Check Nginx**: `sudo systemctl status nginx`
3. **Check Docker**: `sudo docker-compose ps`
4. **Check DNS**: Ensure your domain points to the server IP
5. **Check ports**: `sudo netstat -tulpn | grep -E '(80|443|5001)'`

### PUBLIC_MODE Not Working

Verify the environment variable is set correctly:

```bash
# Check .env file
cat .env | grep PUBLIC_MODE

# Should show: PUBLIC_MODE=true

# Restart services after changing .env
sudo docker-compose down
sudo docker-compose up -d
```

## Security Checklist

- [ ] `PUBLIC_MODE=true` is set in `.env`
- [ ] Firewall is configured (UFW)
- [ ] SSL/TLS is enabled (HTTPS)
- [ ] Strong passwords for any admin accounts
- [ ] Regular backups are configured
- [ ] System packages are up to date
- [ ] Docker and Nginx are running latest stable versions
- [ ] Logs are being monitored
- [ ] Database file has proper permissions

## Quick Reference

### Essential Commands

```bash
# Start services
sudo docker-compose up -d

# Stop services
sudo docker-compose down

# View logs
sudo docker-compose logs -f

# Restart services
sudo docker-compose restart

# Update application
sudo git pull && sudo docker-compose build && sudo docker-compose up -d

# Check status
sudo docker-compose ps
sudo systemctl status nginx
```

### Important Files

- `.env` - Environment configuration (including PUBLIC_MODE)
- `docker-compose.yml` - Docker service configuration
- `/etc/nginx/sites-available/arquivo-violencia` - Nginx configuration
- `/opt/arquivo-da-violencia/instance/` - Database files
- `/opt/arquivo-da-violencia/logs/` - Application logs

## Next Steps

1. Set up monitoring (e.g., UptimeRobot, Pingdom)
2. Configure automated backups
3. Set up log rotation
4. Consider using PostgreSQL instead of SQLite for better performance
5. Set up a CDN for static assets
6. Configure rate limiting in Nginx
7. Set up email notifications for errors

## Support

If you encounter issues:

1. Check the logs: `sudo docker-compose logs`
2. Verify configuration: Check `.env` file and Nginx config
3. Test components individually: Docker, Nginx, DNS
4. Review this tutorial's troubleshooting section

---

**Remember**: Always set `PUBLIC_MODE=true` in production to hide admin pages from public access!

