@echo off
REM Setup 60-Day Vatican Monitoring for All Agencies (Production Database)
REM This script runs inside the Docker backend container to access the production database

echo Running 60-day monitoring setup in production...
docker-compose exec backend python /app/setup_60_day_monitoring.py %*
