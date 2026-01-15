# PRDForge Deployment Guide

This guide covers deploying PRDForge for production use.

## Deployment Options

| Option | Best For | Complexity |
|--------|----------|------------|
| Docker Compose | Single server, small teams | Low |
| Kubernetes | Scale, HA, enterprise | Medium-High |
| Manual | Full control, debugging | Medium |

## Docker Compose (Recommended)

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 1GB RAM minimum (2GB recommended)
- 10GB disk space

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/prdforge.git
cd prdforge

# Create environment file
cat > .env << 'EOF'
# Server configuration
PRDFORGE_PORT=8000
PRDFORGE_LOG_LEVEL=INFO

# AI API keys (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Projects directory (optional)
PRDFORGE_PROJECTS_DIR=/path/to/projects
EOF

# Start the server
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

### Production Configuration

**docker-compose.production.yml:**
```yaml
services:
  api:
    image: prdforge:latest
    container_name: prdforge-api
    ports:
      - "8000:8000"
    volumes:
      - prdforge-data:/app/data
      - /path/to/projects:/projects:ro
    environment:
      - PRDFORGE_DB_PATH=/app/data/prdforge.db
      - PRDFORGE_LOG_LEVEL=INFO
      - PRDFORGE_SECRET_KEY=${PRDFORGE_SECRET_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

volumes:
  prdforge-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/prdforge
```

**Start production:**
```bash
docker-compose -f docker-compose.production.yml up -d
```

### Reverse Proxy Setup (nginx)

```nginx
# /etc/nginx/sites-available/prdforge
upstream prdforge {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name prdforge.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name prdforge.example.com;

    ssl_certificate /etc/letsencrypt/live/prdforge.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/prdforge.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://prdforge;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # WebSocket support for real-time updates
    location /ws {
        proxy_pass http://prdforge;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### SSL with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d prdforge.example.com

# Test renewal
sudo certbot renew --dry-run
```

## Manual Installation

### Prerequisites

- Python 3.10+
- Git
- SQLite 3.35+

### Installation Steps

```bash
# Clone repository
git clone https://github.com/yourusername/prdforge.git
cd prdforge

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install with production dependencies
pip install -e ".[web]"

# Initialize database
prdforge db-init

# Create systemd service
sudo tee /etc/systemd/system/prdforge.service << 'EOF'
[Unit]
Description=PRDForge Server
After=network.target

[Service]
Type=simple
User=prdforge
Group=prdforge
WorkingDirectory=/opt/prdforge
Environment="PATH=/opt/prdforge/venv/bin"
Environment="PRDFORGE_DB_PATH=/var/lib/prdforge/prdforge.db"
Environment="PRDFORGE_LOG_LEVEL=INFO"
ExecStart=/opt/prdforge/venv/bin/python -m src.cli serve --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl enable prdforge
sudo systemctl start prdforge
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (for Claude executor) |
| `OPENAI_API_KEY` | OpenAI API key (for OpenAI executor) |

At least one AI provider API key is required.

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `PRDFORGE_PORT` | `8000` | Server port |
| `PRDFORGE_HOST` | `0.0.0.0` | Server host |
| `PRDFORGE_DB_PATH` | `~/.prdforge/prdforge.db` | Database path |
| `PRDFORGE_LOG_LEVEL` | `INFO` | Log level |
| `PRDFORGE_SECRET_KEY` | (generated) | Session encryption key |
| `PRDFORGE_WEBHOOK_SECRET` | (optional) | Webhook signing secret |
| `PRDFORGE_DEBUG` | `false` | Enable debug mode |

## Database Management

### Backup

```bash
# SQLite backup
sqlite3 /path/to/prdforge.db ".backup '/backup/prdforge-$(date +%Y%m%d).db'"

# With Docker
docker exec prdforge-api sqlite3 /app/data/prdforge.db ".backup '/app/data/backup.db'"
docker cp prdforge-api:/app/data/backup.db ./backup-$(date +%Y%m%d).db
```

### Restore

```bash
# Stop the server first
docker-compose stop api

# Restore backup
docker cp ./backup.db prdforge-api:/app/data/prdforge.db

# Start the server
docker-compose start api
```

### Migrations

Database migrations run automatically on startup. To run manually:

```bash
# With CLI
prdforge db-migrate

# Check version
prdforge db-version
```

## Monitoring

### Health Check

```bash
# API health endpoint
curl http://localhost:8000/api/health

# Response
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Logs

```bash
# Docker logs
docker-compose logs -f api --tail=100

# System logs (manual install)
journalctl -u prdforge -f

# Application logs
tail -f /var/log/prdforge/app.log
```

### Metrics

Enable metrics collection by setting:

```bash
PRDFORGE_METRICS_ENABLED=true
PRDFORGE_METRICS_PORT=9090
```

Then scrape Prometheus metrics from `/metrics`.

## Security

### Firewall

```bash
# UFW example
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### API Keys

Never commit API keys to version control. Use:
- Environment variables
- Docker secrets
- Vault/secret managers

### Database Security

```bash
# Set restrictive permissions
chmod 600 /path/to/prdforge.db
chown prdforge:prdforge /path/to/prdforge.db
```

### Network Security

- Always use HTTPS in production
- Use a reverse proxy (nginx, Caddy)
- Enable rate limiting
- Restrict CORS origins

## Scaling

### Horizontal Scaling

PRDForge uses SQLite, which limits horizontal scaling. For multi-instance deployments:

1. **Shared storage**: Mount the database on shared storage (NFS)
2. **Read replicas**: Use Litestream for SQLite replication
3. **PostgreSQL**: Migrate to PostgreSQL for full scaling (future feature)

### Performance Tuning

```bash
# Increase SQLite cache
PRDFORGE_DB_CACHE_SIZE=10000

# Increase worker processes (if using gunicorn)
WEB_CONCURRENCY=4
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs api

# Common issues:
# - Port already in use: Change PRDFORGE_PORT
# - Permission denied: Check volume permissions
# - Missing API key: Set ANTHROPIC_API_KEY or OPENAI_API_KEY
```

### Database locked

```bash
# Check for open connections
lsof /path/to/prdforge.db

# Force close
fuser -k /path/to/prdforge.db
```

### High memory usage

```bash
# Limit container memory
docker update --memory 2g prdforge-api

# Check memory usage
docker stats prdforge-api
```

### Connection timeouts

```bash
# Increase nginx timeouts
proxy_read_timeout 300s;
proxy_connect_timeout 75s;

# Increase server timeout
PRDFORGE_REQUEST_TIMEOUT=300
```

## Upgrading

### Docker

```bash
# Pull latest image
docker-compose pull

# Restart with new image
docker-compose up -d

# Verify
docker-compose ps
curl http://localhost:8000/api/health
```

### Manual

```bash
# Backup database
sqlite3 prdforge.db ".backup backup.db"

# Pull latest code
git pull origin main

# Update dependencies
pip install -e ".[web]"

# Restart service
sudo systemctl restart prdforge

# Verify
curl http://localhost:8000/api/health
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/prdforge/issues
- Documentation: https://docs.prdforge.io
