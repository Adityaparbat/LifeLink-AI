# Agentic AI Blood Donation System - Setup Guide

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+** installed
2. **Redis** installed and running
3. **MongoDB** connection string
4. **Environment variables** configured

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Install Redis

**Windows:**
- Download Redis from: https://github.com/microsoftarchive/redis/releases
- Extract and run `redis-server.exe`
- Or use WSL: `wsl sudo apt-get install redis-server`

**Linux:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
```

**Mac:**
```bash
brew install redis
brew services start redis
```

### Step 3: Configure Environment Variables

Create/update `.env` file in `Final Project/zzzz/` directory:

```env
# MongoDB
MONGODB_URI=your_mongodb_connection_string

# Redis (for Celery)
REDIS_URL=redis://localhost:6379/0

# Twilio (for voice calls)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_number
CALLBACK_BASE_URL=http://localhost:8000

# SMS (Fast2SMS)
FAST2SMS_API_KEY=your_fast2sms_key

# Optional: Route Planning
GOOGLE_MAPS_API_KEY=your_google_maps_key
OPENROUTE_API_KEY=your_openroute_key

# Optional: Emergency Detection
NEWS_API_KEY=your_news_api_key
```

### Step 4: Start All Services

**Option A: Automated (Windows)**
```bash
start_all_services.bat
```

**Option B: Manual Start**

Open 4 separate terminals:

**Terminal 1 - Redis:**
```bash
redis-server
```

**Terminal 2 - Celery Worker:**
```bash
cd "Final Project/zzzz"
celery -A celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 - Celery Beat (Scheduler):**
```bash
cd "Final Project/zzzz"
celery -A celery_app beat --loglevel=info
```

**Terminal 4 - Flask Application:**
```bash
cd "Final Project/zzzz"
python app.py
```

### Step 5: Verify Setup

1. **Check Redis:**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. **Check Celery Worker:**
   - Look for "celery@hostname ready" message

3. **Check Celery Beat:**
   - Look for "beat: Starting..." message

4. **Check Flask App:**
   - Visit http://localhost:5001
   - Should see "✓ Agentic AI routes registered" in console

## 📋 System Architecture

```
┌─────────────────┐
│   Flask App     │  ← Main Application
│   (Port 5001)   │
└────────┬────────┘
         │
         ├──→ AutoPulse Agent (Inventory Monitoring)
         ├──→ RapidAid Agent (Emergency Response)
         ├──→ PathFinder Agent (Route Planning)
         └──→ LinkBridge Agent (Hospital Coordination)
                  │
                  ↓
         ┌─────────────────┐
         │  Celery Worker   │  ← Task Execution
         └────────┬─────────┘
                  │
                  ↓
         ┌─────────────────┐
         │      Redis      │  ← Message Broker
         └─────────────────┘
                  │
                  ↓
         ┌─────────────────┐
         │   Celery Beat   │  ← Scheduled Tasks
         └─────────────────┘
```

## 🤖 Agent Workflows

### AutoPulse Agent (Inventory Intelligence)

**Triggers:**
- Every 15 minutes (automatic)
- When inventory is updated manually
- Daily at 6 AM for predictions

**Actions:**
1. Checks all hospital inventories
2. Identifies low stock (< threshold)
3. Finds nearby eligible donors (within 10km)
4. Sends SMS notifications
5. Makes voice calls via Twilio
6. Creates pending notifications

**API:**
```bash
POST /api/agents/autopulse/monitor
{
  "admin_id": "hospital_id"
}
```

### RapidAid Agent (Critical Response)

**Triggers:**
- Every 5 minutes (automatic emergency check)
- Manual emergency request
- Hospital alerts
- Rare blood group requests

**Actions:**
1. Detects emergencies from multiple sources
2. Contacts ALL eligible donors (up to 50km)
3. Sends urgent SMS
4. Makes emergency voice calls
5. Creates high-priority notifications

**API:**
```bash
POST /api/agents/rapidaid/emergency
{
  "hospital_id": "hospital_id",
  "blood_group": "O+",
  "units_needed": 5,
  "severity": "critical",
  "location": {
    "latitude": 18.5204,
    "longitude": 73.8567
  }
}
```

### PathFinder Agent (Smart Logistics)

**Triggers:**
- When donor accepts request
- Periodic route updates (every 10 minutes)
- Donor location updates

**Actions:**
1. Calculates optimal route
2. Tracks donor movement
3. Updates hospital dashboard
4. Handles delays (reroute or backup)

**API:**
```bash
POST /api/agents/pathfinder/plan-route
{
  "donor_id": "donor_id",
  "hospital_id": "hospital_id",
  "request_id": "request_id"
}

POST /api/agents/pathfinder/update-location
{
  "request_id": "request_id",
  "latitude": 18.5204,
  "longitude": 73.8567
}
```

### LinkBridge Agent (Hospital Coordination)

**Triggers:**
- Every 30 minutes (automatic check)
- When inventory is low
- Manual transfer request

**Actions:**
1. Finds nearby hospitals (within 50km)
2. Checks available stock
3. Creates transfer requests
4. If no stock, triggers AutoPulse

**API:**
```bash
POST /api/agents/linkbridge/check-stock
{
  "hospital_id": "hospital_id",
  "blood_group": "O+",
  "units_needed": 3
}
```

## 🔄 Integration Points

### Automatic Triggers

1. **Inventory Update** → AutoPulse Agent
   - When admin updates inventory, AutoPulse checks for low stock

2. **Donor Accepts** → PathFinder Agent
   - When donor accepts request, PathFinder plans route

3. **Low Stock** → LinkBridge → AutoPulse
   - LinkBridge checks nearby hospitals first
   - If no stock, triggers AutoPulse

4. **Emergency** → RapidAid Agent
   - Manual trigger or automatic detection

## 📊 Monitoring

### View Agent Logs

```python
from pymongo import MongoClient
client = MongoClient('your_mongodb_uri')
db = client.blood_donation

# View recent agent actions
logs = db.agent_logs.find().sort('timestamp', -1).limit(20)
for log in logs:
    print(f"{log['agent']}: {log['action']} at {log['timestamp']}")
```

### Check Celery Task Status

```python
from celery_app import celery_app
task = celery_app.AsyncResult('task-id-here')
print(f"Status: {task.status}")
print(f"Result: {task.result}")
```

### View Scheduled Tasks

Check `celery_app.py` for beat_schedule configuration.

## 🐛 Troubleshooting

### Issue: Redis Connection Error

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
redis-server
```

### Issue: Celery Worker Not Starting

**Solution:**
1. Check Redis is running
2. Verify REDIS_URL in .env
3. Check for import errors in agent files
4. Ensure all dependencies installed

### Issue: Tasks Not Executing

**Solution:**
1. Verify Celery Beat is running
2. Check task registration in celery_app.py
3. Check worker logs for errors
4. Verify Redis connectivity

### Issue: Agents Not Triggering

**Solution:**
1. Check AGENTS_ENABLED flag in app.py
2. Verify agent routes are registered
3. Check MongoDB connection
4. Review agent logs in database

### Issue: Import Errors

**Solution:**
```bash
# Ensure you're in the correct directory
cd "Final Project/zzzz"

# Check Python path
python -c "import sys; print(sys.path)"

# Install missing packages
pip install -r requirements.txt
```

## 📝 Testing

### Test AutoPulse Agent

```python
from agents.autopulse_agent import AutoPulseAgent

agent = AutoPulseAgent()
result = agent.execute(admin_id="your_hospital_id")
print(result)
```

### Test RapidAid Agent

```python
from agents.rapidaid_agent import RapidAidAgent

agent = RapidAidAgent()
result = agent.execute({
    'type': 'manual',
    'hospital_id': 'your_hospital_id',
    'blood_group': 'O+',
    'units_needed': 5,
    'severity': 'high'
})
print(result)
```

### Test PathFinder Agent

```python
from agents.pathfinder_agent import PathFinderAgent

agent = PathFinderAgent()
result = agent.execute(
    donor_id="donor_id",
    hospital_id="hospital_id",
    request_id="request_id"
)
print(result)
```

### Test LinkBridge Agent

```python
from agents.linkbridge_agent import LinkBridgeAgent

agent = LinkBridgeAgent()
result = agent.execute(
    hospital_id="hospital_id",
    blood_group="O+",
    units_needed=3
)
print(result)
```

## 🚀 Production Deployment

1. **Use Process Manager:**
   - Supervisor (Linux)
   - systemd (Linux)
   - PM2 (Node.js-based, works for Python too)

2. **Redis Persistence:**
   - Configure Redis AOF or RDB
   - Set up Redis replication

3. **Monitoring:**
   - Use Flower for Celery monitoring
   - Set up logging aggregation
   - Monitor Redis memory usage

4. **Scaling:**
   - Run multiple Celery workers
   - Use Redis Cluster for high availability
   - Load balance Flask app

## 📚 Additional Resources

- [Celery Documentation](https://docs.celeryproject.org/)
- [Redis Documentation](https://redis.io/docs/)
- [Flask Blueprints](https://flask.palletsprojects.com/en/2.3.x/blueprints/)

## ✅ Next Steps

1. ✅ Install dependencies
2. ✅ Configure environment variables
3. ✅ Start Redis
4. ✅ Start Celery Worker
5. ✅ Start Celery Beat
6. ✅ Start Flask App
7. ✅ Test agent endpoints
8. ✅ Monitor agent logs
9. ✅ Configure production deployment

## 🆘 Support

For issues or questions:
1. Check agent logs in MongoDB
2. Review Celery worker logs
3. Check Redis connectivity
4. Verify environment variables
5. Review this guide

---

**System Status:** All agents operational ✅

