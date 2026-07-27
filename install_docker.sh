#!/bin/bash

# Install Docker and Docker Compose on Ubuntu/Debian

set -e

echo "🚀 Installing Docker and Docker Compose..."
echo "=========================================="

# Update package list
echo "📦 Updating package list..."
apt-get update

# Install prerequisites
echo "📦 Installing prerequisites..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
echo "🔑 Adding Docker GPG key..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo "📦 Setting up Docker repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package list again
echo "📦 Updating package list..."
apt-get update

# Install Docker Engine
echo "🐳 Installing Docker Engine..."
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Install Docker Compose (standalone)
echo "🐳 Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create symlink for docker compose (v2 style)
ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

# Start Docker service
echo "🚀 Starting Docker service..."
systemctl start docker
systemctl enable docker

# Verify installation
echo ""
echo "✅ Installation complete!"
echo ""
echo "📊 Versions installed:"
docker --version
docker-compose --version

echo ""
echo "✅ Docker is ready!"
echo ""
echo "🎯 Next step: Run ./deploy.sh"
