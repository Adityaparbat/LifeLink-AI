"""
LinkBridge Agent - Hospital Coordination
Checks nearby hospitals for stock, coordinates transfers
Matches MongoDB structure:
  Database: blood_donation
  Collection: admins
  Each admin document contains: blood_inventory (dict), location (GeoJSON), hospital_name, hospital_id, status
Reference screenshot (uploaded): /mnt/data/224aa89e-c042-4ebf-bd2e-3cfdf3802c68.png
"""
from .base_agent import BaseAgent
from celery import shared_task
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import ReturnDocument
import logging
import math

logger = logging.getLogger(__name__)


class LinkBridgeAgent(BaseAgent):
    def __init__(self):
        super().__init__("LinkBridge")

        # shorthand to hospitals collection (matches your cluster structure)
        self._admins_col = self.db['blood_donation']['admins']

        # FIXED: direct collection access (no .get())
        self._requests_col = self.db['blood_donation']['inter_hospital_requests']
        self._admin_notifications_col = self.db['blood_donation']['admin_notifications']
        self._notifications_col = self.db['blood_donation']['notifications']

    # ---------- Public API ----------
    def execute(self, hospital_id: str, blood_group: str, units_needed: int):
        """Check nearby hospitals and coordinate transfer"""
        try:
            requesting_hospital = self._get_hospital_doc(hospital_id)
            if not requesting_hospital:
                return {'success': False, 'error': 'Hospital not found'}

            if 'location' not in requesting_hospital:
                return {'success': False, 'error': 'Hospital location not found'}

            req_coords = requesting_hospital['location']['coordinates']
            req_lat = float(req_coords[1])
            req_lon = float(req_coords[0])

            nearby_hospitals = self._find_nearby_hospitals(
                req_lat, req_lon, max_distance_km=50, exclude_hospital_id=hospital_id
            )

            available_stock = []
            for hospital in nearby_hospitals:
                stock_info = self._check_hospital_stock(hospital, blood_group, units_needed)
                if stock_info.get('has_stock'):
                    available_stock.append({
                        'hospital_id': str(hospital['_id']),
                        'hospital_name': hospital.get('hospital_name', 'Unknown'),
                        'hospital_id_code': hospital.get('hospital_id', 'N/A'),
                        'distance_km': stock_info.get('distance'),
                        'available_units': stock_info.get('available_units'),
                        'location': hospital.get('location', {}).get('address', 'N/A')
                    })

            available_stock.sort(key=lambda x: x['distance_km'])

            if available_stock:
                result = {
                    'success': True,
                    'has_stock_nearby': True,
                    'options': available_stock,
                    'recommended': available_stock[0]
                }

                recommended = available_stock[0]
                self._create_transfer_request(
                    from_hospital_id=hospital_id,
                    to_hospital_id=recommended['hospital_id'],
                    blood_group=blood_group,
                    units=units_needed
                )
            else:
                result = {
                    'success': True,
                    'has_stock_nearby': False,
                    'message': 'No stock found in nearby hospitals. Triggering donor search.',
                    'autopulse_triggered': True
                }

                try:
                    from agents.autopulse_agent import AutoPulseAgent
                    autopulse = AutoPulseAgent()
                    autopulse._auto_contact_donors(hospital_id, blood_group, units_needed)
                except Exception as ex:
                    logger.exception("Failed to trigger AutoPulseAgent: %s", ex)

            self.log_action('checked_nearby_stock', {
                'hospital_id': hospital_id,
                'blood_group': blood_group,
                'units_needed': units_needed,
                'hospitals_checked': len(nearby_hospitals),
                'hospitals_with_stock': len(available_stock)
            })

            return result

        except Exception as e:
            logger.exception("Error checking nearby hospitals: %s", e)
            return {'success': False, 'error': str(e)}

    # ---------- Helper DB / domain methods ----------
    def _get_hospital_doc(self, hospital_id: str):
        try:
            return self._admins_col.find_one({'_id': ObjectId(hospital_id)})
        except Exception:
            return None

    def _find_nearby_hospitals(self, latitude: float, longitude: float,
                               max_distance_km: float = 50,
                               exclude_hospital_id: str = None):
        try:
            query = {'status': 'active'}
            if exclude_hospital_id:
                try:
                    query['_id'] = {'$ne': ObjectId(exclude_hospital_id)}
                except Exception:
                    pass

            hospitals = list(self._admins_col.find(query))
            nearby = []
            for hospital in hospitals:
                if 'location' not in hospital:
                    continue
                coords = hospital['location']['coordinates']
                hospital_lat = float(coords[1])
                hospital_lon = float(coords[0])
                distance = self._haversine_distance(latitude, longitude, hospital_lat, hospital_lon)
                if distance <= max_distance_km:
                    hospital['distance'] = distance
                    nearby.append(hospital)
            nearby.sort(key=lambda x: x.get('distance', 999))
            return nearby
        except Exception as e:
            logger.exception("Error finding nearby hospitals: %s", e)
            return []

    def _check_hospital_stock(self, hospital_doc: dict, blood_group: str, units_needed: int):
        try:
            hospital_id = str(hospital_doc['_id'])
            inventory = hospital_doc.get('blood_inventory')
            if inventory is None:
                doc = self._admins_col.find_one({'_id': ObjectId(hospital_id)}, {'blood_inventory': 1})
                inventory = doc.get('blood_inventory', {}) if doc else {}

            available_units = int(inventory.get(blood_group, 0))
            has_stock = available_units >= units_needed
            distance = float(hospital_doc.get('distance', 0.0))
            return {
                'has_stock': has_stock,
                'available_units': available_units,
                'distance': distance
            }
        except Exception as e:
            logger.exception("Error checking stock for hospital %s: %s", hospital_doc.get('_id'), e)
            return {'has_stock': False, 'available_units': 0, 'distance': hospital_doc.get('distance', 0)}

    def get_hospital_inventory(self, hospital_id: str):
        try:
            doc = self._admins_col.find_one({'_id': ObjectId(hospital_id)}, {'blood_inventory': 1})
            return doc.get('blood_inventory', {}) if doc else {}
        except Exception:
            return {}

    def _create_transfer_request(self, from_hospital_id: str, to_hospital_id: str,
                                 blood_group: str, units: int):
        try:
            existing = self._requests_col.find_one({
                'from_admin': from_hospital_id,
                'to_admin': to_hospital_id,
                'blood_group': blood_group,
                'status': 'pending'
            })
            if existing:
                return {'success': False, 'error': 'Request already exists'}

            request_doc = {
                'from_admin': from_hospital_id,
                'to_admin': to_hospital_id,
                'blood_group': blood_group,
                'units': units,
                'status': 'pending',
                'created_at': datetime.now(timezone.utc),
                'response': None,
                'response_message': None,
                'response_time': None,
                'transfer_type': 'linkbridge_auto',
                'agent': 'linkbridge'
            }
            result = self._requests_col.insert_one(request_doc)

            receiving_hospital = self._get_hospital_doc(to_hospital_id)
            if receiving_hospital:
                notification = {
                    'admin_id': to_hospital_id,
                    'type': 'inter_hospital_request',
                    'title': f"Blood Transfer Request - {blood_group}",
                    'body': f"Request for {units} units of {blood_group} blood.",
                    'data': {
                        'request_id': str(result.inserted_id),
                        'from_hospital_id': from_hospital_id,
                        'blood_group': blood_group,
                        'units': units
                    },
                    'created_at': datetime.now(timezone.utc),
                    'read': False,
                    'status': 'pending'
                }
                self._admin_notifications_col.insert_one(notification)

            self.log_action('transfer_request_created', {
                'request_id': str(result.inserted_id),
                'from_hospital': from_hospital_id,
                'to_hospital': to_hospital_id,
                'blood_group': blood_group,
                'units': units
            })
            return {'success': True, 'request_id': str(result.inserted_id)}
        except Exception as e:
            logger.exception("Error creating transfer request: %s", e)
            return {'success': False, 'error': str(e)}

    # ---------- Transfer processing ----------
    def process_transfer(self, request_id: str, action: str, message: str = ''):
        try:
            request = self._requests_col.find_one({'_id': ObjectId(request_id)})
            if not request:
                return {'success': False, 'error': 'Request not found'}
            if request.get('status') != 'pending':
                return {'success': False, 'error': 'Request already processed'}

            if action == 'accept':
                to_hospital_id = request['to_admin']
                blood_group = request['blood_group']
                units = int(request['units'])

                filter_query = {
                    '_id': ObjectId(to_hospital_id),
                    f'blood_inventory.{blood_group}': {'$gte': units}
                }
                update_op = {'$inc': {f'blood_inventory.{blood_group}': -units}}
                updated = self._admins_col.find_one_and_update(
                    filter_query,
                    update_op,
                    return_document=ReturnDocument.AFTER
                )

                if not updated:
                    return {'success': False, 'error': 'Insufficient stock at providing hospital'}

                from_hospital_id = request['from_admin']
                self._admins_col.update_one(
                    {'_id': ObjectId(from_hospital_id)},
                    {'$inc': {f'blood_inventory.{blood_group}': units}}
                )

                self._requests_col.update_one(
                    {'_id': ObjectId(request_id)},
                    {'$set': {
                        'status': 'accepted',
                        'response': 'accepted',
                        'response_message': message,
                        'response_time': datetime.now(timezone.utc),
                        'processed_at': datetime.now(timezone.utc)
                    }}
                )

                self.log_action('transfer_accepted', {
                    'request_id': request_id,
                    'from_hospital': from_hospital_id,
                    'to_hospital': to_hospital_id,
                    'blood_group': blood_group,
                    'units': units
                })
                return {'success': True, 'message': 'Transfer accepted and processed'}

            elif action == 'reject':
                self._requests_col.update_one(
                    {'_id': ObjectId(request_id)},
                    {'$set': {
                        'status': 'rejected',
                        'response': 'rejected',
                        'response_message': message,
                        'response_time': datetime.now(timezone.utc)
                    }}
                )

                try:
                    from agents.autopulse_agent import AutoPulseAgent
                    autopulse = AutoPulseAgent()
                    autopulse._auto_contact_donors(request['from_admin'], request['blood_group'], request['units'])
                except Exception as ex:
                    logger.exception("Failed to trigger AutoPulseAgent on rejection: %s", ex)

                self.log_action('transfer_rejected', {
                    'request_id': request_id,
                    'reason': message
                })
                return {'success': True, 'message': 'Transfer rejected'}

            else:
                return {'success': False, 'error': 'Invalid action'}
        except Exception as e:
            logger.exception("Error processing transfer: %s", e)
            return {'success': False, 'error': str(e)}

    # ---------- Periodic check ----------
    def check_nearby_stock(self):
        try:
            admins_cursor = self._admins_col.find({'status': 'active'})
            checked_count = 0
            found_stock_count = 0

            thresholds = {
                'A+': 10, 'A-': 5, 'B+': 10, 'B-': 5,
                'AB+': 5, 'AB-': 3, 'O+': 15, 'O-': 8
            }

            for hospital in admins_cursor:
                hospital_id = str(hospital['_id'])
                inventory = hospital.get('blood_inventory', {})
                if not inventory:
                    continue

                for blood_group, threshold in thresholds.items():
                    current_stock = int(inventory.get(blood_group, 0))
                    if current_stock < threshold:
                        checked_count += 1
                        result = self.execute(hospital_id, blood_group, threshold - current_stock)
                        if result.get('has_stock_nearby'):
                            found_stock_count += 1

            self.log_action('periodic_stock_check', {
                'hospitals_checked': checked_count,
                'stock_found': found_stock_count
            })
            return {'checked': checked_count, 'found_stock': found_stock_count}
        except Exception as e:
            logger.exception("Error in periodic stock check: %s", e)
            return {'error': str(e)}

    # ---------- Utilities ----------
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


# Celery tasks
@shared_task(name='agents.linkbridge_agent.check_nearby_stock')
def check_nearby_stock_task():
    agent = LinkBridgeAgent()
    return agent.check_nearby_stock()


@shared_task(name='agents.linkbridge_agent.coordinate_transfer')
def coordinate_transfer_task(hospital_id: str, blood_group: str, units_needed: int):
    agent = LinkBridgeAgent()
    return agent.execute(hospital_id, blood_group, units_needed)
