#!/bin/bash

# Vatican Bot - Complete Deployment Script
# Copies files to server and sets up monitoring

set -e

SERVER="root@178.105.157.86"
SSH_KEY="hetzner_key"
REMOTE_DIR="/root/vatican-bot"

echo "🚀 Vatican Bot - Complete Deployment"
echo "======================================"

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found: $SSH_KEY"
    exit 1
fi

# Check if google_credentials.json exists
if [ ! -f "google_credentials.json" ]; then
    echo "❌ google_credentials.json not found"
    exit 1
fi

echo ""
echo "1️⃣ Copying files to server..."
./copy-to-server.sh

echo ""
echo "2️⃣ Setting up services on server..."
ssh -i "$SSH_KEY" "$SERVER" << 'ENDSSH'
cd /root/vatican-bot

echo "   📦 Pulling latest images..."
docker-compose -f docker-compose.server.yml pull

echo "   🔨 Building backend..."
docker-compose -f docker-compose.server.yml build backend

echo "   🚀 Starting services..."
docker-compose -f docker-compose.server.yml up -d

echo "   ⏳ Waiting for services to start..."
sleep 10

echo "   🔍 Checking service status..."
docker-compose -f docker-compose.server.yml ps

echo "   ✅ Services started!"
ENDSSH

echo ""
echo "3️⃣ Creating monitoring tasks from Google Sheets..."
ssh -i "$SSH_KEY" "$SERVER" << 'ENDSSH'
cd /root/vatican-bot

echo "   📊 Reading Google Sheets and creating tasks..."
docker-compose -f docker-compose.server.yml exec -T backend python /app/create_tasks_from_sheets.py

echo "   ✅ Tasks created!"
ENDSSH

echo ""
echo "4️⃣ Checking logs..."
ssh -i "$SSH_KEY" "$SERVER" << 'ENDSSH'
cd /root/vatican-bot

echo "   📋 Recent logs:"
docker-compose -f docker-compose.server.yml logs --tail=20

echo ""
echo "   🔍 Service health:"
docker-compose -f docker-compose.server.yml ps
ENDSSH

echo ""
echo "======================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "======================================"
echo ""
echo "📊 What's Running:"
echo "   • PostgreSQL database"
echo "   • Redis cache"
echo "   • Django backend API"
echo "   • Celery worker (Vatican monitoring)"
echo "   • Celery beat (task scheduler)"
echo "   • Telegram bot"
echo ""
echo "🔍 Monitor Logs:"
echo "   ssh -i $SSH_KEY $SERVER"
echo "   cd $REMOTE_DIR"
echo "   docker-compose -f docker-compose.server.yml logs -f worker_vatican"
echo ""
echo "📱 Telegram Notifications:"
echo "   You'll receive notifications when slots become available"
echo ""
echo "🛠️ Useful Commands:"
echo "   # Check task status"
echo "   docker-compose -f docker-compose.server.yml exec backend python manage.py shell"
echo ""
echo "   # Restart services"
echo "   docker-compose -f docker-compose.server.yml restart"
echo ""
echo "   # Stop services"
echo "   docker-compose -f docker-compose.server.yml down"
echo ""
echo "======================================"
