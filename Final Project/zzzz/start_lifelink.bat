@echo off
echo ========================================
echo   LifeLink System - Quick Start
echo ========================================
echo.

REM Check if Redis is running
echo [1/4] Checking Redis...
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo    Redis not running. Starting Redis...
    start "Redis Server" cmd /k "redis-server"
    timeout /t 3
) else (
    echo    Redis is running ✓
)

REM Start Celery Worker
echo [2/4] Starting Celery Worker...
start "Celery Worker" cmd /k "cd /d %~dp0 && celery -A celery_app worker --loglevel=info --pool=solo"
timeout /t 3

REM Start Celery Beat
echo [3/4] Starting Celery Beat...
start "Celery Beat" cmd /k "cd /d %~dp0 && celery -A celery_app beat --loglevel=info"
timeout /t 3

REM Start Flask App
echo [4/4] Starting Flask Application...
echo.
echo ========================================
echo   All services starting...
echo   Flask will be available at:
echo   http://localhost:5001
echo ========================================
echo.
echo Press Ctrl+C to stop all services
echo.

cd /d %~dp0
python app.py

