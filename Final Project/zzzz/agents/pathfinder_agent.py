"""
PathFinder Agent - Smart Logistics
Plans routes, tracks donor movement, and optimizes delivery
"""
from .base_agent import BaseAgent
from celery import shared_task
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import requests
import os
import logging

logger = logging.getLogger(__name__)


class PathFinderAgent(BaseAgent):
    """Agent that handles route planning and donor tracking"""
    
    def __init__(self):
        super().__init__("PathFinder")
        self.google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY', '')
        self.openroute_api_key = os.getenv('OPENROUTE_API_KEY', '')
    
    def execute(self, donor_id: str, hospital_id: str, request_id: str):
        """Plan route for donor to hospital"""
        try:
            print(f"[PathFinder] Executing for Request: {request_id}, Donor: {donor_id}, Hospital: {hospital_id}")
            donor = self.db.users.find_one({'_id': ObjectId(donor_id)})
            hospital = self.db.admins.find_one({'_id': ObjectId(hospital_id)})
            
            if not donor or not hospital:
                print(f"[PathFinder] Error: Donor or hospital not found. Donor: {donor}, Hospital: {hospital}")
                return {'success': False, 'error': 'Donor or hospital not found'}
            
            # Get locations
            donor_location = donor.get('location', {}).get('coordinates', [0, 0])
            hospital_location = hospital.get('location', {}).get('coordinates', [0, 0])
            print(f"[PathFinder] Locations - Donor: {donor_location}, Hospital: {hospital_location}")
            
            # Calculate route
            route = self._calculate_route(
                donor_location[1], donor_location[0],  # lat, lon
                hospital_location[1], hospital_location[0]
            )
            print(f"[PathFinder] Calculated Route: {route}")
            
            # Store route information
            route_data = {
                'request_id': request_id,
                'donor_id': donor_id,
                'hospital_id': hospital_id,
                'route': route,
                'status': 'active',
                'created_at': datetime.now(timezone.utc),
                'estimated_arrival': self._estimate_arrival_time(route),
                'last_updated': datetime.now(timezone.utc)
            }
            print(f"[PathFinder] Route Data to Save: {route_data}")
            
            # Update or insert route
            self.db.donor_routes.update_one(
                {'request_id': request_id},
                {'$set': route_data},
                upsert=True
            )
            
            # Start tracking
            self._start_tracking(donor_id, request_id)
            
            self.log_action('route_planned', {
                'request_id': request_id,
                'distance_km': route.get('distance_km', 0),
                'estimated_time_min': route.get('duration_min', 0)
            })
            
            return {
                'success': True,
                'route': route,
                'estimated_arrival': route_data['estimated_arrival']
            }
        except Exception as e:
            self.logger.error(f"Error planning route: {str(e)}")
            print(f"[PathFinder] Exception in execute: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _calculate_route(self, start_lat: float, start_lon: float,
                        end_lat: float, end_lon: float):
        """Calculate optimal route between two points"""
        try:
            print(f"[PathFinder] Calculating route from ({start_lat}, {start_lon}) to ({end_lat}, {end_lon})")
            # Try Google Maps API first
            if self.google_maps_api_key:
                print("[PathFinder] Using Google Maps API")
                route = self._get_google_maps_route(
                    start_lat, start_lon, end_lat, end_lon
                )
                if route:
                    return route
            
            # Fallback to OpenRouteService
            if self.openroute_api_key:
                print("[PathFinder] Using OpenRouteService API")
                route = self._get_openroute_route(
                    start_lat, start_lon, end_lat, end_lon
                )
                if route:
                    return route
            
            print("[PathFinder] Using Fallback (Haversine)")
            # Fallback: Use Haversine distance and estimate
            distance = self._haversine_distance(start_lat, start_lon, end_lat, end_lon)
            estimated_time = distance * 2  # Assume 30 km/h average speed
            
            return {
                'distance_km': round(distance, 2),
                'duration_min': int(estimated_time),
                'route_type': 'estimated',
                'waypoints': [
                    {'lat': start_lat, 'lon': start_lon},
                    {'lat': end_lat, 'lon': end_lon}
                ]
            }
        except Exception as e:
            self.logger.error(f"Error calculating route: {str(e)}")
            print(f"[PathFinder] Exception in _calculate_route: {str(e)}")
            # Return basic route
            distance = self._haversine_distance(start_lat, start_lon, end_lat, end_lon)
            return {
                'distance_km': round(distance, 2),
                'duration_min': int(distance * 2),
                'route_type': 'fallback'
            }
    
    def _get_google_maps_route(self, start_lat: float, start_lon: float,
                               end_lat: float, end_lon: float):
        """Get route from Google Maps API"""
        try:
            url = "https://maps.googleapis.com/maps/api/directions/json"
            params = {
                'origin': f"{start_lat},{start_lon}",
                'destination': f"{end_lat},{end_lon}",
                'key': self.google_maps_api_key,
                'mode': 'driving',
                'alternatives': 'false'
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('routes'):
                    route = data['routes'][0]
                    leg = route['legs'][0]
                    
                    return {
                        'distance_km': round(leg['distance']['value'] / 1000, 2),
                        'duration_min': int(leg['duration']['value'] / 60),
                        'route_type': 'google_maps',
                        'polyline': route.get('overview_polyline', {}).get('points', ''),
                        'waypoints': [
                            {'lat': start_lat, 'lon': start_lon},
                            {'lat': end_lat, 'lon': end_lon}
                        ]
                    }
        except Exception as e:
            self.logger.error(f"Error getting Google Maps route: {str(e)}")
        
        return None
    
    def _get_openroute_route(self, start_lat: float, start_lon: float,
                            end_lat: float, end_lon: float):
        """Get route from OpenRouteService API"""
        try:
            url = "https://api.openrouteservice.org/v2/directions/driving-car"
            headers = {
                'Authorization': self.openroute_api_key,
                'Content-Type': 'application/json'
            }
            params = {
                'coordinates': [[start_lon, start_lat], [end_lon, end_lat]]
            }
            
            response = requests.post(url, json=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('routes'):
                    route = data['routes'][0]
                    summary = route['summary']
                    
                    return {
                        'distance_km': round(summary['distance'] / 1000, 2),
                        'duration_min': int(summary['duration'] / 60),
                        'route_type': 'openroute',
                        'geometry': route.get('geometry', ''),
                        'waypoints': [
                            {'lat': start_lat, 'lon': start_lon},
                            {'lat': end_lat, 'lon': end_lon}
                        ]
                    }
        except Exception as e:
            self.logger.error(f"Error getting OpenRoute route: {str(e)}")
        
        return None
    
    def _estimate_arrival_time(self, route: dict):
        """Estimate arrival time based on route"""
        try:
            duration_min = route.get('duration_min', 0)
            estimated_arrival = datetime.now(timezone.utc) + timedelta(minutes=duration_min)
            return estimated_arrival.isoformat()
        except Exception as e:
            self.logger.error(f"Error estimating arrival: {str(e)}")
            return None
    
    def _start_tracking(self, donor_id: str, request_id: str):
        """Start tracking donor movement"""
        try:
            tracking_data = {
                'donor_id': donor_id,
                'request_id': request_id,
                'status': 'tracking',
                'started_at': datetime.now(timezone.utc),
                'last_location': None,
                'estimated_arrival': None,
                'actual_arrival': None
            }
            
            self.db.donor_tracking.update_one(
                {'request_id': request_id},
                {'$set': tracking_data},
                upsert=True
            )
        except Exception as e:
            self.logger.error(f"Error starting tracking: {str(e)}")
    
    def update_donor_location(self, request_id: str, latitude: float, longitude: float):
        """Update donor's current location"""
        try:
            tracking = self.db.donor_tracking.find_one({'request_id': request_id})
            if not tracking:
                return {'success': False, 'error': 'Tracking not found'}
            
            # Get route
            route = self.db.donor_routes.find_one({'request_id': request_id})
            if not route:
                return {'success': False, 'error': 'Route not found'}
            
            # Get hospital location
            hospital = self.db.admins.find_one({'_id': ObjectId(route['hospital_id'])})
            if not hospital or 'location' not in hospital:
                return {'success': False, 'error': 'Hospital location not found'}
            
            hospital_coords = hospital['location']['coordinates']
            hospital_lat = float(hospital_coords[1])
            hospital_lon = float(hospital_coords[0])
            
            # Calculate remaining distance
            remaining_distance = self._haversine_distance(
                latitude, longitude, hospital_lat, hospital_lon
            )
            
            # Estimate remaining time (assuming 30 km/h average)
            estimated_remaining_min = int(remaining_distance * 2)
            
            # Update tracking
            self.db.donor_tracking.update_one(
                {'request_id': request_id},
                {'$set': {
                    'last_location': {
                        'latitude': latitude,
                        'longitude': longitude,
                        'timestamp': datetime.now(timezone.utc)
                    },
                    'remaining_distance_km': round(remaining_distance, 2),
                    'estimated_remaining_min': estimated_remaining_min,
                    'last_updated': datetime.now(timezone.utc)
                }}
            )
            
            # Update hospital dashboard
            self._update_hospital_dashboard(route['hospital_id'], request_id, {
                'current_location': {'lat': latitude, 'lon': longitude},
                'remaining_distance_km': round(remaining_distance, 2),
                'estimated_arrival_min': estimated_remaining_min
            })
            
            # Check if donor is delayed
            if estimated_remaining_min > route.get('duration_min', 0) * 1.5:
                self._handle_delay(request_id, route)
            
            return {
                'success': True,
                'remaining_distance_km': round(remaining_distance, 2),
                'estimated_arrival_min': estimated_remaining_min
            }
        except Exception as e:
            self.logger.error(f"Error updating location: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _update_hospital_dashboard(self, hospital_id: str, request_id: str, data: dict):
        """Update hospital dashboard with donor location"""
        try:
            # Store in real-time updates collection
            self.db.realtime_updates.update_one(
                {'request_id': request_id},
                {'$set': {
                    'hospital_id': hospital_id,
                    'request_id': request_id,
                    'data': data,
                    'updated_at': datetime.now(timezone.utc)
                }},
                upsert=True
            )
        except Exception as e:
            self.logger.error(f"Error updating dashboard: {str(e)}")
    
    def _handle_delay(self, request_id: str, route: dict):
        """Handle donor delay - reroute or assign backup"""
        try:
            # Check if delay is significant
            tracking = self.db.donor_tracking.find_one({'request_id': request_id})
            if not tracking:
                return
            
            remaining_min = tracking.get('estimated_remaining_min', 0)
            original_duration = route.get('duration_min', 0)
            
            if remaining_min > original_duration * 1.5:
                # Significant delay - consider backup donor
                self.logger.warning(f"Donor delay detected for request {request_id}")
                
                # Option 1: Recalculate route
                if tracking.get('last_location'):
                    last_loc = tracking['last_location']
                    hospital = self.db.admins.find_one({'_id': ObjectId(route['hospital_id'])})
                    if hospital and 'location' in hospital:
                        hospital_coords = hospital['location']['coordinates']
                        new_route = self._calculate_route(
                            last_loc['latitude'], last_loc['longitude'],
                            float(hospital_coords[1]), float(hospital_coords[0])
                        )
                        
                        # Update route
                        self.db.donor_routes.update_one(
                            {'request_id': request_id},
                            {'$set': {
                                'route': new_route,
                                'last_updated': datetime.now(timezone.utc)
                            }}
                        )
                
                # Option 2: Trigger backup donor search (can be done by AutoPulse)
                notification = self.db.notifications.find_one({'request_id': request_id})
                if notification:
                    # Trigger backup search
                    from agents.autopulse_agent import AutoPulseAgent
                    autopulse = AutoPulseAgent()
                    autopulse._auto_contact_donors(
                        route['hospital_id'],
                        notification.get('data', {}).get('blood_group_needed', ''),
                        1  # Need 1 unit as backup
                    )
        except Exception as e:
            self.logger.error(f"Error handling delay: {str(e)}")
    
    def update_active_routes(self):
        """Update all active routes with latest traffic data"""
        try:
            active_routes = list(self.db.donor_routes.find({
                'status': 'active',
                'created_at': {
                    '$gte': datetime.now(timezone.utc) - timedelta(hours=24)
                }
            }))
            
            updated_count = 0
            for route in active_routes:
                try:
                    # Recalculate route with latest traffic
                    donor = self.db.users.find_one({'_id': ObjectId(route['donor_id'])})
                    hospital = self.db.admins.find_one({'_id': ObjectId(route['hospital_id'])})
                    
                    if donor and hospital:
                        donor_coords = donor['location']['coordinates']
                        hospital_coords = hospital['location']['coordinates']
                        
                        new_route = self._calculate_route(
                            float(donor_coords[1]), float(donor_coords[0]),
                            float(hospital_coords[1]), float(hospital_coords[0])
                        )
                        
                        # Update if route changed significantly
                        old_duration = route.get('route', {}).get('duration_min', 0)
                        new_duration = new_route.get('duration_min', 0)
                        
                        if abs(new_duration - old_duration) > 5:  # More than 5 min difference
                            self.db.donor_routes.update_one(
                                {'_id': route['_id']},
                                {'$set': {
                                    'route': new_route,
                                    'estimated_arrival': self._estimate_arrival_time(new_route),
                                    'last_updated': datetime.now(timezone.utc)
                                }}
                            )
                            updated_count += 1
                except Exception as e:
                    self.logger.error(f"Error updating route {route.get('_id')}: {str(e)}")
                    continue
            
            self.log_action('updated_routes', {
                'routes_checked': len(active_routes),
                'routes_updated': updated_count
            })
            
            return {'updated': updated_count, 'checked': len(active_routes)}
        except Exception as e:
            self.logger.error(f"Error updating active routes: {str(e)}")
            return {'error': str(e)}
    
    def mark_arrival(self, request_id: str):
        """Mark donor as arrived at hospital"""
        try:
            self.db.donor_tracking.update_one(
                {'request_id': request_id},
                {'$set': {
                    'actual_arrival': datetime.now(timezone.utc),
                    'status': 'arrived',
                    'last_updated': datetime.now(timezone.utc)
                }}
            )
            
            self.db.donor_routes.update_one(
                {'request_id': request_id},
                {'$set': {
                    'status': 'completed',
                    'completed_at': datetime.now(timezone.utc)
                }}
            )
            
            self.log_action('donor_arrived', {'request_id': request_id})
            return {'success': True}
        except Exception as e:
            self.logger.error(f"Error marking arrival: {str(e)}")
            return {'success': False, 'error': str(e)}


# Celery tasks
@shared_task(name='agents.pathfinder_agent.plan_route')
def plan_route(donor_id: str, hospital_id: str, request_id: str):
    """Celery task to plan route"""
    agent = PathFinderAgent()
    return agent.execute(donor_id, hospital_id, request_id)


@shared_task(name='agents.pathfinder_agent.update_active_routes')
def update_active_routes():
    """Celery task to update active routes"""
    agent = PathFinderAgent()
    return agent.update_active_routes()


@shared_task(name='agents.pathfinder_agent.update_location')
def update_location(request_id: str, latitude: float, longitude: float):
    """Celery task to update donor location"""
    agent = PathFinderAgent()
    return agent.update_donor_location(request_id, latitude, longitude)


@shared_task(name='agents.pathfinder_agent.mark_arrival')
def mark_arrival(request_id: str):
    """Celery task to mark donor arrival"""
    agent = PathFinderAgent()
    return agent.mark_arrival(request_id)

