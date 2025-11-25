"""
Script to check MongoDB connection and verify hospital data
"""
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
import os

# Load .env file from the project root
_current_dir = Path(__file__).resolve().parent
_env_path = _current_dir / '.env'
load_dotenv(_env_path)

def check_connection():
    """Check MongoDB connection and list hospitals"""
    try:
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            print("[ERROR] MONGODB_URI not found in environment variables")
            print(f"   Looking for .env at: {_env_path}")
            return
        
        print(f"[OK] MONGODB_URI found")
        print(f"  URI: {mongodb_uri[:50]}...")
        print()
        
        # Connect to MongoDB
        print("Connecting to MongoDB...")
        client = MongoClient(mongodb_uri)
        
        # Test connection
        client.admin.command('ping')
        print("[OK] Successfully connected to MongoDB")
        print()
        
        # Get database
        db = client.blood_donation
        print(f"[OK] Using database: blood_donation")
        print()
        
        # Check admins collection
        admins_collection = db.admins
        total_admins = admins_collection.count_documents({})
        print(f"[INFO] Total admins in collection: {total_admins}")
        
        active_admins = admins_collection.count_documents({'status': 'active'})
        print(f"[INFO] Active admins: {active_admins}")
        print()
        
        # List all admins
        print("=" * 60)
        print("ALL ADMINS:")
        print("=" * 60)
        for admin in admins_collection.find():
            print(f"\nHospital Name: {admin.get('hospital_name', 'N/A')}")
            print(f"  ID: {admin.get('_id')}")
            print(f"  Email: {admin.get('email', 'N/A')}")
            print(f"  Status: {admin.get('status', 'N/A')}")
            print(f"  Has blood_inventory: {'blood_inventory' in admin}")
            if 'blood_inventory' in admin:
                inventory = admin.get('blood_inventory', {})
                if isinstance(inventory, dict):
                    print(f"  Inventory type: dict")
                    print(f"  Inventory keys: {list(inventory.keys())}")
                    if inventory:
                        print(f"  Sample inventory: {dict(list(inventory.items())[:3])}")
                elif isinstance(inventory, list):
                    print(f"  Inventory type: list (length: {len(inventory)})")
                    print(f"  Inventory: {inventory}")
                else:
                    print(f"  Inventory type: {type(inventory)}")
                    print(f"  Inventory: {inventory}")
            print("-" * 60)
        
        # Check for admins without status field
        admins_without_status = list(admins_collection.find({'status': {'$exists': False}}))
        if admins_without_status:
            print(f"\n[WARNING] Found {len(admins_without_status)} admins without 'status' field")
            print("   These won't be found by the query {'status': 'active'}")
        
        # Check for admins with different status values
        status_values = list(admins_collection.aggregate([
            {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
        ]))
        if status_values:
            print(f"\n[INFO] Status distribution:")
            for stat in status_values:
                print(f"   {stat['_id']}: {stat['count']}")
        
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_connection()

