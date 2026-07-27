#!/bin/bash
# Create Hetzner Deployment Package
# This script creates a clean deployment folder with everything needed for Hetzner

echo "📦 Creating Hetzner deployment package..."

# Create deployment directory
DEPLOY_DIR="hetzner-deployment"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

echo "📁 Copying essential files..."

# Copy backend
cp -r backend $DEPLOY_DIR/
echo "  ✅ Backend copied"

# Copy worker
cp -r worker_vatican $DEPLOY_DIR/
echo "  ✅ Worker copied"

# Copy Playwright bot (if exists, otherwise create placeholder)
if [ -d "playwright_bot" ]; then
    cp -r playwright_bot $DEPLOY_DIR/
else
    mkdir -p $DEPLOY_DIR/playwright_bot
    echo "  ⚠️  Playwright bot not found, created placeholder"
fi
echo "  ✅ Playwright bot ready"

# Copy Docker files
cp docker-compose.yml $DEPLOY_DIR/
cp .dockerignore $DEPLOY_DIR/ 2>/dev/null || true
echo "  ✅ Docker files copied"

# Copy environment file
if [ -f ".env" ]; then
    cp .env $DEPLOY_DIR/.env.example
    echo "  ✅ Environment file copied (as .env.example)"
else
    echo "  ⚠️  No .env file found"
fi

# Copy nginx config (if exists)
if [ -d "nginx" ]; then
    cp -r nginx $DEPLOY_DIR/
    echo "  ✅ Nginx config copied"
fi

# Copy requirements
cp requirements.txt $DEPLOY_DIR/ 2>/dev/null || true

# Create deployment script
cat > $DEPLOY_DIR/deploy.sh << 'EOF'
#!/bin/bash
# Hetzner Deployment Script

echo "🚀 Deploying Vatican Bot to Hetzner..."

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "   Copy .env.example to .env and configure it"
    exit 1
fi

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 15

# Run migrations
echo "📊 Running database migrations..."
docker-compose exec -T backend python /app/backend/manage.py migrate

# Collect static files
echo "📁 Collecting static files..."
docker-compose exec -T backend python /app/backend/manage.py collectstatic --noinput

# Check status
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Access points:"
echo "   Backend API: http://YOUR_SERVER_IP:8000"
echo "   Frontend: http://YOUR_SERVER_IP:3000"
echo ""
echo "📝 Next steps:"
echo "   1. Create superuser: docker-compose exec backend python /app/backend/manage.py createsuperuser"
echo "   2. Create monitoring task: docker-compose exec backend python /app/create_real_monitoring_task.py"
echo "   3. Check logs: docker-compose logs -f"
EOF

chmod +x $DEPLOY_DIR/deploy.sh
echo "  ✅ Deployment script created"

# Create README
cat > $DEPLOY_DIR/README.md << 'EOF'
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
EOF

echo "  ✅ README created"

# Create .gitignore for deployment folder
cat > $DEPLOY_DIR/.gitignore << 'EOF'
.env
*.pyc
__pycache__/
*.log
screenshots/
*.sqlite3
.DS_Store
EOF

echo "  ✅ .gitignore created"

# Create archive
echo ""
echo "📦 Creating archive..."
tar -czf vatican-bot-hetzner.tar.gz -C $DEPLOY_DIR .

echo ""
echo "=" * 80
echo "✅ Hetzner deployment package created!"
echo "=" * 80
echo ""
echo "📁 Deployment folder: $DEPLOY_DIR/"
echo "📦 Archive: vatican-bot-hetzner.tar.gz"
echo ""
echo "🚀 To deploy to Hetzner:"
echo "   1. scp vatican-bot-hetzner.tar.gz root@YOUR_SERVER_IP:/root/"
echo "   2. ssh root@YOUR_SERVER_IP"
echo "   3. mkdir vatican-bot && cd vatican-bot"
echo "   4. tar -xzf ../vatican-bot-hetzner.tar.gz"
echo "   5. cp .env.example .env && nano .env"
echo "   6. ./deploy.sh"
echo ""
echo "📚 See HETZNER_DEPLOYMENT_COMPLETE.md for full guide"
echo ""
