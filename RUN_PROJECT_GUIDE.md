# 🚀 Complete Guide to Run LifeLink Project

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Python 3.8+ installed
- [ ] MongoDB connection string (or local MongoDB)
- [ ] Redis installed and running
- [ ] Google API Key (for Gemini AI)
- [ ] Environment variables configured

---

## Step 1: Install Dependencies

```bash
# Navigate to project directory
cd "Final Project/zzzz"

# Install Python packages
pip install -r requirements.txt
```

**Key dependencies:**
- Flask
- pymongo
- celery
- redis
- google-generativeai
- twilio
- requests
- geopy

---

## Step 2: Configure Environment Variables

Create/update `.env` file in `Final Project/zzzz/`:

```env
# MongoDB (REQUIRED)
MONGODB_URI=mongodb+srv://your_connection_string

# Redis (REQUIRED)
REDIS_URL=redis://localhost:6379/0

# Google Gemini AI (REQUIRED for LifeBot)
GOOGLE_API_KEY=your_gemini_api_key
LIFEBOT_MODEL=gemini-1.5-flash

# Twilio (Optional - for voice calls)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
CALLBACK_BASE_URL=http://localhost:5001

# Fast2SMS (Optional - for SMS)
FAST2SMS_API_KEY=your_fast2sms_key

# Google Maps (Optional - for route planning)
GOOGLE_MAPS_API_KEY=your_google_maps_key

# OpenRouteService (Optional - route fallback)
OPENROUTE_API_KEY=your_openroute_key

# News API (Optional - for emergency detection)
NEWS_API_KEY=your_news_api_key

# Database name
MONGO_DB=blood_donation
```

---

## Step 3: Start Redis Server

**Windows:**
```bash
# Option 1: If Redis is installed
redis-server

# Option 2: Using WSL
wsl
sudo service redis-server start

# Option 3: Download from:
# https://github.com/microsoftarchive/redis/releases

# Option 4: Use Docker (if available)
docker run -d -p 6379:6379 redis:latest
```

**Linux/Mac:**
```bash
# Linux
sudo systemctl start redis
# or
redis-server

# Mac
brew services start redis
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

---

## Step 4: Start All Services

You need **4 separate terminal windows**:

### Terminal 1: Redis (if not running as service)
```bash
redis-server
```
**Expected output:**
```
[timestamp] * Ready to accept connections
```

### Terminal 2: Celery Worker
```bash
cd "Final Project/zzzz"
celery -A celery_app worker --loglevel=info --pool=solo
```

**Expected output:**
```
[timestamp] celery@LAPTOP-XXXXX ready.
[timestamp] mingle: searching for neighbors
[timestamp] mingle: all alone
```

**✅ Success indicators:**
- "celery@hostname ready"
- No import errors
- Agents loaded successfully

### Terminal 3: Celery Beat (Scheduler)
```bash
cd "Final Project/zzzz"
celery -A celery_app beat --loglevel=info
```

**Expected output:**
```
[timestamp] beat: Starting...
[timestamp] DatabaseScheduler: Schedule changed.
[timestamp] Scheduler: Sending due task autopulse-inventory-check
```

**✅ Success indicators:**
- "beat: Starting..."
- Tasks scheduled (autopulse-inventory-check, rapidaid-check-emergencies)

### Terminal 4: Flask Application
```bash
cd "Final Project/zzzz"
python app.py
```

**Expected output:**
```
TWILIO_ACCOUNT_SID: ✓ or ✗
TWILIO_AUTH_TOKEN: ✓ or ✗
TWILIO_PHONE_NUMBER: ✓ or ✗
Successfully connected to MongoDB
Database indexes created successfully
✓ Agentic AI routes registered
 * Running on http://127.0.0.1:5001
```

**✅ Success indicators:**
- MongoDB connected
- Agentic AI routes registered
- Server running on port 5001

---

## Step 5: Verify Everything is Working

### 5.1 Check Flask App
Open browser: **http://localhost:5001**

You should see:
- Landing page loads
- Login/Signup pages work

### 5.2 Check Celery Worker
In Terminal 2, you should see:
```
[timestamp] Task agents.autopulse_agent.monitor_inventory[...] received
[timestamp] Found X active hospitals to monitor
```

### 5.3 Check Celery Beat
In Terminal 3, you should see:
```
[timestamp] Scheduler: Sending due task autopulse-inventory-check
```

### 5.4 Test MongoDB Connection
```bash
python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGODB_URI')); print('MongoDB connected:', client.admin.command('ping'))"
```

---

## Step 6: Create Test Data (Optional but Recommended)

### 6.1 Create Test Admin Account

**Option A: Use Default Admin**
- Email: `admin@blooddonation.com`
- Password: `admin123`
- The system creates this automatically on first run

**Option B: Create via Signup**
1. Go to: http://localhost:5001/admin/signup
2. Fill in hospital details
3. Upload verification document
4. Wait for approval (or manually approve in database)

### 6.2 Create Test Donor Account

1. Go to: http://localhost:5001/signup
2. Fill in:
   - Name, Email, Password
   - Blood Group (e.g., O+)
   - Location (latitude, longitude)
   - Health data (age, weight, height)

### 6.3 Add Blood Inventory (Admin Dashboard)

1. Login as admin: http://localhost:5001/admin/login
2. Go to Blood Availability section
3. Update inventory for different blood groups
4. Save changes

---

## Step 7: Test the Agents

### 7.1 Test AutoPulse Agent (Manual Trigger)

**Via API:**
```bash
# First, get admin session (login via browser, then use session cookie)
curl -X POST http://localhost:5001/api/agents/autopulse/monitor \
  -H "Content-Type: application/json" \
  -H "Cookie: session=your_session_cookie" \
  -d '{"admin_id": "your_admin_id"}'
```

**Via Python:**
```python
from agents.autopulse_agent import AutoPulseAgent

agent = AutoPulseAgent()
result = agent.execute()  # Monitor all hospitals
print(result)
```

**Check Celery Worker Terminal:**
You should see:
```
[timestamp] Found X active hospitals to monitor
[timestamp] Monitoring hospital: Hospital Name (ID: ...)
[timestamp] [AUTOPULSE] Low stock detected: O+ (current: 5, threshold: 15)
```

### 7.2 Test RapidAid Agent

```python
from agents.rapidaid_agent import RapidAidAgent

agent = RapidAidAgent()
result = agent.execute({
    'type': 'manual',
    'hospital_id': 'your_hospital_id',
    'blood_group': 'O+',
    'units_needed': 2,
    'severity': 'high'
})
print(result)
```

### 7.3 Test PathFinder Agent

```python
from agents.pathfinder_agent import PathFinderAgent

agent = PathFinderAgent()
result = agent.execute(
    donor_id='donor_id',
    hospital_id='hospital_id',
    request_id='request_id'
)
print(result)
```

### 7.4 Test LinkBridge Agent

```python
from agents.linkbridge_agent import LinkBridgeAgent

agent = LinkBridgeAgent()
result = agent.execute(
    hospital_id='hospital_id',
    blood_group='O+',
    units_needed=3
)
print(result)
```

---

## Step 8: Test LifeBot Explainable AI Assistant

### 8.1 Access Admin Dashboard

1. Login as admin: http://localhost:5001/admin/login
2. Click on **"AI Assistant"** in the navigation
3. You should see the LifeBot interface

### 8.2 Test LifeBot Tasks

**Task 1: Hospital Stock Lookup**
1. Click on **"Hospital Stock"** tab
2. Select a blood group (e.g., O-)
3. Click **"Run inventory scan"**
4. Wait for response
5. Check **"Explainable Response"** section for:
   - Explanation text
   - Tool traces (MCP.MongoAdmins.read, Gemini.Explain)
   - Data table

**Task 2: Accepted Donors**
1. Click on **"Accepted Donors"** tab
2. Select a request ID from dropdown (or enter manually)
3. Click **"Fetch accepted donors"**
4. View results with explanations

**Task 3: Successful Donations**
1. Click on **"Successful Donations"** tab
2. Set limit (default 10)
3. Click **"Load timeline"**
4. View donation history

**Task 4: Handle Emergency**
1. Click on **"Handle Emergency"** tab
2. Fill in:
   - Hospital (select from dropdown)
   - Blood Group
   - Units Needed
   - Severity
   - Optional: Latitude, Longitude
3. Click **"Trigger emergency workflow"**
4. View result or error response

### 8.3 Test Quick Scripts

Click any quick script button:
- "Scan O- stock network"
- "Last 5 successful routes"
- "Accepted donors for latest request"
- "Prepare emergency payload"

---

## Step 9: Test ADK Integration

### 9.1 Test ADK Agents

```python
# Navigate to project directory
cd "Final Project/zzzz"

# Run Python
python

# Import ADK agents
from adk_integration import adk_lifebot, adk_autopulse, session_service, memory_bank
import asyncio

# Test LifeBot
result = asyncio.run(adk_lifebot.run("Show me O- stock"))
print(result)

# Check session
sessions = session_service.sessions
print(f"Active sessions: {len(sessions)}")

# Check memory
memories = memory_bank.get_recent(5)
print(f"Recent memories: {len(memories)}")
```

### 9.2 Test MCP Tools

```python
from mcp_tools import MongoDBMCPTools
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGODB_URI'))
db = client.blood_donation

mcp = MongoDBMCPTools(db, db.admins, db.users, db.notifications)

# Test get_blood_stock
result = mcp.get_blood_stock('O+')
print(f"Total O+ units: {result['total_units']}")

# Test get_all_tools
tools = mcp.get_all_tools()
print(f"Available MCP tools: {len(tools)}")
```

---

## Step 10: Test Observability

### 10.1 Check Logs

```python
from observability import observability

# Get metrics
metrics = observability.get_metrics_summary()
print(f"Total traces: {metrics['total_traces']}")
print(f"Agent invocations: {metrics['agent_invocations']}")

# Export traces
observability.export_traces('traces.json')
print("Traces exported to traces.json")
```

### 10.2 Check Log Files

```bash
# Check Flask app logs
tail -f app.log

# Check Celery logs (in terminal output)
# Check observability logs
tail -f lifelink_observability.log
```

---

## Step 11: Run Agent Evaluations

```bash
cd "Final Project/zzzz"
python agent_evaluation.py
```

**Expected output:**
```json
{
  "autopulse": {
    "test_name": "AutoPulse Inventory Monitoring",
    "passed": true,
    "duration_seconds": 2.34
  },
  "rapidaid": {
    "test_name": "RapidAid Emergency Response",
    "passed": true
  },
  ...
  "summary": {
    "total_tests": 5,
    "passed_tests": 5,
    "pass_rate": 100.0
  }
}
```

---

## Step 12: Verify Scheduled Tasks

### 12.1 Check AutoPulse Runs Every 3 Minutes

In Celery Worker terminal, you should see every 3 minutes:
```
[timestamp] Task agents.autopulse_agent.monitor_inventory[...] received
[timestamp] Found X active hospitals to monitor
```

### 12.2 Check RapidAid Runs Every 5 Minutes

Every 5 minutes:
```
[timestamp] Task agents.rapidaid_agent.check_emergencies[...] received
[timestamp] [RAPIDAID] Checking news APIs for emergencies...
```

---

## Troubleshooting

### Issue: Redis Connection Error

**Symptoms:**
```
Error: [Errno 111] Connection refused
```

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not, start Redis
redis-server
```

### Issue: MongoDB Connection Error

**Symptoms:**
```
MongoDB connection error: ...
```

**Solution:**
1. Check `MONGODB_URI` in `.env`
2. Verify MongoDB is accessible
3. Check network/firewall settings
4. Test connection:
```python
from pymongo import MongoClient
client = MongoClient('your_mongodb_uri')
client.admin.command('ping')
```

### Issue: Celery Worker Not Starting

**Symptoms:**
```
ImportError: No module named 'agents'
```

**Solution:**
```bash
# Make sure you're in the correct directory
cd "Final Project/zzzz"

# Check Python path
python -c "import sys; print(sys.path)"

# Install missing packages
pip install -r requirements.txt
```

### Issue: Agents Not Triggering

**Symptoms:**
- No tasks in Celery Worker
- No logs in agent_logs collection

**Solution:**
1. Check `AGENTS_ENABLED` flag in app.py
2. Verify Celery Beat is running
3. Check Redis connectivity
4. Verify task registration in celery_app.py

### Issue: LifeBot Not Responding

**Symptoms:**
- LifeBot shows "Offline" status
- No response to queries

**Solution:**
1. Check `GOOGLE_API_KEY` in `.env`
2. Verify Gemini API is accessible
3. Check browser console for errors
4. Verify MongoDB connection

### Issue: Port Already in Use

**Symptoms:**
```
OSError: [Errno 48] Address already in use
```

**Solution:**
```bash
# Find process using port 5001
lsof -i :5001  # Mac/Linux
netstat -ano | findstr :5001  # Windows

# Kill process
kill -9 <PID>  # Mac/Linux
taskkill /PID <PID> /F  # Windows
```

---

## Quick Start Script (Windows)

Create `start_all.bat`:

```batch
@echo off
echo Starting LifeLink System...

start "Redis" cmd /k "redis-server"
timeout /t 3

start "Celery Worker" cmd /k "cd Final Project\zzzz && celery -A celery_app worker --loglevel=info --pool=solo"
timeout /t 3

start "Celery Beat" cmd /k "cd Final Project\zzzz && celery -A celery_app beat --loglevel=info"
timeout /t 3

start "Flask App" cmd /k "cd Final Project\zzzz && python app.py"

echo All services started!
echo Open http://localhost:5001 in your browser
pause
```

---

## Quick Start Script (Linux/Mac)

Create `start_all.sh`:

```bash
#!/bin/bash

echo "Starting LifeLink System..."

# Start Redis (if not running as service)
redis-server &
sleep 2

# Start Celery Worker
cd "Final Project/zzzz"
celery -A celery_app worker --loglevel=info &
sleep 2

# Start Celery Beat
celery -A celery_app beat --loglevel=info &
sleep 2

# Start Flask App
python app.py &

echo "All services started!"
echo "Open http://localhost:5001 in your browser"
```

Make executable:
```bash
chmod +x start_all.sh
./start_all.sh
```

---

## Verification Checklist

After starting all services, verify:

- [ ] Redis is running (`redis-cli ping` returns PONG)
- [ ] Celery Worker shows "ready" message
- [ ] Celery Beat shows "Starting..." message
- [ ] Flask app shows "Running on http://127.0.0.1:5001"
- [ ] Browser can access http://localhost:5001
- [ ] Admin login works
- [ ] LifeBot interface loads
- [ ] AutoPulse tasks appear in Celery Worker (every 3 min)
- [ ] RapidAid tasks appear in Celery Worker (every 5 min)
- [ ] LifeBot can query stock
- [ ] MCP tools work
- [ ] Observability logs are created

---

## Next Steps

Once everything is running:

1. **Create test data** (admins, users, inventory)
2. **Test each agent** individually
3. **Test LifeBot** all 4 tasks
4. **Run evaluations** to verify compliance
5. **Check observability** logs
6. **Export traces** for documentation

---

## Support

If you encounter issues:

1. Check log files (`app.log`, `lifelink_observability.log`)
2. Check Celery Worker/Beat terminal output
3. Verify all environment variables
4. Test each service individually
5. Review troubleshooting section above

---

**🎉 Once all services are running, you can see the complete system in action!**

