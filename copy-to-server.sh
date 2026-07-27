#!/bin/bash

# Copy Vatican Bot to Server
# Usage: ./copy-to-server.sh YOUR_SERVER_IP

if [ -z "$1" ]; then
    echo "❌ Error: Please provide server IP address"
    echo "Usage: ./copy-to-server.sh YOUR_SERVER_IP"
    echo "Example: ./copy-to-server.sh 151.25.69.162"
    exit 1
fi

SERVER_IP=$1

echo "🚀 Copying Vatican Bot to server: $SERVER_IP"
echo "=============================================="
echo ""

echo "📦 Copying configuration files..."
scp docker-compose.server.yml root@$SERVER_IP:/root/vatican-bot/
scp deploy-server-only.sh root@$SERVER_IP:/root/vatican-bot/
scp .env root@$SERVER_IP:/root/vatican-bot/
scp google_credentials.json root@$SERVER_IP:/root/vatican-bot/
scp Dockerfile root@$SERVER_IP:/root/vatican-bot/

echo ""
echo "📦 Copying backend folder..."
scp -r backend root@$SERVER_IP:/root/vatican-bot/

echo ""
echo "📦 Copying worker_vatican folder..."
scp -r worker_vatican root@$SERVER_IP:/root/vatican-bot/

echo ""
echo "✅ All files copied!"
echo ""
echo "🎯 Next steps:"
echo "1. SSH to server: ssh root@$SERVER_IP"
echo "2. Go to directory: cd /root/vatican-bot"
echo "3. Deploy: chmod +x deploy-server-only.sh && sudo ./deploy-server-only.sh"
