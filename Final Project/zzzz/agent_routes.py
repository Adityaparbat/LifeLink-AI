"""
Agent API Routes - Integration endpoints for agents
"""
from flask import Blueprint, request, jsonify, session
from agent_orchestrator import orchestrator
from agents.autopulse_agent import monitor_inventory, predict_shortages
from agents.rapidaid_agent import check_emergencies, handle_emergency
from agents.pathfinder_agent import plan_route, update_location, mark_arrival
from agents.linkbridge_agent import check_nearby_stock_task as check_nearby_stock, coordinate_transfer_task as coordinate_transfer
from bson import ObjectId
from utils import admin_required
import logging

logger = logging.getLogger(__name__)

agent_bp = Blueprint('agents', __name__, url_prefix='/api/agents')


@agent_bp.route('/autopulse/monitor', methods=['POST'])
@admin_required
def trigger_autopulse():
    """Manually trigger AutoPulse agent"""
    try:
        data = request.get_json()
        admin_id = data.get('admin_id') or session.get('admin')
        
        if not admin_id:
            return jsonify({'error': 'Admin ID required'}), 400
        
        # Trigger Celery task
        task = monitor_inventory.delay(admin_id)
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'AutoPulse monitoring started'
        })
    except Exception as e:
        logger.error(f"Error triggering AutoPulse: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/autopulse/predict', methods=['POST'])
@admin_required
def trigger_prediction():
    """Trigger shortage prediction"""
    try:
        task = predict_shortages.delay()
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Shortage prediction started'
        })
    except Exception as e:
        logger.error(f"Error triggering prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/rapidaid/emergency', methods=['POST'])
@admin_required
def trigger_rapidaid():
    """Trigger RapidAid agent for emergency"""
    try:
        data = request.get_json()
        
        required_fields = ['hospital_id', 'blood_group', 'units_needed']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        emergency_data = {
            'type': 'manual',
            'hospital_id': data['hospital_id'],
            'blood_group': data['blood_group'],
            'units_needed': data['units_needed'],
            'location': data.get('location'),
            'severity': data.get('severity', 'high'),
            'description': data.get('description', 'Emergency blood request')
        }
        
        task = handle_emergency.delay(emergency_data)
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'RapidAid emergency response initiated'
        })
    except Exception as e:
        logger.error(f"Error triggering RapidAid: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/pathfinder/plan-route', methods=['POST'])
def trigger_pathfinder():
    """Trigger PathFinder to plan route"""
    try:
        data = request.get_json()
        
        required_fields = ['donor_id', 'hospital_id', 'request_id']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        task = plan_route.delay(
            data['donor_id'],
            data['hospital_id'],
            data['request_id']
        )
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Route planning started'
        })
    except Exception as e:
        logger.error(f"Error triggering PathFinder: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/pathfinder/update-location', methods=['POST'])
def update_donor_location():
    """Update donor location"""
    try:
        data = request.get_json()
        
        required_fields = ['request_id', 'latitude', 'longitude']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        task = update_location.delay(
            data['request_id'],
            float(data['latitude']),
            float(data['longitude'])
        )
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Location update processed'
        })
    except Exception as e:
        logger.error(f"Error updating location: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/pathfinder/arrival', methods=['POST'])
def mark_donor_arrival():
    """Mark donor as arrived"""
    try:
        data = request.get_json()
        request_id = data.get('request_id')
        
        if not request_id:
            return jsonify({'error': 'Request ID required'}), 400
        
        task = mark_arrival.delay(request_id)
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Arrival marked'
        })
    except Exception as e:
        logger.error(f"Error marking arrival: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/linkbridge/check-stock', methods=['POST'])
@admin_required
def trigger_linkbridge():
    """Trigger LinkBridge to check nearby hospitals"""
    try:
        data = request.get_json()
        
        required_fields = ['hospital_id', 'blood_group', 'units_needed']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        task = coordinate_transfer.delay(
            data['hospital_id'],
            data['blood_group'],
            data['units_needed']
        )
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': 'Nearby stock check initiated'
        })
    except Exception as e:
        logger.error(f"Error triggering LinkBridge: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/orchestrator/low-inventory', methods=['POST'])
@admin_required
def handle_low_inventory():
    """Orchestrate response to low inventory"""
    try:
        data = request.get_json()
        
        required_fields = ['hospital_id', 'blood_group', 'units_needed']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        result = orchestrator.handle_low_inventory(
            data['hospital_id'],
            data['blood_group'],
            data['units_needed']
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error handling low inventory: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/orchestrator/emergency', methods=['POST'])
@admin_required
def handle_emergency_orchestrated():
    """Orchestrate emergency response"""
    try:
        data = request.get_json()
        
        required_fields = ['hospital_id', 'blood_group', 'units_needed']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        emergency_data = {
            'type': data.get('type', 'manual'),
            'hospital_id': data['hospital_id'],
            'blood_group': data['blood_group'],
            'units_needed': data['units_needed'],
            'location': data.get('location'),
            'severity': data.get('severity', 'high'),
            'description': data.get('description', 'Emergency blood request')
        }
        
        result = orchestrator.handle_emergency(emergency_data)
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error handling emergency: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/orchestrator/donor-accepted', methods=['POST'])
def handle_donor_accepted():
    """Handle when donor accepts request"""
    try:
        data = request.get_json()
        
        required_fields = ['request_id', 'donor_id', 'hospital_id']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        result = orchestrator.handle_donor_accepted(
            data['request_id'],
            data['donor_id'],
            data['hospital_id']
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error handling donor acceptance: {str(e)}")
        return jsonify({'error': str(e)}), 500


@agent_bp.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get status of a Celery task"""
    try:
        from celery_app import celery_app
        task = celery_app.AsyncResult(task_id)
        
        return jsonify({
            'task_id': task_id,
            'status': task.status,
            'result': task.result if task.ready() else None
        })
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return jsonify({'error': str(e)}), 500

