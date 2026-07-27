# Vatican Bot - Hetzner Deployment

## Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
nano .env
```

### 2. Deploy
```bash
./deploy.sh
```

### 3. Create Monitoring Task
```bash
docker-compose exec backend python /app/create_real_monitoring_task.py
```

### 4. Monitor
```bash
docker-compose logs -f
```

## Services

- **Backend:** Django API (Port 8000)
- **Worker:** Celery worker for Vatican monitoring
- **Playwright Bot:** Headless booking automation
- **Database:** PostgreSQL
- **Redis:** Message broker
- **Nginx:** Reverse proxy (Port 80/443)

## Useful Commands

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs -f [service_name]

# Restart service
docker-compose restart [service_name]

# Stop all
docker-compose down

# Rebuild
docker-compose build --no-cache
```

## Troubleshooting

### Services not starting
```bash
docker-compose logs [service_name]
```

### Database issues
```bash
docker-compose exec backend python /app/backend/manage.py migrate
```

### Playwright issues
```bash
docker-compose logs playwright_bot
docker-compose restart playwright_bot
```
