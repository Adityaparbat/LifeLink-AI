# 🚀 Starting LifeLink in PowerShell

## Quick Start (PowerShell)

Since you're using PowerShell, use one of these methods:

### Method 1: PowerShell Script (Recommended)

```powershell
cd "Final Project\zzzz"
.\start_lifelink.ps1
```

**Note:** If you get an execution policy error, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Method 2: Batch File (with .\ prefix)

```powershell
cd "Final Project\zzzz"
.\start_lifelink.bat
```

### Method 3: Manual Start (4 PowerShell Windows)

Open 4 separate PowerShell windows:

**Window 1 - Redis:**
```powershell
redis-server
```

**Window 2 - Celery Worker:**
```powershell
cd "Final Project\zzzz"
celery -A celery_app worker --loglevel=info --pool=solo
```

**Window 3 - Celery Beat:**
```powershell
cd "Final Project\zzzz"
celery -A celery_app beat --loglevel=info
```

**Window 4 - Flask App:**
```powershell
cd "Final Project\zzzz"
python app.py
```

---

## If Redis is Not Installed

### Option 1: Install Redis for Windows
Download from: https://github.com/microsoftarchive/redis/releases

### Option 2: Use WSL (Windows Subsystem for Linux)
```powershell
wsl
sudo apt-get update
sudo apt-get install redis-server
sudo service redis-server start
```

### Option 3: Use Docker (if Docker Desktop is installed)
```powershell
docker run -d -p 6379:6379 redis:latest
```

---

## Verify Everything is Running

After starting all services, check:

1. **Redis:** Open new PowerShell, run `redis-cli ping` → Should return `PONG`

2. **Flask:** Open browser → http://localhost:5001 → Should see landing page

3. **Celery Worker:** Check Window 2 → Should see "celery@hostname ready"

4. **Celery Beat:** Check Window 3 → Should see "beat: Starting..."

---

## Troubleshooting

### Execution Policy Error
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Port 5001 Already in Use
```powershell
# Find process
netstat -ano | findstr :5001

# Kill process (replace <PID> with actual process ID)
Stop-Process -Id <PID> -Force
```

### Redis Connection Error
- Make sure Redis is running: `redis-cli ping`
- Check REDIS_URL in `.env` file
- Default should be: `redis://localhost:6379/0`

---

## Next Steps

Once all services are running:

1. Open browser: http://localhost:5001
2. Login as admin: http://localhost:5001/admin/login
3. Click "AI Assistant" to access LifeBot
4. Test all 4 LifeBot tasks

---

**That's it! Your system should be running now.** 🎉

