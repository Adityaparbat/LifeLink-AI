"""
AutoPulse Agent - Inventory Intelligence
Continuously monitors hospital stock, predicts shortages, and auto-contacts donors
"""
from .base_agent import BaseAgent
from celery import shared_task
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import requests
import os
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)


class AutoPulseAgent(BaseAgent):
    """Agent that monitors inventory and automatically contacts donors when stock is low"""
    
    def __init__(self, orchestrator=None):
        super().__init__("AutoPulse")
        self.inventory_thresholds = {
            'A+': 10, 'A-': 5, 'B+': 10, 'B-': 5,
            'AB+': 5, 'AB-': 3, 'O+': 15, 'O-': 8
        }
        self.rare_blood_groups = {'O-', 'AB-', 'B-', 'A-'}
        self.twilio_client = None
        self.orchestrator = orchestrator
        self._init_twilio()
    
    def _init_twilio(self):
        """Initialize Twilio client"""
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            if account_sid and auth_token:
                self.twilio_client = Client(account_sid, auth_token)
        except Exception as e:
            logger.warning(f"Twilio not configured: {str(e)}")
    
    def execute(self, admin_id: str = None):
        """Main execution - monitor all hospitals or specific one"""
        if admin_id:
            return self._monitor_hospital(admin_id)
        else:
            return self._monitor_all_hospitals()
    
    def _monitor_all_hospitals(self):
        """Monitor inventory for all active hospitals"""
        try:
            # Query for active hospitals
            hospitals = list(self.db.admins.find({'status': 'active'}))
            self.logger.info(f"Found {len(hospitals)} active hospitals to monitor")
            
            # Also check total hospitals for debugging
            total_hospitals = self.db.admins.count_documents({})
            pending_hospitals = self.db.admins.count_documents({'status': 'pending'})
            self.logger.info(f"Total hospitals: {total_hospitals}, Active: {len(hospitals)}, Pending: {pending_hospitals}")
            
            if len(hospitals) == 0:
                self.logger.warning("No active hospitals found. Consider checking pending hospitals or updating hospital status.")
            
            results = []
            
            for hospital in hospitals:
                hospital_name = hospital.get('hospital_name', 'Unknown')
                hospital_id = str(hospital['_id'])
                self.logger.info(f"Monitoring hospital: {hospital_name} (ID: {hospital_id})")
                res = self._monitor_hospital(hospital_id)
                results.append(res)
            
            self.log_action('monitored_all_hospitals', {
                'hospitals_checked': len(hospitals),
                'results': results
            })
            
            return results
        
        except Exception as e:
            self.logger.error(f"Error monitoring all hospitals: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    
    from bson import ObjectId

    def _monitor_hospital(self, admin_id: str):
        """Monitor a specific hospital's inventory"""
        try:
            # Fetch hospital doc from correct collection
            admin = self.db.admins.find_one({'_id': ObjectId(admin_id)})
            if not admin:
                return {'success': False, 'error': 'Hospital not found'}
            
            # Directly read inventory from admin document
            inventory_raw = admin.get('blood_inventory', {})
            
            # Handle different inventory formats
            if isinstance(inventory_raw, list):
                # If inventory is a list, convert to empty dict (list format not supported)
                self.logger.warning(f"Hospital {admin_id} has inventory as list, converting to empty dict")
                inventory = {}
            elif isinstance(inventory_raw, dict):
                inventory = inventory_raw
            else:
                # Unknown format, use empty dict
                self.logger.warning(f"Hospital {admin_id} has inventory in unknown format: {type(inventory_raw)}")
                inventory = {}
            
            # If inventory is empty, initialize with zeros
            if not inventory:
                inventory = {
                    'A+': 0, 'A-': 0, 'B+': 0, 'B-': 0,
                    'AB+': 0, 'AB-': 0, 'O+': 0, 'O-': 0
                }
                self.logger.info(f"Hospital {admin_id} has empty inventory, initialized with zeros")
            
            low_stock_groups = []
            
            # Check thresholds
            for blood_group, threshold in self.inventory_thresholds.items():
                current_stock = inventory.get(blood_group, 0)
                if current_stock < threshold:
                    low_stock_groups.append({
                        'blood_group': blood_group,
                        'current': current_stock,
                        'threshold': threshold,
                        'deficit': threshold - current_stock
                    })
            
            # Auto-contact donors for all low groups via orchestrator.
            # For Celery/background runs where no orchestrator was injected,
            # lazily import the global orchestrator to avoid circular imports.
            from .agent_orchestrator import orchestrator as global_orchestrator
            active_orchestrator = self.orchestrator or global_orchestrator

            for group in low_stock_groups:
                self.logger.info(f"[AUTOPULSE] Low stock detected: {group['blood_group']} (current: {group['current']}, threshold: {group['threshold']}, deficit: {group['deficit']})")
                self.logger.info(f"[AUTOPULSE] Invoking orchestrator.handle_low_inventory for hospital_id={admin_id}, blood_group={group['blood_group']}, units_needed={group['deficit']}")
                active_orchestrator.handle_low_inventory(
                    admin_id,
                    group["blood_group"],
                    group["deficit"]
                )
                self.logger.info(f"[AUTOPULSE] Orchestrator.handle_low_inventory completed for {group['blood_group']}")
            
            # Log action
            if low_stock_groups:
                self.log_action('low_stock_detected', {
                    'hospital_id': admin_id,
                    'hospital_name': admin.get('hospital_name', 'Unknown'),
                    'low_stock_groups': low_stock_groups
                })
            
            return {
                'success': True,
                'hospital_id': admin_id,
                'inventory': inventory,
                'low_stock_groups': low_stock_groups
            }
        
        except Exception as e:
            self.logger.error(f"Error monitoring hospital {admin_id}: {str(e)}")
            return {'success': False, 'error': str(e)}

    
    def _auto_contact_donors(self, admin_id: str, blood_group: str, units_needed: int):
        """Automatically contact nearby donors for low stock"""
        try:
            # Fetch hospital/admin
            admin = self.db.admins.find_one({'_id': ObjectId(admin_id)})
            if not admin or 'location' not in admin:
                return
            
            admin_lat = float(admin['location']['coordinates'][1])
            admin_lon = float(admin['location']['coordinates'][0])
            units_requested = max(1, int(units_needed))
            is_rare_group = blood_group in self.rare_blood_groups

            # ---- FETCH DONORS FROM CORRECT COLLECTION ----
            donors_cursor = self.db.users.find({
                'blood_group': blood_group,
                'medical_info.is_eligible': True
            })

            donors = []
            for d in donors_cursor:
                try:
                    lat = float(d['location']['coordinates'][1])
                    lon = float(d['location']['coordinates'][0])
                    distance = self._haversine(admin_lon, admin_lat, lon, lat)
                    
                    donors.append({
                        'id': str(d['_id']),
                        'name': d.get('name'),
                        'phone': d.get('phone'),
                        'distance': distance
                    })
                except:
                    continue

            # Sort donors by nearest first
            donors.sort(key=lambda x: x['distance'])
            donors_to_contact = donors[:5]

            # Notify donors
            for donor in donors_to_contact:
                request_id = str(ObjectId())
                notification_data = {
                    "blood_group_needed": blood_group,
                    "units_needed": units_requested,
                    "hospital_id": str(admin.get("_id")),
                    "hospital_name": admin.get("hospital_name", "Hospital"),
                    "deficit": units_requested,
                    "rare": is_rare_group,
                    "source": "autopulse_agent",
                    "location": {
                        "latitude": admin_lat,
                        "longitude": admin_lon
                    }
                }

                notification = {
                    "user_id": donor['id'],
                    "admin_id": admin_id,
                    "hospital_name": admin.get("hospital_name", "Hospital"),
                    "hospital_address": admin.get("address", ""),
                    "hospital_phone": admin.get("phone", ""),
                    "type": "blood_request",
                    "priority": "critical" if is_rare_group else "high",
                    "blood_group_needed": blood_group,
                    "units_needed": units_requested,
                    "hospital_id": admin.get("_id"),
                    "distance": round(donor["distance"], 2),
                    "message": f"""
                    🚨 URGENT BLOOD DONATION REQUEST 🚨

                    Dear Blood Donor,

                    {admin.get("hospital_name", "Hospital")} urgently needs {blood_group} blood.
                    Current stock is critically low.

                    Distance from you: {round(donor["distance"],2)} KM
                    """,
                    "created_at": datetime.now(timezone.utc),
                    "read": False,
                    "status": "pending",
                    "data": notification_data
                }

                # Check if similar pending notification exists
                existing = self.db.notifications.find_one({
                    "user_id": donor['id'],
                    "admin_id": admin_id,
                    "blood_group_needed": blood_group,
                    "read": False
                })

                if not existing:
                    self.db.notifications.insert_one(notification)

                    # Send SMS
                    self._send_sms(donor['phone'], notification['message'])

                    # Optional — voice call
                    if self.twilio_client:
                        self._make_voice_call(donor['phone'], admin_id, request_id)
                else:
                    self.logger.info(f"Existing notification found: {existing}")

            self.log_action('auto_contacted_donors', {
                'hospital_id': admin_id,
                'blood_group': blood_group,
                'donors_contacted': len(donors_to_contact)
            })

        except Exception as e:
            self.logger.error(f"Error auto-contacting donors: {str(e)}")

    def _haversine(self, lon1, lat1, lon2, lat2):
        from math import radians, sin, cos, sqrt, atan2

        R = 5 # km

        dlon = radians(lon2 - lon1)
        dlat = radians(lat2 - lat1)

        a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def _send_sms(self, phone_number: str, message: str):
        """Send SMS to donor"""
        try:
            formatted_number = ''.join(filter(str.isdigit, phone_number))
            api_key = os.getenv('FAST2SMS_API_KEY', '')
            
            if not api_key:
                return
            
            payload = {
                "route": "q",
                "numbers": formatted_number,
                "message": message
            }
            
            headers = {
                "authorization": api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                "https://www.fast2sms.com/dev/bulkV2",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.info(f"SMS sent to {formatted_number}")
            else:
                self.logger.warning(f"Failed to send SMS: {response.text}")
        except Exception as e:
            self.logger.error(f"Error sending SMS: {str(e)}")
    
    def _make_voice_call(self, phone_number: str, admin_id: str, request_id: str):
        """Make voice call to donor"""
        try:
            if not self.twilio_client:
                return
            
            twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
            callback_url = os.getenv('CALLBACK_BASE_URL', 'http://localhost:8000')
            
            if not twilio_number:
                return
            
            # Format phone number
            if not phone_number.startswith('+'):
                phone_number = '+91' + ''.join(filter(str.isdigit, phone_number))
            
            call = self.twilio_client.calls.create(
                to=phone_number,
                from_=twilio_number,
                url=f"{callback_url}/voice?request_id={request_id}&admin_id={admin_id}",
                status_callback=f"{callback_url}/call-status",
                status_callback_method='POST'
            )
            
            self.logger.info(f"Voice call initiated: {call.sid}")
        except Exception as e:
            self.logger.error(f"Error making voice call: {str(e)}")
    
    def predict_shortages(self):
        """Predict future shortages based on historical data"""
        try:
            hospitals = list(self.db.admins.find({'status': 'active'}))
            predictions = []
            
            for hospital in hospitals:
                hospital_id = str(hospital['_id'])
                
                # Get historical donation data
                historical_data = self._get_historical_data(hospital_id)
                
                # Simple prediction: check trends and upcoming events
                for blood_group in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']:
                    prediction = self._predict_blood_group_shortage(
                        hospital_id, blood_group, historical_data
                    )
                    
                    if prediction['will_be_low']:
                        predictions.append({
                            'hospital_id': hospital_id,
                            'hospital_name': hospital.get('hospital_name', 'Unknown'),
                            'blood_group': blood_group,
                            'predicted_date': prediction['predicted_date'],
                            'confidence': prediction['confidence']
                        })
            
            # Store predictions
            if predictions:
                self.db.shortage_predictions.insert_many([
                    {
                        **pred,
                        'created_at': datetime.now(timezone.utc),
                        'status': 'active'
                    }
                    for pred in predictions
                ])
            
            self.log_action('predicted_shortages', {
                'predictions_count': len(predictions)
            })
            
            return predictions
        except Exception as e:
            self.logger.error(f"Error predicting shortages: {str(e)}")
            return []
    
    def _get_historical_data(self, hospital_id: str):
        """Get historical donation and usage data"""
        try:
            # Get donation history for this hospital
            donations = list(self.db.donation_history.find({
                'admin_id': hospital_id
            }).sort('donation_date', -1).limit(100))
            
            # Get inventory changes
            inventory_changes = list(self.db.inventory_history.find({
                'admin_id': hospital_id
            }).sort('timestamp', -1).limit(100))
            
            return {
                'donations': donations,
                'inventory_changes': inventory_changes
            }
        except Exception as e:
            self.logger.error(f"Error getting historical data: {str(e)}")
            return {'donations': [], 'inventory_changes': []}
    
    def _predict_blood_group_shortage(self, hospital_id: str, blood_group: str, 
                                     historical_data: dict):
        """Predict if a blood group will be low in the next 7 days"""
        try:
            current_inventory = self.get_hospital_inventory(hospital_id)
            if not current_inventory:
                return {'will_be_low': False}
            
            current_stock = current_inventory.get(blood_group, 0)
            threshold = self.inventory_thresholds.get(blood_group, 10)
            
            # Simple prediction: if current stock is close to threshold
            # and historical data shows high usage, predict shortage
            if current_stock < threshold * 1.5:  # Within 50% of threshold
                # Check historical usage rate
                usage_rate = self._calculate_usage_rate(historical_data, blood_group)
                
                # Predict if stock will drop below threshold in 7 days
                days_until_shortage = (current_stock - threshold) / usage_rate if usage_rate > 0 else 999
                
                if days_until_shortage <= 7:
                    return {
                        'will_be_low': True,
                        'predicted_date': (datetime.now(timezone.utc) + 
                                         timedelta(days=int(days_until_shortage))).isoformat(),
                        'confidence': min(0.9, 0.5 + (7 - days_until_shortage) / 7 * 0.4)
                    }
            
            return {'will_be_low': False}
        except Exception as e:
            self.logger.error(f"Error predicting shortage: {str(e)}")
            return {'will_be_low': False}
    
    def _calculate_usage_rate(self, historical_data: dict, blood_group: str):
        """Calculate average daily usage rate for a blood group"""
        try:
            inventory_changes = historical_data.get('inventory_changes', [])
            if len(inventory_changes) < 2:
                return 0.5  # Default rate
            
            # Calculate average daily decrease
            total_decrease = 0
            days = 0
            
            for i in range(1, min(30, len(inventory_changes))):
                change = inventory_changes[i-1]
                prev_change = inventory_changes[i]
                
                if (change.get('blood_group') == blood_group and 
                    prev_change.get('blood_group') == blood_group):
                    diff = prev_change.get('units', 0) - change.get('units', 0)
                    if diff > 0:  # Decrease
                        total_decrease += diff
                        days += 1
            
            return total_decrease / days if days > 0 else 0.5
        except Exception as e:
            self.logger.error(f"Error calculating usage rate: {str(e)}")
            return 0.5


# Celery tasks
@shared_task(name='agents.autopulse_agent.monitor_inventory')
def monitor_inventory(admin_id: str = None):
    """Celery task to monitor inventory"""
    agent = AutoPulseAgent()
    return agent.execute(admin_id)


@shared_task(name='agents.autopulse_agent.predict_shortages')
def predict_shortages():
    """Celery task to predict shortages"""
    agent = AutoPulseAgent()
    return agent.predict_shortages()

