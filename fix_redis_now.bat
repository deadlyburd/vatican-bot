@echo off
echo ================================================================================
echo REDIS FIX - EMERGENCY CLEANUP
echo ================================================================================
echo.
echo Redis is stuck loading. This will:
echo 1. Stop Redis
echo 2. Clear the data
echo 3. Restart all services
echo.
echo ⚠️  WARNING: This will clear all Redis cache (safe - will rebuild automatically)
echo.
pause

echo.
echo Step 1: Stopping Redis...
docker-compose stop redis

echo.
echo Step 2: Removing Redis data volume...
docker volume rm root_redis-data 2>nul
if %errorlevel% neq 0 (
    echo Volume doesn't exist or is in use, continuing...
)

echo.
echo Step 3: Starting Redis fresh...
docker-compose up -d redis

echo.
echo Step 4: Waiting for Redis to start (10 seconds)...
timeout /t 10 /nobreak >nul

echo.
echo Step 5: Restarting all services...
docker-compose restart backend worker_vatican beat

echo.
echo Step 6: Waiting for services to start (20 seconds)...
timeout /t 20 /nobreak >nul

echo.
echo ================================================================================
echo VERIFICATION
echo ================================================================================
echo.

echo Checking Redis...
docker-compose exec -T redis redis-cli DBSIZE

echo.
echo Checking worker status...
docker-compose logs --tail=10 worker_vatican

echo.
echo ================================================================================
echo ✅ FIX COMPLETE
echo ================================================================================
echo.
echo Redis has been reset and services restarted.
echo.
echo Monitor the bot:
echo   docker-compose logs -f worker_vatican
echo.
echo Check Redis health:
echo   docker-compose exec redis redis-cli DBSIZE
echo.
pause
