# ⚡ Quick Start Guide - LifeLink System

## 🎯 Fastest Way to Run Everything

### Step 1: Verify Setup (One-Time)

```bash
cd "Final Project/zzzz"
python verify_setup.py
```

This checks:
- ✓ Python version
- ✓ MongoDB connection
- ✓ Redis connection
- ✓ Required packages
- ✓ Environment variables

**Fix any issues before proceeding!**

---

### Step 2: Start All Services

#### Option A: Quick Start Script (Recommended)

**Windows:**
```bash
cd "Final Project/zzzz"
.\start_lifelink.bat
```

**Or in PowerShell:**
```powershell
cd "Final Project\zzzz"
.\start_lifelink.bat
```

**Linux/Mac:**
```bash
cd "Final Project/zzzz"
chmod +x start_lifelink.sh
./start_lifelink.sh
```

This automatically starts:
1. Redis (if not running)
2. Celery Worker
3. Celery Beat
4. Flask App

#### Option B: Manual Start (4 Terminals)

**Terminal 1 - Redis:**
```bash
redis-server
```

**Terminal 2 - Celery Worker:**
```bash
cd "Final Project/zzzz"
celery -A celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 - Celery Beat:**
```bash
cd "Final Project/zzzz"
celery -A celery_app beat --loglevel=info
```

**Terminal 4 - Flask App:**
```bash
cd "Final Project/zzzz"
python app.py
```

---

### Step 3: Access the Application

Open your browser:
```
http://localhost:5001
```

---

### Step 4: Test LifeBot (Admin Dashboard)

1. **Login as Admin:**
   - Go to: http://localhost:5001/admin/login
   - Email: `admin@blooddonation.com`
   - Password: `admin123`
   - (Or create your own admin account)

2. **Access LifeBot:**
   - Click **"AI Assistant"** in navigation
   - You should see the LifeBot interface

3. **Test Tasks:**
   - **Hospital Stock**: Select blood group → Click "Run inventory scan"
   - **Accepted Donors**: Select request ID → Click "Fetch accepted donors"
   - **Successful Donations**: Set limit → Click "Load timeline"
   - **Handle Emergency**: Fill form → Click "Trigger emergency workflow"

---

### Step 5: Verify Agents Are Running

**Check Celery Worker Terminal:**
You should see every 3 minutes:
```
[timestamp] Task agents.autopulse_agent.monitor_inventory[...] received
[timestamp] Found X active hospitals to monitor
```

**Check Celery Beat Terminal:**
You should see:
```
[timestamp] Scheduler: Sending due task autopulse-inventory-check
```

---

## ✅ Success Indicators

### Flask App Running:
```
✓ Agentic AI routes registered
 * Running on http://127.0.0.1:5001
```

### Celery Worker Running:
```
celery@hostname ready.
```

### Celery Beat Running:
```
beat: Starting...
```

### LifeBot Working:
- Interface loads without errors
- Queries return responses
- Explanations appear in "Explainable Response" section

---

## 🐛 Common Issues & Quick Fixes

### Redis Not Running
```bash
# Windows (WSL)
wsl
sudo service redis-server start

# Or download Redis for Windows
# https://github.com/microsoftarchive/redis/releases
```

### Port 5001 Already in Use
```bash
# Find and kill process
# Windows:
netstat -ano | findstr :5001
taskkill /PID <PID> /F

# Mac/Linux:
lsof -i :5001
kill -9 <PID>
```

### MongoDB Connection Error
- Check `.env` file has correct `MONGODB_URI`
- Verify MongoDB is accessible
- Test: `python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGODB_URI')); print(client.admin.command('ping'))"`

### Celery Worker Import Errors
```bash
# Make sure you're in the correct directory
cd "Final Project/zzzz"

# Reinstall packages
pip install -r requirements.txt
```

---

## 📊 What You Should See

### Terminal Outputs:

**Flask:**
```
Successfully connected to MongoDB
Database indexes created successfully
✓ Agentic AI routes registered
 * Running on http://127.0.0.1:5001
```

**Celery Worker:**
```
celery@LAPTOP-XXXXX ready.
[timestamp] Task agents.autopulse_agent.monitor_inventory[...] received
```

**Celery Beat:**
```
beat: Starting...
[timestamp] Scheduler: Sending due task autopulse-inventory-check
```

### Browser:

**Landing Page:**
- LifeLink logo
- Navigation menu
- Sign up / Login buttons

**Admin Dashboard:**
- Blood Availability section
- AI Assistant (LifeBot) section
- Notifications
- Statistics

**LifeBot Interface:**
- Mission Control cards
- Quick Scripts
- Task forms (4 tabs)
- Explainable Response area

---

## 🧪 Quick Test Commands

### Test MongoDB:
```python
python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGODB_URI')); print('MongoDB:', client.admin.command('ping'))"
```

### Test Redis:
```bash
redis-cli ping
# Should return: PONG
```

### Test ADK Agents:
```python
python
>>> from adk_integration import adk_lifebot
>>> print("ADK agents loaded successfully")
```

### Test MCP Tools:
```python
python
>>> from mcp_tools import MongoDBMCPTools
>>> print("MCP tools loaded successfully")
```

---

## 📝 Next Steps After Running

1. **Create Test Data:**
   - Create admin account (or use default)
   - Create donor accounts
   - Add blood inventory

2. **Test Each Agent:**
   - AutoPulse: Wait 3 minutes, check Celery logs
   - RapidAid: Trigger emergency via LifeBot
   - PathFinder: Accept a donation request
   - LinkBridge: Check nearby hospitals

3. **Run Evaluations:**
   ```bash
   python agent_evaluation.py
   ```

4. **Check Observability:**
   ```python
   from observability import observability
   metrics = observability.get_metrics_summary()
   print(metrics)
   ```

---

## 🎉 You're All Set!

Once you see:
- ✓ Flask running on port 5001
- ✓ Celery Worker ready
- ✓ Celery Beat scheduling tasks
- ✓ LifeBot interface accessible

**Your system is fully operational!**

For detailed documentation, see `RUN_PROJECT_GUIDE.md`

