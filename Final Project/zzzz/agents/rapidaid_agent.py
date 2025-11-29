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
import feedparser
import google.generativeai as genai
import json
import time
import re

logger = logging.getLogger(__name__)

class RapidAidAgent(BaseAgent):
    """Agent that handles emergency situations and mass donor outreach"""
    
    def __init__(self, orchestrator=None):
        super().__init__("RapidAid")
        self.twilio_client = None
        self._init_twilio()
        self.orchestrator = orchestrator
        self.news_api_key = os.getenv('NEWS_API_KEY', '')
        self.gemini_api_key=os.getenv('GOOGLE_API_KEY','')

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
            handled_emergencies = []
            
            if emergency_type == 'auto':
                # Auto-detect from news/events
                emergencies = self._detect_emergencies()
                for emergency in emergencies:
                    emergency_log = self._handle_emergency(emergency)
                    handled_payload = self._build_handled_emergency_payload(emergency, emergency_log)
                    if handled_payload:
                        handled_emergencies.append(handled_payload)
            else:
                # Manual emergency trigger
                manual_emergency = {
                    'hospital_id': emergency_data.get('hospital_id'),
                    'blood_group': emergency_data.get('blood_group'),
                    'units_needed': emergency_data.get('units_needed', 1),
                    'location': emergency_data.get('location'),
                    'severity': emergency_data.get('severity', 'high'),
                    'description': emergency_data.get('description', 'Emergency blood request')
                }
                emergency_log = self._handle_emergency(manual_emergency)
                handled_payload = self._build_handled_emergency_payload(manual_emergency, emergency_log)
                if handled_payload:
                    handled_emergencies.append(handled_payload)
            
            success = len(handled_emergencies) > 0
            return {
                'success': success,
                'handled_emergencies': handled_emergencies
            }
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
            
            insert_result = self.db.emergencies.insert_one(emergency_log)
            emergency_log['_id'] = insert_result.inserted_id
            
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
            self.logger.info("[RAPIDAID] Checking news APIs for emergencies...")
            news_emergencies = self._check_news_apis()
            self.logger.info(f"[RAPIDAID] News API check completed: found {len(news_emergencies)} emergencies")
            # Check hospital alerts
            hospital_alerts = self._check_hospital_alerts()
            
            # Check for rare blood requests
            rare_blood_requests = self._check_rare_blood_requests()
            
            all_emergencies = news_emergencies + hospital_alerts + rare_blood_requests
            
            # Handle each emergency via orchestrator when available,
            # otherwise fall back to global orchestrator from agents package.
            from .agent_orchestrator import orchestrator as global_orchestrator
            for emergency in all_emergencies:
                hospital_id = emergency.get('hospital_id', 'N/A')
                blood_group = emergency.get('blood_group', 'N/A')
                units_needed = emergency.get('units_needed', 1)
                self.logger.info(f"[RAPIDAID] Emergency detected: hospital_id={hospital_id}, blood_group={blood_group}, units_needed={units_needed}, type={emergency.get('type', 'unknown')}")
                self.logger.info(f"[RAPIDAID] Invoking orchestrator.handle_emergency...")
                if self.orchestrator:
                    self.orchestrator.handle_emergency(emergency)
                else:
                    global_orchestrator.handle_emergency(emergency)
                self.logger.info(f"[RAPIDAID] Orchestrator.handle_emergency completed for {blood_group} at {hospital_id}")
            
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
        """Check news from multiple RSS sources + Gemini to extract emergencies."""

        emergencies = []
        try:
            # Check Gemini key
            if not self.gemini_api_key:
                self.logger.warning("[RAPIDAID] GOOGLE_API_KEY not set; skipping Gemini news analysis.")
                return emergencies

            # Configure Gemini
            try:
                genai.configure(api_key=self.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
            except Exception as e:
                self.logger.error(f"[RAPIDAID] Failed to configure Gemini: {e}")
                return emergencies

            # ------------------ RSS FETCHING BLOCK ------------------

            import feedparser

            def fetch_google_news():
                feeds = [
                    "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
                    "https://news.google.com/rss/search?q=accident+India",
                    "https://news.google.com/rss/search?q=fire+India",
                    "https://news.google.com/rss/search?q=disaster+India"
                ]
                articles = []
                for url in feeds:
                    d = feedparser.parse(url)
                    for e in d.entries:
                        articles.append({
                            "title": e.get("title"),
                            "summary": e.get("summary") or "",
                            "link": e.get("link"),
                            "source": "google_rss"
                        })
                return articles

            def fetch_indian_rss():
                feeds = [
                    "https://feeds.feedburner.com/ndtvnews-india-news",
                    "https://www.thehindu.com/news/national/feeder/default.rss",
                    "https://www.indiatoday.in/rss/home",
                    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms"
                ]
                articles = []
                for url in feeds:
                    d = feedparser.parse(url)
                    for e in d.entries:
                        articles.append({
                            "title": e.get("title"),
                            "summary": e.get("summary") or "",
                            "link": e.get("link"),
                            "source": "india_rss"
                        })
                return articles

            def fetch_disaster_rss():
                feeds = [
                    "https://nitter.net/ndmaindia/rss",
                    "https://nitter.net/ndrf_india/rss",
                    "https://nitter.net/DisasterMgmtIND/rss"
                ]
                articles = []
                for url in feeds:
                    d = feedparser.parse(url)
                    for e in d.entries:
                        articles.append({
                            "title": e.get("title"),
                            "summary": e.get("summary") or "",
                            "link": e.get("link"),
                            "source": "disaster_rss"
                        })
                return articles

            articles = []
            articles.extend(fetch_google_news())
            articles.extend(fetch_indian_rss())
            articles.extend(fetch_disaster_rss())

            self.logger.info(f"[RAPIDAID] RSS total articles fetched: {len(articles)}")

            # ------------------ GEOCODER ------------------

            def geocode_place(place_name: str):
                try:
                    url = "https://nominatim.openstreetmap.org/search"
                    params = {"q": place_name, "format": "json", "limit": 1}
                    headers = {"User-Agent": "RapidAidAgent/1.0"}
                    r = requests.get(url, params=params, headers=headers, timeout=8)
                    if r.status_code == 200:
                        data = r.json()
                        if data:
                            return float(data[0]["lat"]), float(data[0]["lon"])
                except:
                    pass
                return None, None

            # Keyword filter
            keywords = [
                'accident', 'disaster', 'emergency', 'fire', 'collapse',
                'flood', 'explosion', 'crash', 'mass casualty',
                'blood shortage', 'hospital crisis', 'stampede'
            ]

            self.logger.info(f"[RAPIDAID] Processing {len(articles)} RSS articles...")

            for art in articles:
                title = (art.get("title") or "").strip()
                summary = (art.get("summary") or "").strip()
                link = art.get("link")
                text = f"{title}. {summary}"

                if not text or len(text) < 20:
                    continue

                if not any(k in text.lower() for k in keywords):
                    continue

                # Gemini prompt
                prompt = f"""
    You are an emergency-extraction system. Return ONLY valid JSON.
    NEWS:
    Title: {title}
    Summary: {summary}
    URL: {link}

    Required JSON keys:
    - is_emergency: true/false
    - incident_type
    - human_casualties_estimate
    - location_name
    - suggested_blood_group
    - confidence
    - notes
    """

                try:
                    gen_resp = model.generate_content(prompt)
                    raw = getattr(gen_resp, "text", None) or gen_resp
                    json_text = raw if isinstance(raw, str) else str(raw)

                    m = re.search(r"(\{[\s\S]*\})", json_text)
                    if not m:
                        continue

                    payload = json.loads(m.group(1))

                except Exception:
                    continue

                if not payload.get("is_emergency"):
                    continue

                incident_type = payload.get("incident_type", "other")
                casualties = int(payload.get("human_casualties_estimate") or 0)
                loc_name = (payload.get("location_name") or "").strip()
                suggested_bg = payload.get("suggested_blood_group") or None
                
                # Handle confidence - may be string or number
                confidence_val = payload.get("confidence") or 0.0
                if isinstance(confidence_val, str):
                    # Map string confidence to numeric values
                    confidence_map = {"high": 0.8, "medium": 0.6, "low": 0.3, "critical": 0.95}
                    confidence = confidence_map.get(confidence_val.lower(), 0.5)
                else:
                    try:
                        confidence = float(confidence_val)
                    except (ValueError, TypeError):
                        confidence = 0.5
                
                notes = payload.get("notes", "")

                # Severity
                if casualties >= 50 or confidence > 0.9:
                    severity = "critical"
                elif casualties >= 10 or confidence > 0.75:
                    severity = "high"
                elif casualties >= 3 or confidence > 0.5:
                    severity = "moderate"
                else:
                    severity = "low"

                # Estimate blood units
                units = max(1, int(round(casualties * 1.5)))
                if severity == "critical":
                    units = max(units, int(round(casualties * 2.0)))
                if incident_type in ("mass_casualty", "natural_disaster"):
                    units = max(units, 20)

                rare_groups = {"O-", "AB-", "B-", "A-"}
                if suggested_bg in rare_groups:
                    units = int(units * 1.25)

                # Geocode
                lat, lon = geocode_place(loc_name) if loc_name else (None, None)

                # Skip if no location and severity is low (parentheses fix logic error)
                if (lat is None or lon is None) and severity == "low":
                    continue

                emergency_item = {
                    "hospital_id": None,
                    "blood_group": suggested_bg,
                    "units_needed": int(units),
                    "location": {"latitude": lat, "longitude": lon} if lat and lon else None,
                    "severity": severity,
                    "description": f"{incident_type}: {notes or title}",
                    "type": "news",
                    "source": art.get("source"),
                    "title": title,
                    "url": link,
                    "detected_at": datetime.now(timezone.utc)
                }

                emergencies.append(emergency_item)
                time.sleep(0.35)

            self.logger.info(f"[RAPIDAID] Final emergencies extracted: {len(emergencies)}")

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
                        request_data = request.get('data', {}) or {}
                        units_requested = (
                            request_data.get('units_needed') or
                            request.get('units_needed') or
                            1
                        )
                        emergencies.append({
                            'hospital_id': request.get('admin_id'),
                            'blood_group': request_data.get('blood_group_needed'),
                            'units_needed': max(1, int(units_requested)),
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

    def _build_handled_emergency_payload(self, source_emergency: dict, emergency_log: dict):
        """Create standardized payload for downstream agents"""
        if not emergency_log:
            return None
        
        return {
            'emergency_id': str(emergency_log.get('_id')),
            'hospital_id': emergency_log.get('hospital_id') or source_emergency.get('hospital_id'),
            'blood_group': emergency_log.get('blood_group') or source_emergency.get('blood_group'),
            'units_needed': emergency_log.get('units_needed') or source_emergency.get('units_needed', 1),
            'location': emergency_log.get('location') or source_emergency.get('location'),
            'severity': emergency_log.get('severity') or source_emergency.get('severity', 'high'),
            'description': emergency_log.get('description') or source_emergency.get('description')
        }


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

