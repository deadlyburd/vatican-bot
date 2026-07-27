#!/bin/bash
# Redis Bloat Fix - Complete Automation
# ======================================
# This script runs the complete fix process

echo "================================================================================"
echo "REDIS BLOAT FIX - PERMANENT SOLUTION"
echo "================================================================================"
echo ""

# Step 1: Clean up Redis
echo "STEP 1: Cleaning up Redis bloat..."
echo "--------------------------------------------------------------------------------"
docker-compose exec -T backend python fix_redis_bloat.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Redis cleanup failed!"
    echo "   Make sure Docker containers are running: docker-compose ps"
    exit 1
fi

echo ""
echo "✅ Redis cleanup completed!"
echo ""

# Step 2: Restart services
echo "STEP 2: Restarting services to apply new settings..."
echo "--------------------------------------------------------------------------------"
docker-compose restart backend worker_vatican beat redis

echo ""
echo "⏳ Waiting for services to start (30 seconds)..."
sleep 30

# Step 3: Verify fix
echo ""
echo "STEP 3: Verifying fix..."
echo "--------------------------------------------------------------------------------"

echo ""
echo "Redis key count:"
docker-compose exec -T redis redis-cli DBSIZE

echo ""
echo "Redis memory usage:"
docker-compose exec -T redis redis-cli INFO memory | grep used_memory_human

echo ""
echo "Worker status (last 10 lines):"
docker-compose logs --tail=10 worker_vatican

echo ""
echo "================================================================================"
echo "✅ FIX COMPLETED!"
echo "================================================================================"
echo ""
echo "Expected results:"
echo "  - Redis keys: < 10,000 (was 220,000+)"
echo "  - Redis memory: < 100MB (was 1.7GB)"
echo "  - Workers: Connected and running"
echo ""
echo "Monitor the bot:"
echo "  docker-compose logs -f worker_vatican | grep ORCHESTRATOR"
echo ""
echo "Check Redis health anytime:"
echo "  docker-compose exec redis redis-cli DBSIZE"
echo "  docker-compose exec redis redis-cli INFO memory | grep used_memory_human"
echo ""
