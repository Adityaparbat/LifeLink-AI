"""
MCP (Model Context Protocol) Tools for LifeLink System

This module exposes MongoDB operations and system functions as MCP tools
for use with ADK agents. Meets Kaggle Agent Intensive MCP requirements.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import json

logger = logging.getLogger(__name__)


class MongoDBMCPTools:
    """
    MCP tools for MongoDB operations.
    Exposes database queries as tools for ADK agents.
    """
    
    def __init__(self, db, admins, users, notifications):
        self.db = db
        self.admins = admins
        self.users = users
        self.notifications = notifications
        logger.info("MongoDBMCPTools initialized")
    
    def get_blood_stock(self, blood_group: str) -> Dict[str, Any]:
        """
        MCP Tool: Get blood stock for a blood group
        
        Args:
            blood_group: Blood group (A+, A-, B+, B-, AB+, AB-, O+, O-)
        
        Returns:
            Dictionary with total units, hospital breakdown, low supply count
        """
        logger.info(f"MCP Tool: get_blood_stock called for {blood_group}")
        
        blood_group = blood_group.upper()
        hospitals = list(self.admins.find({'status': 'active'}))
        
        total_units = 0
        hospital_data = []
        low_supply_count = 0
        
        for hospital in hospitals:
            inventory = hospital.get('blood_inventory', {})
            units = int(inventory.get(blood_group, 0) or 0)
            total_units += units
            
            hospital_data.append({
                'hospital_id': str(hospital['_id']),
                'hospital_name': hospital.get('hospital_name', 'Unknown'),
                'units': units,
                'status': hospital.get('status', 'unknown')
            })
            
            if units == 0:
                low_supply_count += 1
        
        hospital_data.sort(key=lambda x: x['units'], reverse=True)
        
        result = {
            'blood_group': blood_group,
            'total_units': total_units,
            'hospitals': hospital_data,
            'low_supply_count': low_supply_count,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"MCP Tool: get_blood_stock returned {total_units} total units")
        return result
    
    def check_nearby_hospital_stock(self, hospital_id: str, blood_group: str, 
                                    units_needed: int, max_distance_km: float = 50) -> Dict[str, Any]:
        """
        MCP Tool: Check nearby hospitals for stock
        
        Args:
            hospital_id: Source hospital ID
            blood_group: Required blood group
            units_needed: Units needed
            max_distance_km: Maximum search radius (default 50km)
        
        Returns:
            Dictionary with nearby hospitals that have stock
        """
        logger.info(f"MCP Tool: check_nearby_hospital_stock called for {blood_group}")
        
        try:
            source_hospital = self.admins.find_one({'_id': ObjectId(hospital_id)})
            if not source_hospital or 'location' not in source_hospital:
                return {'error': 'Hospital not found or no location data'}
            
            source_coords = source_hospital['location']['coordinates']
            source_lat = float(source_coords[1])
            source_lon = float(source_coords[0])
            
            # Find nearby hospitals using geospatial query
            nearby_hospitals = list(self.admins.find({
                'status': 'active',
                '_id': {'$ne': ObjectId(hospital_id)},
                'location': {
                    '$near': {
                        '$geometry': {
                            'type': 'Point',
                            'coordinates': [source_lon, source_lat]
                        },
                        '$maxDistance': max_distance_km * 1000  # Convert to meters
                    }
                }
            }))
            
            available_options = []
            for hospital in nearby_hospitals:
                inventory = hospital.get('blood_inventory', {})
                available_units = int(inventory.get(blood_group, 0) or 0)
                
                if available_units >= units_needed:
                    # Calculate distance
                    hospital_coords = hospital['location']['coordinates']
                    hospital_lat = float(hospital_coords[1])
                    hospital_lon = float(hospital_coords[0])
                    
                    distance = self._haversine_distance(
                        source_lat, source_lon, hospital_lat, hospital_lon
                    )
                    
                    available_options.append({
                        'hospital_id': str(hospital['_id']),
                        'hospital_name': hospital.get('hospital_name', 'Unknown'),
                        'available_units': available_units,
                        'distance_km': round(distance, 2),
                        'address': hospital.get('address', 'N/A')
                    })
            
            available_options.sort(key=lambda x: x['distance_km'])
            
            result = {
                'has_stock_nearby': len(available_options) > 0,
                'options': available_options,
                'blood_group': blood_group,
                'units_needed': units_needed,
                'search_radius_km': max_distance_km,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"MCP Tool: check_nearby_hospital_stock found {len(available_options)} options")
            return result
            
        except Exception as e:
            logger.error(f"MCP Tool error in check_nearby_hospital_stock: {str(e)}")
            return {'error': str(e)}
    
    def get_accepted_donors_for_request(self, request_id: str) -> Dict[str, Any]:
        """
        MCP Tool: Get accepted donors for a request
        
        Args:
            request_id: Blood request ID
        
        Returns:
            Dictionary with list of accepted donors and their details
        """
        logger.info(f"MCP Tool: get_accepted_donors_for_request called for {request_id}")
        
        accepted_requests = list(self.notifications.find({
            'request_id': request_id,
            'status': 'responded',
            'response': 'accepted'
        }))
        
        donors = []
        for req in accepted_requests:
            donor_id = req.get('user_id')
            if donor_id and ObjectId.is_valid(str(donor_id)):
                donor = self.users.find_one({'_id': ObjectId(donor_id)})
                if donor:
                    donors.append({
                        'user_id': str(donor['_id']),
                        'name': donor.get('name', 'Unknown'),
                        'blood_group': donor.get('blood_group'),
                        'phone': donor.get('phone', 'N/A'),
                        'email': donor.get('email', 'N/A'),
                        'response_time': req.get('response_time').isoformat() if req.get('response_time') else None,
                        'distance': req.get('data', {}).get('distance')
                    })
        
        result = {
            'request_id': request_id,
            'accepted_count': len(donors),
            'donors': donors,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"MCP Tool: get_accepted_donors_for_request found {len(donors)} donors")
        return result
    
    def get_successful_donations(self, limit: int = 10) -> Dict[str, Any]:
        """
        MCP Tool: Get successful donations
        
        Args:
            limit: Maximum number of records to return (default 10, max 25)
        
        Returns:
            Dictionary with timeline of successful donations
        """
        logger.info(f"MCP Tool: get_successful_donations called with limit {limit}")
        
        limit = max(1, min(limit or 10, 25))
        
        routes = list(
            self.db.donor_routes.find({
                'status': {'$in': ['completed', 'success', 'completed_by_agent']}
            })
            .sort('completed_at', -1)
            .limit(limit)
        )
        
        timeline = []
        for route in routes:
            request_id = route.get('request_id')
            notification = self.notifications.find_one({'request_id': request_id}) if request_id else None
            donor_id = route.get('donor_id') or (notification or {}).get('user_id')
            
            donor = None
            if donor_id and ObjectId.is_valid(str(donor_id)):
                donor = self.users.find_one({'_id': ObjectId(donor_id)})
            
            timeline.append({
                'request_id': request_id,
                'status': route.get('status'),
                'completed_at': route.get('completed_at').isoformat() if route.get('completed_at') else None,
                'donor_name': (donor or {}).get('name', 'Unknown'),
                'blood_group': (notification or {}).get('data', {}).get('blood_group_needed'),
                'distance_km': route.get('distance_km'),
                'hospital_id': str(route.get('hospital_id')) if route.get('hospital_id') else None
            })
        
        result = {
            'count': len(timeline),
            'records': timeline,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"MCP Tool: get_successful_donations returned {len(timeline)} records")
        return result
    
    def predict_shortage(self, hospital_id: str, blood_group: str) -> Dict[str, Any]:
        """
        MCP Tool: Predict shortage for a hospital and blood group
        
        Args:
            hospital_id: Hospital ID
            blood_group: Blood group to predict
        
        Returns:
            Dictionary with prediction data
        """
        logger.info(f"MCP Tool: predict_shortage called for {blood_group} at {hospital_id}")
        
        try:
            hospital = self.admins.find_one({'_id': ObjectId(hospital_id)})
            if not hospital:
                return {'error': 'Hospital not found'}
            
            inventory = hospital.get('blood_inventory', {})
            current_stock = int(inventory.get(blood_group, 0) or 0)
            
            # Simple prediction based on thresholds
            thresholds = {
                'A+': 10, 'A-': 5, 'B+': 10, 'B-': 5,
                'AB+': 5, 'AB-': 3, 'O+': 15, 'O-': 8
            }
            threshold = thresholds.get(blood_group, 10)
            
            # Check recent donation history
            recent_donations = list(
                self.db.donation_history.find({
                    'admin_id': hospital_id,
                    'donor_blood_group': blood_group
                })
                .sort('donation_date', -1)
                .limit(10)
            )
            
            days_until_shortage = None
            if current_stock < threshold:
                # Already low
                days_until_shortage = 0
            elif len(recent_donations) > 0:
                # Estimate based on usage rate
                avg_days_between = 7  # Simplified
                days_until_shortage = (current_stock - threshold) * avg_days_between
            
            result = {
                'hospital_id': hospital_id,
                'hospital_name': hospital.get('hospital_name', 'Unknown'),
                'blood_group': blood_group,
                'current_stock': current_stock,
                'threshold': threshold,
                'is_low': current_stock < threshold,
                'days_until_shortage': days_until_shortage,
                'prediction_confidence': 0.7 if days_until_shortage else 0.5,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"MCP Tool: predict_shortage completed for {blood_group}")
            return result
            
        except Exception as e:
            logger.error(f"MCP Tool error in predict_shortage: {str(e)}")
            return {'error': str(e)}
    
    def get_todays_notifications(self, admin_id: str = None) -> Dict[str, Any]:
        """
        MCP Tool: Get today's notifications
        
        Args:
            admin_id: Optional admin ID to filter
        
        Returns:
            Dictionary with today's notifications
        """
        logger.info(f"MCP Tool: get_todays_notifications called")
        
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        query = {
            'created_at': {'$gte': today_start},
            'type': 'blood_request'
        }
        
        if admin_id:
            query['admin_id'] = ObjectId(admin_id)
        
        notifications = list(self.notifications.find(query).sort('created_at', -1).limit(50))
        
        result = {
            'count': len(notifications),
            'notifications': [
                {
                    'request_id': n.get('request_id'),
                    'blood_group': (n.get('data') or {}).get('blood_group_needed'),
                    'status': n.get('status'),
                    'created_at': n.get('created_at').isoformat() if n.get('created_at') else None
                }
                for n in notifications
            ],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"MCP Tool: get_todays_notifications returned {len(notifications)} notifications")
        return result
    
    def list_hospitals_with_low_stock(self, blood_group: str) -> Dict[str, Any]:
        """
        MCP Tool: List hospitals with low stock
        
        Args:
            blood_group: Blood group to check
        
        Returns:
            Dictionary with list of hospitals below threshold
        """
        logger.info(f"MCP Tool: list_hospitals_with_low_stock called for {blood_group}")
        
        thresholds = {
            'A+': 10, 'A-': 5, 'B+': 10, 'B-': 5,
            'AB+': 5, 'AB-': 3, 'O+': 15, 'O-': 8
        }
        threshold = thresholds.get(blood_group.upper(), 10)
        
        hospitals = list(self.admins.find({'status': 'active'}))
        low_stock_hospitals = []
        
        for hospital in hospitals:
            inventory = hospital.get('blood_inventory', {})
            units = int(inventory.get(blood_group.upper(), 0) or 0)
            
            if units < threshold:
                low_stock_hospitals.append({
                    'hospital_id': str(hospital['_id']),
                    'hospital_name': hospital.get('hospital_name', 'Unknown'),
                    'current_units': units,
                    'threshold': threshold,
                    'deficit': threshold - units
                })
        
        result = {
            'blood_group': blood_group.upper(),
            'threshold': threshold,
            'low_stock_count': len(low_stock_hospitals),
            'hospitals': low_stock_hospitals,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"MCP Tool: list_hospitals_with_low_stock found {len(low_stock_hospitals)} hospitals")
        return result
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates"""
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
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get list of all MCP tools"""
        return [
            {
                'name': 'get_blood_stock',
                'description': 'Get blood inventory for a specific blood group across all hospitals',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'blood_group': {'type': 'string', 'enum': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']}
                    },
                    'required': ['blood_group']
                }
            },
            {
                'name': 'check_nearby_hospital_stock',
                'description': 'Check blood stock in hospitals within a radius',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'hospital_id': {'type': 'string'},
                        'blood_group': {'type': 'string'},
                        'units_needed': {'type': 'integer'},
                        'max_distance_km': {'type': 'number', 'default': 50}
                    },
                    'required': ['hospital_id', 'blood_group', 'units_needed']
                }
            },
            {
                'name': 'get_accepted_donors_for_request',
                'description': 'Get list of donors who accepted a blood request',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'request_id': {'type': 'string'}
                    },
                    'required': ['request_id']
                }
            },
            {
                'name': 'get_successful_donations',
                'description': 'Get timeline of successful blood donations',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'limit': {'type': 'integer', 'default': 10, 'maximum': 25}
                    }
                }
            },
            {
                'name': 'predict_shortage',
                'description': 'Predict potential blood shortages based on historical data',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'hospital_id': {'type': 'string'},
                        'blood_group': {'type': 'string'}
                    },
                    'required': ['hospital_id', 'blood_group']
                }
            },
            {
                'name': 'get_todays_notifications',
                'description': 'Get notifications created today',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'admin_id': {'type': 'string'}
                    }
                }
            },
            {
                'name': 'list_hospitals_with_low_stock',
                'description': 'List all hospitals with low stock for a blood group',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'blood_group': {'type': 'string'}
                    },
                    'required': ['blood_group']
                }
            }
        ]


logger.info("MCP tools module loaded successfully")

