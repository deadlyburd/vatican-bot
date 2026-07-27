#!/bin/bash

# Vatican Ticket Bot - Automated Deployment Script
# This script deploys the complete system to a fresh server

set -e  # Exit on error

echo "🚀 Vatican Ticket Bot - Automated Deployment"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Step 1: Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    echo -e "${GREEN}✅ Docker installed${NC}"
else
    echo -e "${GREEN}✅ Docker already installed${NC}"
fi

echo ""
echo -e "${YELLOW}📋 Step 2: Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    apt-get update
    apt-get install -y docker-compose
    echo -e "${GREEN}✅ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✅ Docker Compose already installed${NC}"
fi

echo ""
echo -e "${YELLOW}📋 Step 3: Creating Docker volumes...${NC}"
docker volume create root_postgres_data 2>/dev/null || echo "Volume already exists"
docker volume create root_static_volume 2>/dev/null || echo "Volume already exists"
echo -e "${GREEN}✅ Docker volumes created${NC}"

echo ""
echo -e "${YELLOW}📋 Step 4: Checking configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found, copying from .env.example${NC}"
    cp .env.example .env
    echo -e "${RED}❗ IMPORTANT: Edit .env file and add your credentials:${NC}"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - SERVER_BASE_URL"
    echo "   - ALLOWED_HOSTS"
    echo ""
    read -p "Press Enter after editing .env file..."
fi

if [ ! -f "google_credentials.json" ]; then
    echo -e "${RED}❌ google_credentials.json not found!${NC}"
    echo "Please copy your Google service account JSON file to:"
    echo "  $(pwd)/google_credentials.json"
    echo ""
    read -p "Press Enter after copying the file..."
fi

echo -e "${GREEN}✅ Configuration files present${NC}"

echo ""
echo -e "${YELLOW}📋 Step 5: Building Docker images...${NC}"
docker-compose build
echo -e "${GREEN}✅ Docker images built${NC}"

echo ""
echo -e "${YELLOW}📋 Step 6: Starting services...${NC}"
docker-compose up -d
echo -e "${GREEN}✅ Services started${NC}"

echo ""
echo -e "${YELLOW}📋 Step 7: Waiting for services to be ready...${NC}"
sleep 10
echo -e "${GREEN}✅ Services ready${NC}"

echo ""
echo -e "${YELLOW}📋 Step 8: Running database migrations...${NC}"
docker-compose exec -T backend python /app/backend/manage.py migrate
echo -e "${GREEN}✅ Database migrated${NC}"

echo ""
echo -e "${YELLOW}📋 Step 9: Setting up Bokun integration...${NC}"
docker-compose exec -T backend python /app/backend/manage.py setup_bokun --sync-now
echo -e "${GREEN}✅ Bokun integration configured${NC}"

echo ""
echo -e "${YELLOW}📋 Step 10: Configuring firewall...${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp    # SSH
    ufw allow 80/tcp    # HTTP
    ufw allow 443/tcp   # HTTPS
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
docker-compose ps

echo ""
echo -e "${GREEN}✅ Next Steps:${NC}"
echo "1. Configure browser extension:"
echo "   - Backend URL: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "2. Check logs:"
echo "   docker-compose logs -f worker_vatican | grep 'Bokun\\|Sheets\\|Vatican'"
echo ""
echo "3. Test the system:"
echo "   docker-compose exec backend python /app/backend/manage.py setup_bokun --test-only"
echo ""
echo "4. View Google Sheet:"
echo "   https://docs.google.com/spreadsheets/d/1MLEb4tKzCF3KWsgUiHGyqn-GaMgPIN0scEAWxFQvJT0/edit"
echo ""
echo -e "${YELLOW}📚 Documentation:${NC}"
echo "   - README.md - Overview"
echo "   - COMPLETE_SETUP_GUIDE.md - Detailed guide"
echo "   - BOKUN_SHEETS_SETUP.md - Bokun integration"
echo ""
echo -e "${GREEN}🚀 Your Vatican Ticket Bot is now running 24/7!${NC}"
