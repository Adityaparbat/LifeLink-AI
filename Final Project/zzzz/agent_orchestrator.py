"""
Agent Orchestrator - Coordinates all agents
"""
from agents.autopulse_agent import AutoPulseAgent
from agents.rapidaid_agent import RapidAidAgent
from agents.pathfinder_agent import PathFinderAgent
from agents.linkbridge_agent import LinkBridgeAgent
from celery import chain, group
import logging

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates all agents to work together"""
    
    def __init__(self):
        self.autopulse = AutoPulseAgent()
        self.rapidaid = RapidAidAgent()
        self.pathfinder = PathFinderAgent()
        self.linkbridge = LinkBridgeAgent()
    
    def handle_low_inventory(self, hospital_id: str, blood_group: str, units_needed: int):
        """Handle low inventory situation"""
        try:
            # Step 1: Check nearby hospitals first (LinkBridge)
            linkbridge_result = self.linkbridge.execute(
                hospital_id, blood_group, units_needed
            )
            
            if linkbridge_result.get('has_stock_nearby'):
                # Stock available nearby - return transfer options
                return {
                    'success': True,
                    'action': 'transfer_available',
                    'options': linkbridge_result.get('options', []),
                    'agent': 'linkbridge'
                }
            else:
                # No stock nearby - trigger AutoPulse
                self.autopulse._auto_contact_donors(
                    hospital_id, blood_group, units_needed
                )
                return {
                    'success': True,
                    'action': 'donor_search_initiated',
                    'agent': 'autopulse'
                }
        except Exception as e:
            logger.error(f"Error handling low inventory: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def handle_emergency(self, emergency_data: dict):
        """Handle emergency situation"""
        try:
            # RapidAid handles emergencies
            result = self.rapidaid.execute(emergency_data)
            
            # If donor accepts, trigger PathFinder
            if result.get('success'):
                return {
                    'success': True,
                    'action': 'emergency_handled',
                    'agent': 'rapidaid',
                    'next_step': 'pathfinder_waiting'
                }
            
            return result
        except Exception as e:
            logger.error(f"Error handling emergency: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def handle_donor_accepted(self, request_id: str, donor_id: str, hospital_id: str):
        """Handle when donor accepts request"""
        try:
            # Get request details
            from pymongo import MongoClient
            import os
            from dotenv import load_dotenv
            
            load_dotenv()
            client = MongoClient(os.getenv('MONGODB_URI'))
            db = client.blood_donation
            
            notification = db.notifications.find_one({'request_id': request_id})
            if not notification:
                return {'success': False, 'error': 'Request not found'}
            
            blood_group = notification.get('data', {}).get('blood_group_needed', '')
            
            # Trigger PathFinder to plan route
            route_result = self.pathfinder.execute(donor_id, hospital_id, request_id)
            
            return {
                'success': True,
                'action': 'route_planned',
                'agent': 'pathfinder',
                'route': route_result.get('route', {}),
                'estimated_arrival': route_result.get('estimated_arrival')
            }
        except Exception as e:
            logger.error(f"Error handling donor acceptance: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def handle_donor_location_update(self, request_id: str, latitude: float, longitude: float):
        """Handle donor location update"""
        try:
            result = self.pathfinder.update_donor_location(
                request_id, latitude, longitude
            )
            return result
        except Exception as e:
            logger.error(f"Error updating location: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def handle_donor_arrival(self, request_id: str):
        """Handle donor arrival at hospital"""
        try:
            result = self.pathfinder.mark_arrival(request_id)
            return result
        except Exception as e:
            logger.error(f"Error marking arrival: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def predict_and_prepare(self):
        """Predict shortages and prepare in advance"""
        try:
            # AutoPulse predicts shortages
            predictions = self.autopulse.predict_shortages()
            
            # For each prediction, proactively check nearby hospitals
            for prediction in predictions:
                if prediction.get('will_be_low'):
                    self.linkbridge.execute(
                        prediction['hospital_id'],
                        prediction['blood_group'],
                        prediction.get('units_needed', 1)
                    )
            
            return {
                'success': True,
                'predictions': len(predictions),
                'prepared': True
            }
        except Exception as e:
            logger.error(f"Error in prediction and preparation: {str(e)}")
            return {'success': False, 'error': str(e)}


# Global orchestrator instance
orchestrator = AgentOrchestrator()

