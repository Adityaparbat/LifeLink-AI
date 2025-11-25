"""
RapidAid Agent - Critical Response
Handles emergencies, mass accidents, and epidemic outbreaks
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


class RapidAidAgent(BaseAgent):
    """Agent that handles emergency situations and mass donor outreach"""
    
    def __init__(self):
        super().__init__("RapidAid")
        self.twilio_client = None
        self._init_twilio()
        self.news_api_key = os.getenv('NEWS_API_KEY', '')
    
    def _init_twilio(self):
        """Initialize Twilio client"""
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            if account_sid and auth_token:
                self.twilio_client = Client(account_sid, auth_token)
        except Exception as e:
            logger.warning(f"Twilio not configured: {str(e)}")
    
    def execute(self, emergency_data: dict):
        """Handle emergency situation"""
        try:
            emergency_type = emergency_data.get('type', 'manual')
            hospital_id = emergency_data.get('hospital_id')
            blood_group = emergency_data.get('blood_group')
            units_needed = emergency_data.get('units_needed', 1)
            location = emergency_data.get('location')
            
            if emergency_type == 'auto':
                # Auto-detect from news/events
                emergencies = self._detect_emergencies()
                for emergency in emergencies:
                    self._handle_emergency(emergency)
            else:
                # Manual emergency trigger
                self._handle_emergency({
                    'hospital_id': hospital_id,
                    'blood_group': blood_group,
                    'units_needed': units_needed,
                    'location': location,
                    'severity': emergency_data.get('severity', 'high'),
                    'description': emergency_data.get('description', 'Emergency blood request')
                })
            
            return {'success': True}
        except Exception as e:
            self.logger.error(f"Error handling emergency: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _handle_emergency(self, emergency: dict):
        """Handle a specific emergency"""
        try:
            hospital_id = emergency.get('hospital_id')
            blood_group = emergency.get('blood_group')
            units_needed = emergency.get('units_needed', 1)
            location = emergency.get('location')
            severity = emergency.get('severity', 'high')
            
            admin = None
            if hospital_id:
                admin = self.db.admins.find_one({'_id': ObjectId(hospital_id)})
            
            # Determine search radius based on severity
            max_distance = 50 if severity == 'critical' else 25  # km
            
            # Get location coordinates
            if location:
                lat, lon = location.get('latitude'), location.get('longitude')
            elif admin and 'location' in admin:
                coords = admin['location']['coordinates']
                lat, lon = float(coords[1]), float(coords[0])
            else:
                self.logger.error("No location provided for emergency")
                return
            
            # Find ALL eligible donors in the area (not slot-wise)
            donors = self.find_nearby_donors(lat, lon, blood_group, max_distance_km=max_distance)
            
            # Contact ALL donors immediately
            contacted_count = 0
            for donor in donors:
                if self._contact_donor_emergency(donor, emergency, admin):
                    contacted_count += 1
            
            # Log emergency
            emergency_log = {
                'type': 'emergency',
                'hospital_id': hospital_id,
                'blood_group': blood_group,
                'units_needed': units_needed,
                'location': {'latitude': lat, 'longitude': lon},
                'severity': severity,
                'donors_contacted': contacted_count,
                'total_donors_found': len(donors),
                'created_at': datetime.now(timezone.utc),
                'status': 'active'
            }
            
            self.db.emergencies.insert_one(emergency_log)
            
            self.log_action('emergency_handled', {
                'emergency_id': str(emergency_log.get('_id')),
                'donors_contacted': contacted_count
            })
            
            return emergency_log
        except Exception as e:
            self.logger.error(f"Error handling emergency: {str(e)}")
            return None
    
    def _contact_donor_emergency(self, donor: dict, emergency: dict, admin: dict):
        """Contact a donor for emergency"""
        try:
            request_id = str(ObjectId())
            hospital_name = admin.get('hospital_name', 'Hospital') if admin else 'Hospital'
            
            # Create urgent notification
            notification = {
                'user_id': donor['id'],
                'type': 'emergency_request',
                'title': f"🚨 URGENT: Emergency Blood Request - {emergency.get('blood_group', 'Blood')}",
                'body': f"EMERGENCY: {hospital_name} urgently needs {emergency.get('blood_group', 'blood')} "
                       f"blood. This is a critical situation. Can you help immediately?",
                'data': {
                    'type': 'emergency',
                    'hospital_name': hospital_name,
                    'hospital_id': admin.get('hospital_id', 'N/A') if admin else 'N/A',
                    'blood_group_needed': emergency.get('blood_group'),
                    'units_needed': emergency.get('units_needed', 1),
                    'distance': donor['distance'],
                    'request_id': request_id,
                    'severity': emergency.get('severity', 'high'),
                    'source': 'rapidaid_agent'
                },
                'created_at': datetime.now(timezone.utc),
                'read': False,
                'status': 'pending',
                'admin_id': emergency.get('hospital_id'),
                'request_id': request_id,
                'channel': 'rapidaid_emergency',
                'priority': 'critical'
            }
            
            # Check if already notified recently (within last hour)
            recent_notification = self.db.notifications.find_one({
                'user_id': donor['id'],
                'admin_id': emergency.get('hospital_id'),
                'data.blood_group_needed': emergency.get('blood_group'),
                'created_at': {
                    '$gte': datetime.now(timezone.utc) - timedelta(hours=1)
                }
            })
            
            if recent_notification:
                return False  # Already notified recently
            
            self.db.notifications.insert_one(notification)
            
            # Send SMS immediately
            self._send_emergency_sms(donor['phone'], notification['body'])
            
            # Make voice call immediately
            if self.twilio_client:
                self._make_emergency_call(
                    donor['phone'],
                    emergency.get('hospital_id'),
                    request_id,
                    emergency.get('blood_group')
                )
            
            return True
        except Exception as e:
            self.logger.error(f"Error contacting donor: {str(e)}")
            return False
    
    def _send_emergency_sms(self, phone_number: str, message: str):
        """Send emergency SMS"""
        try:
            formatted_number = ''.join(filter(str.isdigit, phone_number))
            api_key = os.getenv('FAST2SMS_API_KEY', '')
            
            if not api_key:
                return
            
            # Add urgency prefix
            urgent_message = f"🚨 URGENT: {message}"
            
            payload = {
                "route": "q",
                "numbers": formatted_number,
                "message": urgent_message
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
                self.logger.info(f"Emergency SMS sent to {formatted_number}")
        except Exception as e:
            self.logger.error(f"Error sending emergency SMS: {str(e)}")
    
    def _make_emergency_call(self, phone_number: str, admin_id: str, 
                            request_id: str, blood_group: str):
        """Make emergency voice call"""
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
                url=f"{callback_url}/voice-emergency?request_id={request_id}&admin_id={admin_id}&blood_group={blood_group}",
                status_callback=f"{callback_url}/call-status",
                status_callback_method='POST'
            )
            
            self.logger.info(f"Emergency call initiated: {call.sid}")
        except Exception as e:
            self.logger.error(f"Error making emergency call: {str(e)}")
    
    def check_emergencies(self):
        """Check for emergencies from various sources"""
        try:
            # Check news APIs for accidents/disasters
            news_emergencies = self._check_news_apis()
            
            # Check hospital alerts
            hospital_alerts = self._check_hospital_alerts()
            
            # Check for rare blood requests
            rare_blood_requests = self._check_rare_blood_requests()
            
            all_emergencies = news_emergencies + hospital_alerts + rare_blood_requests
            
            # Handle each emergency
            for emergency in all_emergencies:
                self._handle_emergency(emergency)
            
            self.log_action('checked_emergencies', {
                'found': len(all_emergencies)
            })
            
            return all_emergencies
        except Exception as e:
            self.logger.error(f"Error checking emergencies: {str(e)}")
            return []
    
    def _detect_emergencies(self):
        """Auto-detect emergencies from various sources"""
        return self.check_emergencies()
    
    def _check_news_apis(self):
        """Check news APIs for accidents, disasters, etc."""
        emergencies = []
        
        try:
            if not self.news_api_key:
                return emergencies
            
            # Example: Check for accident/disaster keywords in news
            # This is a simplified version - in production, use proper news API
            keywords = ['accident', 'disaster', 'emergency', 'blood shortage', 'hospital crisis']
            
            # Placeholder for news API integration
            # In production, integrate with NewsAPI, Google News, etc.
            
        except Exception as e:
            self.logger.error(f"Error checking news APIs: {str(e)}")
        
        return emergencies
    
    def _check_hospital_alerts(self):
        """Check for hospital-flagged emergencies"""
        try:
            # Check for hospitals that have flagged emergencies
            alerts = list(self.db.hospital_alerts.find({
                'status': 'active',
                'created_at': {
                    '$gte': datetime.now(timezone.utc) - timedelta(hours=24)
                }
            }))
            
            emergencies = []
            for alert in alerts:
                emergencies.append({
                    'hospital_id': alert.get('hospital_id'),
                    'blood_group': alert.get('blood_group'),
                    'units_needed': alert.get('units_needed', 1),
                    'location': alert.get('location'),
                    'severity': alert.get('severity', 'high'),
                    'description': alert.get('description', 'Hospital emergency alert'),
                    'type': 'hospital_alert'
                })
            
            return emergencies
        except Exception as e:
            self.logger.error(f"Error checking hospital alerts: {str(e)}")
            return []
    
    def _check_rare_blood_requests(self):
        """Check for rare blood group requests (O-, AB-, etc.)"""
        try:
            # Check for urgent requests for rare blood groups
            rare_groups = ['O-', 'AB-', 'B-', 'A-']
            
            urgent_requests = list(self.db.notifications.find({
                'type': 'blood_request',
                'data.blood_group_needed': {'$in': rare_groups},
                'status': 'pending',
                'created_at': {
                    '$gte': datetime.now(timezone.utc) - timedelta(hours=2)
                }
            }))
            
            emergencies = []
            for request in urgent_requests:
                # Check if it's still urgent (no response yet)
                if request.get('response') is None:
                    admin = self.db.admins.find_one({
                        '_id': ObjectId(request.get('admin_id'))
                    })
                    
                    if admin and 'location' in admin:
                        coords = admin['location']['coordinates']
                        emergencies.append({
                            'hospital_id': request.get('admin_id'),
                            'blood_group': request['data'].get('blood_group_needed'),
                            'units_needed': 1,
                            'location': {
                                'latitude': float(coords[1]),
                                'longitude': float(coords[0])
                            },
                            'severity': 'high',
                            'description': f"Rare blood group {request['data'].get('blood_group_needed')} request",
                            'type': 'rare_blood'
                        })
            
            return emergencies
        except Exception as e:
            self.logger.error(f"Error checking rare blood requests: {str(e)}")
            return []


# Celery tasks
@shared_task(name='agents.rapidaid_agent.check_emergencies')
def check_emergencies():
    """Celery task to check for emergencies"""
    agent = RapidAidAgent()
    return agent.check_emergencies()


@shared_task(name='agents.rapidaid_agent.handle_emergency')
def handle_emergency(emergency_data: dict):
    """Celery task to handle emergency"""
    agent = RapidAidAgent()
    return agent.execute(emergency_data)

