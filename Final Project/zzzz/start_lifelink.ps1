# LifeLink System - Quick Start (PowerShell)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LifeLink System - Quick Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Redis is running
Write-Host "[1/4] Checking Redis..." -ForegroundColor Yellow
try {
    $redisCheck = redis-cli ping 2>$null
    if ($redisCheck -eq "PONG") {
        Write-Host "   Redis is running ✓" -ForegroundColor Green
    } else {
        throw "Redis not responding"
    }
} catch {
    Write-Host "   Redis not running. Please start Redis manually:" -ForegroundColor Red
    Write-Host "   redis-server" -ForegroundColor Yellow
    Write-Host "   Or use WSL: wsl sudo service redis-server start" -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}

# Start Celery Worker
Write-Host "[2/4] Starting Celery Worker..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; celery -A celery_app worker --loglevel=info --pool=solo"
Start-Sleep -Seconds 3

# Start Celery Beat
Write-Host "[3/4] Starting Celery Beat..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; celery -A celery_app beat --loglevel=info"
Start-Sleep -Seconds 3

# Start Flask App
Write-Host "[4/4] Starting Flask Application..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  All services starting..." -ForegroundColor Cyan
Write-Host "  Flask will be available at:" -ForegroundColor Cyan
Write-Host "  http://localhost:5001" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host ""

Set-Location $PSScriptRoot
python app.py

