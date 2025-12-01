"""
Quick verification script to check if all services are properly configured
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

print("=" * 60)
print("LifeLink System - Setup Verification")
print("=" * 60)
print()

checks = {
    'Python Version': False,
    'MongoDB URI': False,
    'Redis URL': False,
    'Google API Key': False,
    'Required Packages': False,
    'MongoDB Connection': False,
    'Redis Connection': False,
}

# Check Python version
print("[1] Checking Python version...")
if sys.version_info >= (3, 8):
    print(f"   ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    checks['Python Version'] = True
else:
    print(f"   ✗ Python 3.8+ required, found {sys.version_info.major}.{sys.version_info.minor}")

# Check MongoDB URI
print("\n[2] Checking MongoDB configuration...")
mongodb_uri = os.getenv('MONGODB_URI')
if mongodb_uri:
    print(f"   ✓ MONGODB_URI found: {mongodb_uri[:30]}...")
    checks['MongoDB URI'] = True
    
    # Test MongoDB connection
    try:
        from pymongo import MongoClient
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("   ✓ MongoDB connection successful")
        checks['MongoDB Connection'] = True
    except Exception as e:
        print(f"   ✗ MongoDB connection failed: {str(e)}")
else:
    print("   ✗ MONGODB_URI not found in .env file")

# Check Redis URL
print("\n[3] Checking Redis configuration...")
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
print(f"   ✓ REDIS_URL: {redis_url}")
checks['Redis URL'] = True

# Test Redis connection
try:
    import redis
    r = redis.from_url(redis_url, socket_connect_timeout=2)
    r.ping()
    print("   ✓ Redis connection successful")
    checks['Redis Connection'] = True
except Exception as e:
    print(f"   ✗ Redis connection failed: {str(e)}")
    print("   → Make sure Redis is running: redis-server")

# Check Google API Key
print("\n[4] Checking Google API Key...")
google_key = os.getenv('GOOGLE_API_KEY')
if google_key:
    print(f"   ✓ GOOGLE_API_KEY found: {google_key[:10]}...")
    checks['Google API Key'] = True
else:
    print("   ✗ GOOGLE_API_KEY not found (required for LifeBot)")

# Check required packages
print("\n[5] Checking required packages...")
required_packages = [
    'flask', 'pymongo', 'celery', 'redis', 
    'google.generativeai', 'twilio', 'requests'
]
missing = []
for package in required_packages:
    try:
        if package == 'google.generativeai':
            import google.generativeai as genai
        elif package == 'pymongo':
            import pymongo
        else:
            __import__(package)
        print(f"   ✓ {package}")
    except ImportError:
        print(f"   ✗ {package} (missing)")
        missing.append(package)

if not missing:
    checks['Required Packages'] = True
    print("   ✓ All required packages installed")
else:
    print(f"\n   → Install missing packages: pip install {' '.join(missing)}")

# Summary
print("\n" + "=" * 60)
print("Verification Summary")
print("=" * 60)

all_passed = True
for check, passed in checks.items():
    status = "✓" if passed else "✗"
    print(f"{status} {check}")

if all(checks.values()):
    print("\n🎉 All checks passed! System is ready to run.")
    print("\nNext steps:")
    print("1. Start Redis: redis-server")
    print("2. Start Celery Worker: celery -A celery_app worker --loglevel=info")
    print("3. Start Celery Beat: celery -A celery_app beat --loglevel=info")
    print("4. Start Flask: python app.py")
    print("\nOr use the quick start script: start_lifelink.bat (Windows) or start_lifelink.sh (Linux/Mac)")
else:
    print("\n⚠️  Some checks failed. Please fix the issues above before running the system.")
    sys.exit(1)

