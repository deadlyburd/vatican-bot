#!/bin/bash

# Vatican Ticket Bot - Server-Only Deployment
# No frontend, no nginx - just monitoring and API

set -e

echo "🚀 Vatican Bot - Server-Only Deployment"
echo "========================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Step 1: Checking configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file with your credentials"
    exit 1
fi

if [ ! -f "google_credentials.json" ]; then
    echo -e "${RED}❌ google_credentials.json not found!${NC}"
    echo "Please copy your Google service account JSON file"
    exit 1
fi

echo -e "${GREEN}✅ Configuration files present${NC}"

echo ""
echo -e "${YELLOW}📋 Step 2: Creating Docker volumes...${NC}"
docker volume create postgres_data 2>/dev/null || echo "Volume already exists"
docker volume create static_volume 2>/dev/null || echo "Volume already exists"
echo -e "${GREEN}✅ Docker volumes created${NC}"

echo ""
echo -e "${YELLOW}📋 Step 3: Building Docker images...${NC}"
docker-compose -f docker-compose.server.yml build
echo -e "${GREEN}✅ Docker images built${NC}"

echo ""
echo -e "${YELLOW}📋 Step 4: Starting services...${NC}"
docker-compose -f docker-compose.server.yml up -d
echo -e "${GREEN}✅ Services started${NC}"

echo ""
echo -e "${YELLOW}📋 Step 5: Waiting for services to be ready...${NC}"
echo "Waiting for database to be ready..."
sleep 20

# Wait for backend to be healthy
echo "Waiting for backend to be ready..."
for i in {1..30}; do
    if docker-compose -f docker-compose.server.yml ps backend | grep -q "Up"; then
        echo "Backend is ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

echo -e "${GREEN}✅ Services ready${NC}"

echo ""
echo -e "${YELLOW}📋 Step 6: Running database migrations...${NC}"
# Try multiple times if container is restarting
for i in {1..5}; do
    echo "Attempt $i/5..."
    if docker-compose -f docker-compose.server.yml exec -T backend python /app/backend/manage.py migrate 2>/dev/null; then
        echo -e "${GREEN}✅ Database migrated${NC}"
        break
    else
        echo "Backend not ready yet, waiting..."
        sleep 10
    fi
done

echo ""
echo -e "${YELLOW}📋 Step 7: Setting up Bokun integration...${NC}"
docker-compose -f docker-compose.server.yml exec -T backend python -c "
import sys
sys.path.insert(0, '/app/backend')
from backend.services.bokun_api import get_bokun_api
from backend.services.bokun_sheets_sync import get_bokun_sync

print('Testing Bokun API...')
api = get_bokun_api()
if api.test_connection():
    print('✅ Bokun API connected')
else:
    print('❌ Bokun API connection failed')

print('Testing Google Sheets...')
try:
    sync = get_bokun_sync()
    print('✅ Google Sheets connected')
except Exception as e:
    print(f'❌ Google Sheets connection failed: {e}')
"
echo -e "${GREEN}✅ Integration tested${NC}"

echo ""
echo -e "${YELLOW}📋 Step 8: Configuring firewall...${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp    # SSH
    ufw allow 8000/tcp  # Backend API
    ufw --force enable
    echo -e "${GREEN}✅ Firewall configured${NC}"
else
    echo -e "${YELLOW}⚠️  UFW not found, skipping firewall configuration${NC}"
fi

echo ""
echo -e "${GREEN}=============================================="
echo "🎉 Deployment Complete!"
echo "==============================================\n${NC}"

echo "📊 Service Status:"
docker-compose -f docker-compose.server.yml ps

echo ""
echo -e "${GREEN}✅ Running Services:${NC}"
echo "   • PostgreSQL Database"
echo "   • Redis Cache"
echo "   • Backend API (port 8000)"
echo "   • Vatican Monitor Worker"
echo "   • Celery Beat Scheduler"
echo "   • Telegram Bot"
echo ""
echo -e "${GREEN}✅ What's Running:${NC}"
echo "   1. Server monitors Vatican API every 5 minutes"
echo "   2. Server syncs Bokun bookings to Google Sheets"
echo "   3. Server sends Telegram notifications when slots found"
echo "   4. Browser extension (on your local machine) handles booking"
echo ""
echo -e "${GREEN}✅ Next Steps:${NC}"
echo "1. Test Bokun connection:"
echo "   docker-compose -f docker-compose.server.yml exec backend python /app/backend/services/bokun_api.py"
echo ""
echo "2. Test Google Sheets:"
echo "   docker-compose -f docker-compose.server.yml exec backend python /app/backend/services/bokun_sheets_sync.py"
echo ""
echo "3. Check logs:"
echo "   docker-compose -f docker-compose.server.yml logs -f worker_vatican | grep 'Bokun\\|Sheets\\|Vatican'"
echo ""
echo "4. View Google Sheet:"
echo "   https://docs.google.com/spreadsheets/d/1MLEb4tKzCF3KWsgUiHGyqn-GaMgPIN0scEAWxFQvJT0/edit"
echo ""
echo "5. Configure browser extension on your LOCAL machine:"
echo "   - Backend URL: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo -e "${GREEN}🚀 Your Vatican Ticket Bot is now running 24/7!${NC}"
