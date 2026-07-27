#!/bin/bash
# Docker Cleanup Script - Automated Memory Management
# Run this script periodically to prevent Docker memory issues

echo "🧹 Docker Cleanup Script Started"
echo "=================================="
echo ""

# 1. Show current usage
echo "📊 Current Docker Usage:"
docker system df
echo ""

# 2. Clean up stopped containers
echo "🗑️  Removing stopped containers..."
docker container prune -f
echo ""

# 3. Clean up unused images
echo "🖼️  Removing unused images..."
docker image prune -a -f --filter "until=24h"
echo ""

# 4. Clean up build cache
echo "🏗️  Removing build cache..."
docker builder prune -f --filter "until=24h"
echo ""

# 5. Clean up unused volumes (CAREFUL - only removes truly unused)
echo "💾 Removing unused volumes..."
docker volume prune -f
echo ""

# 6. Clean up unused networks
echo "🌐 Removing unused networks..."
docker network prune -f
echo ""

# 7. Show final usage
echo "✅ Cleanup Complete!"
echo "📊 Final Docker Usage:"
docker system df
echo ""

# 8. Show memory stats
echo "💾 Container Memory Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
echo ""

echo "🎉 Docker cleanup finished successfully!"
