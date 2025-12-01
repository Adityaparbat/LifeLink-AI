#!/bin/bash

echo "========================================"
echo "  LifeLink System - Quick Start"
echo "========================================"
echo ""

# Check if Redis is running
echo "[1/4] Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "   Redis not running. Starting Redis..."
    redis-server &
    sleep 3
else
    echo "   Redis is running ✓"
fi

# Start Celery Worker
echo "[2/4] Starting Celery Worker..."
cd "$(dirname "$0")"
celery -A celery_app worker --loglevel=info &
sleep 3

# Start Celery Beat
echo "[3/4] Starting Celery Beat..."
celery -A celery_app beat --loglevel=info &
sleep 3

# Start Flask App
echo "[4/4] Starting Flask Application..."
echo ""
echo "========================================"
echo "  All services starting..."
echo "  Flask will be available at:"
echo "  http://localhost:5001"
echo "========================================"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

python app.py

