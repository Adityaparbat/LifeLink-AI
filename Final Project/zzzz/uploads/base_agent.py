"""
Base Agent Class for all AI Agents
"""
from abc import ABC, abstractmethod
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
from pathlib import Path
import logging

# Load .env file from the project root (zzzz directory)
# Get the directory where this file is located
_current_dir = Path(__file__).resolve().parent
# Go up one level to get to zzzz directory
_project_root = _current_dir.parent
_env_path = _project_root / '.env'
load_dotenv(_env_path)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents in the system"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.db = self._connect_db()
        self.logger = logging.getLogger(f"{__name__}.{agent_name}")
        
    def _connect_db(self):
        """Connect to MongoDB"""
        try:
            print(f"[BaseAgent] Attempting to connect to MongoDB...")
            mongodb_uri = os.getenv('MONGODB_URI')
            if not mongodb_uri:
                print(f"[BaseAgent] ERROR: MONGODB_URI not found in environment variables!")
                raise ValueError("MONGODB_URI not found in environment variables. Please check your .env file.")
            
            # Log the connection attempt (without sensitive info)
            print(f"[BaseAgent] MongoDB URI found: {mongodb_uri[:30]}...")
            logger.info(f"Connecting to MongoDB... URI starts with: {mongodb_uri[:30]}...")
            
            print(f"[BaseAgent] Creating MongoClient...")
            client = MongoClient(mongodb_uri)
            db = client.blood_donation
            
            # Test the connection
            print(f"[BaseAgent] Testing connection with ping...")
            client.admin.command('ping')
            print(f"[BaseAgent] Successfully connected to MongoDB!")
            logger.info("Successfully connected to MongoDB")
            
            return db
        except Exception as e:
            print(f"[BaseAgent] FAILED to connect to MongoDB: {str(e)}")
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    @abstractmethod
    def execute(self, *args, **kwargs):
        """Execute agent's main logic"""
        pass
    
    def log_action(self, action: str, details: dict = None):
        """Log agent actions"""
        log_entry = {
            'agent': self.agent_name,
            'action': action,
            'timestamp': datetime.now(timezone.utc),
            'details': details or {}
        }
        
        try:
            self.db.agent_logs.insert_one(log_entry)
            self.logger.info(f"{action}: {details}")
        except Exception as e:
            self.logger.error(f"Failed to log action: {str(e)}")
    
    def get_hospital_inventory(self, admin_id: str):
        """Get current blood inventory for a hospital"""
        try:
            from bson import ObjectId
            admin = self.db.admins.find_one({'_id': ObjectId(admin_id)})
            if admin:
                return admin.get('blood_inventory', {
                    'A+': 0, 'A-': 0, 'B+': 0, 'B-': 0,
                    'AB+': 0, 'AB-': 0, 'O+': 0, 'O-': 0
                })
            return None
        except Exception as e:
            self.logger.error(f"Error getting inventory: {str(e)}")
            return None
    
    def find_nearby_donors(self, latitude: float, longitude: float, 
                          blood_group: str, max_distance_km: float = 10):
        """Find nearby donors matching blood group (excludes blocked users)"""
        try:
            # Get all donors with matching blood group who are NOT blocked
            donors = list(self.db.users.find({
                'blood_group': blood_group,
                '$or': [
                    {'blocked': {'$exists': False}},  # User doesn't have blocked field
                    {'blocked': False}  # User is explicitly not blocked
                ]
            }))
            matching_donors = []
            
            for donor in donors:
                if 'location' not in donor:
                    continue
                
                donor_coords = donor['location']['coordinates']
                donor_lat = float(donor_coords[1])
                donor_lon = float(donor_coords[0])
                
                # Calculate distance using Haversine formula
                distance = self._haversine_distance(
                    latitude, longitude, donor_lat, donor_lon
                )
                
                if distance <= max_distance_km:
                    # Check if donor is eligible (not in cooldown)
                    if self._is_eligible_donor(donor):
                        matching_donors.append({
                            'id': str(donor['_id']),
                            'name': donor.get('name', 'Unknown'),
                            'phone': donor.get('phone', ''),
                            'email': donor.get('email', ''),
                            'distance': round(distance, 2),
                            'location': donor.get('location', {}),
                            'last_donation_date': donor.get('last_donation_date'),
                            'blood_group': donor.get('blood_group')
                        })
            
            # Sort by distance
            matching_donors.sort(key=lambda x: x['distance'])
            return matching_donors
            
        except Exception as e:
            self.logger.error(f"Error finding nearby donors: {str(e)}")
            return []
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                           lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates using Haversine formula"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth radius in kilometers
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + \
            cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    
    def _is_eligible_donor(self, donor: dict) -> bool:
        """Check if donor is eligible (not in cooldown period)"""
        try:
            if 'last_donation_date' not in donor:
                return True
            
            last_donation = donor['last_donation_date']
            if isinstance(last_donation, str):
                last_donation = datetime.fromisoformat(
                    last_donation.replace('Z', '+00:00')
                )
            
            if last_donation.tzinfo is None:
                last_donation = last_donation.replace(tzinfo=timezone.utc)
            
            cooldown_end = last_donation + timedelta(days=90)
            current_time = datetime.now(timezone.utc)
            
            return current_time >= cooldown_end
        except Exception as e:
            self.logger.warning(f"Error checking eligibility: {str(e)}")
            return True  # Assume eligible if check fails

