"""
Celery Configuration for Agentic AI Blood Donation System
"""
from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'blood_donation_agents',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'agents.autopulse_agent',
        'agents.rapidaid_agent',
        'agents.pathfinder_agent',
        'agents.linkbridge_agent'
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # AutoPulse Agent: Check inventory every 15 minutes
    'autopulse-inventory-check': {
        'task': 'agents.autopulse_agent.monitor_inventory',
        'schedule': crontab(minute='*/3'),  # Every 15 minutes
    },
    
    # AutoPulse Agent: Predict shortages daily at 6 AM
    'autopulse-predict-shortages': {
        'task': 'agents.autopulse_agent.predict_shortages',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
    
    # RapidAid Agent: Check for emergencies every 5 minutes
    'rapidaid-check-emergencies': {
        'task': 'agents.rapidaid_agent.check_emergencies',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    
}

if __name__ == '__main__':
    celery_app.start()
