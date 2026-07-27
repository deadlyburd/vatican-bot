# Docker Cleanup Script - Windows PowerShell Version
# Run this script periodically to prevent Docker memory issues

Write-Host "🧹 Docker Cleanup Script Started" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# 1. Show current usage
Write-Host "📊 Current Docker Usage:" -ForegroundColor Yellow
docker system df
Write-Host ""

# 2. Clean up stopped containers
Write-Host "🗑️  Removing stopped containers..." -ForegroundColor Yellow
docker container prune -f
Write-Host ""

# 3. Clean up unused images
Write-Host "🖼️  Removing unused images..." -ForegroundColor Yellow
docker image prune -a -f --filter "until=24h"
Write-Host ""

# 4. Clean up build cache
Write-Host "🏗️  Removing build cache..." -ForegroundColor Yellow
docker builder prune -f --filter "until=24h"
Write-Host ""

# 5. Clean up unused volumes (CAREFUL - only removes truly unused)
Write-Host "💾 Removing unused volumes..." -ForegroundColor Yellow
docker volume prune -f
Write-Host ""

# 6. Clean up unused networks
Write-Host "🌐 Removing unused networks..." -ForegroundColor Yellow
docker network prune -f
Write-Host ""

# 7. Show final usage
Write-Host "✅ Cleanup Complete!" -ForegroundColor Green
Write-Host "📊 Final Docker Usage:" -ForegroundColor Yellow
docker system df
Write-Host ""

# 8. Show memory stats
Write-Host "💾 Container Memory Usage:" -ForegroundColor Yellow
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
Write-Host ""

Write-Host "🎉 Docker cleanup finished successfully!" -ForegroundColor Green
