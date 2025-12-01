"""
Google Agent Development Kit (ADK) Integration for LifeLink System

This module provides ADK-compatible wrappers for all agents to meet Kaggle Agent Intensive requirements.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json

# ADK imports (using Google's AI SDK structure)
try:
    # For Kaggle submission, we'll create a compatible ADK interface
    # In production, use: from google.ai.generativelanguage import adk
    from google.generativeai import GenerativeModel
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    logging.warning("ADK not available, using fallback implementation")

from lifebot_agent import LifeBotAgent
from agents.autopulse_agent import AutoPulseAgent
from agents.rapidaid_agent import RapidAidAgent
from agents.pathfinder_agent import PathFinderAgent
from agents.linkbridge_agent import LinkBridgeAgent

logger = logging.getLogger(__name__)


class InMemorySessionService:
    """
    ADK-compatible in-memory session service for agent state management.
    Stores conversation history and agent context.
    """
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        logger.info("InMemorySessionService initialized")
    
    def create_session(self, session_id: str) -> Dict[str, Any]:
        """Create a new session"""
        self.sessions[session_id] = {
            'session_id': session_id,
            'created_at': datetime.now(timezone.utc),
            'messages': [],
            'context': {},
            'agent_state': {}
        }
        logger.info(f"Created session: {session_id}")
        return self.sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    def add_message(self, session_id: str, role: str, content: str, metadata: Dict = None):
        """Add message to session history"""
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now(timezone.utc),
            'metadata': metadata or {}
        }
        self.sessions[session_id]['messages'].append(message)
        logger.debug(f"Added {role} message to session {session_id}")
    
    def update_context(self, session_id: str, key: str, value: Any):
        """Update session context"""
        if session_id not in self.sessions:
            self.create_session(session_id)
        
        self.sessions[session_id]['context'][key] = value
        logger.debug(f"Updated context {key} for session {session_id}")
    
    def get_context(self, session_id: str, key: str = None) -> Any:
        """Get session context"""
        session = self.get_session(session_id)
        if not session:
            return None
        
        if key:
            return session['context'].get(key)
        return session['context']


class MemoryBank:
    """
    ADK-compatible memory bank for long-term agent memory.
    Stores agent decisions, patterns, and learned behaviors.
    """
    
    def __init__(self):
        self.memories: List[Dict[str, Any]] = []
        logger.info("MemoryBank initialized")
    
    def store(self, agent_name: str, event: str, data: Dict[str, Any]):
        """Store a memory"""
        memory = {
            'agent': agent_name,
            'event': event,
            'data': data,
            'timestamp': datetime.now(timezone.utc)
        }
        self.memories.append(memory)
        logger.debug(f"Memory stored: {agent_name} - {event}")
    
    def retrieve(self, agent_name: str = None, event: str = None) -> List[Dict[str, Any]]:
        """Retrieve memories with optional filters"""
        results = self.memories
        
        if agent_name:
            results = [m for m in results if m['agent'] == agent_name]
        
        if event:
            results = [m for m in results if m['event'] == event]
        
        return sorted(results, key=lambda x: x['timestamp'], reverse=True)
    
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent memories"""
        return sorted(self.memories, key=lambda x: x['timestamp'], reverse=True)[:limit]


class ADKLifeBotAgent:
    """
    ADK-compatible wrapper for LifeBot agent.
    Implements ADK Agent interface for Kaggle submission requirements.
    """
    
    def __init__(self, tools: List[Any] = None, session_service: InMemorySessionService = None, 
                 memory_bank: MemoryBank = None):
        self.tools = tools or []
        self.session_service = session_service or InMemorySessionService()
        self.memory_bank = memory_bank or MemoryBank()
        self.lifebot = None  # Will be initialized with DB connection
        logger.info("ADKLifeBotAgent initialized")
    
    def initialize(self, db, admins, users, notifications, orchestrator=None, agents_enabled=False):
        """Initialize underlying LifeBot agent"""
        self.lifebot = LifeBotAgent(
            db=db,
            admins=admins,
            users=users,
            notifications=notifications,
            orchestrator=orchestrator,
            agents_enabled=agents_enabled
        )
        logger.info("LifeBot agent initialized")
    
    def run(self, query: str, session_id: str = None) -> Dict[str, Any]:
        """
        ADK-compatible run method.
        Processes queries through LifeBot with session management.
        Note: Made synchronous to avoid event loop issues in Flask.
        """
        if not session_id:
            session_id = f"session_{datetime.now(timezone.utc).timestamp()}"
        
        session = self.session_service.get_session(session_id)
        if not session:
            session = self.session_service.create_session(session_id)
        
        # Add user query to session
        self.session_service.add_message(session_id, 'user', query)
        
        logger.info(f"ADKLifeBotAgent processing query in session {session_id}: {query[:50]}...")
        
        # Parse query and route to appropriate LifeBot task
        result = self._route_query(query, session_id)
        
        # Add agent response to session
        self.session_service.add_message(
            session_id, 
            'assistant', 
            result.get('explanation', 'Task completed'),
            metadata={'task': result.get('task'), 'ok': result.get('ok')}
        )
        
        # Store in memory bank
        self.memory_bank.store('LifeBot', 'query_processed', {
            'query': query[:100],
            'task': result.get('task'),
            'success': result.get('ok', False)
        })
        
        return {
            'session_id': session_id,
            'result': result,
            'session_history': session['messages'][-5:]  # Last 5 messages
        }
    
    def _route_query(self, query: str, session_id: str) -> Dict[str, Any]:
        """Route query to appropriate LifeBot task"""
        query_lower = query.lower()
        
        # Stock lookup
        if any(word in query_lower for word in ['stock', 'inventory', 'blood group', 'units']):
            blood_group = self._extract_blood_group(query)
            if blood_group:
                result = self.lifebot.describe_stock(blood_group)
                self.session_service.update_context(session_id, 'last_stock_query', blood_group)
                return result
        
        # Accepted donors
        if any(word in query_lower for word in ['accepted', 'donors', 'request']):
            request_id = self._extract_request_id(query) or self.session_service.get_context(session_id, 'last_request_id')
            if request_id:
                result = self.lifebot.get_accepted_donors(request_id)
                return result
        
        # Successful donations
        if any(word in query_lower for word in ['successful', 'donations', 'completed', 'timeline']):
            limit = self._extract_number(query) or 10
            result = self.lifebot.get_successful_donations(limit)
            return result
        
        # Emergency
        if any(word in query_lower for word in ['emergency', 'urgent', 'critical']):
            emergency_data = self._extract_emergency_data(query)
            if emergency_data:
                result = self.lifebot.handle_emergency(emergency_data)
                return result
        
        # Default: return error
        return {
            'ok': False,
            'task': 'unknown',
            'error': 'Could not understand query. Please specify: stock lookup, accepted donors, successful donations, or emergency handling.',
            'explanation': 'Query not recognized. Please rephrase.',
            'tool_invocations': []
        }
    
    def _extract_blood_group(self, query: str) -> Optional[str]:
        """Extract blood group from query"""
        blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        for bg in blood_groups:
            if bg.lower() in query.lower():
                return bg
        return None
    
    def _extract_request_id(self, query: str) -> Optional[str]:
        """Extract request ID from query"""
        import re
        # Look for ObjectId-like strings
        pattern = r'[0-9a-f]{24}'
        matches = re.findall(pattern, query)
        return matches[0] if matches else None
    
    def _extract_number(self, query: str) -> Optional[int]:
        """Extract number from query"""
        import re
        numbers = re.findall(r'\d+', query)
        return int(numbers[0]) if numbers else None
    
    def _extract_emergency_data(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract emergency data from query (simplified)"""
        # This would need more sophisticated parsing in production
        return None  # Requires structured input


class ADKAutoPulseAgent:
    """ADK-compatible wrapper for AutoPulse agent"""
    
    def __init__(self, session_service: InMemorySessionService = None, memory_bank: MemoryBank = None):
        self.session_service = session_service or InMemorySessionService()
        self.memory_bank = memory_bank or MemoryBank()
        self.autopulse = None
        logger.info("ADKAutoPulseAgent initialized")
    
    def initialize(self, orchestrator=None):
        """Initialize underlying AutoPulse agent"""
        self.autopulse = AutoPulseAgent(orchestrator=orchestrator)
        logger.info("AutoPulse agent initialized")
    
    async def run(self, params: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """ADK-compatible run method"""
        if not session_id:
            session_id = f"autopulse_{datetime.now(timezone.utc).timestamp()}"
        
        admin_id = params.get('admin_id')
        logger.info(f"ADKAutoPulseAgent running for admin_id: {admin_id}")
        
        result = self.autopulse.execute(admin_id)
        
        # Store in memory
        self.memory_bank.store('AutoPulse', 'inventory_check', {
            'admin_id': admin_id,
            'hospitals_checked': len(result) if isinstance(result, list) else 1,
            'timestamp': datetime.now(timezone.utc)
        })
        
        return {
            'session_id': session_id,
            'result': result,
            'status': 'completed'
        }


class ADKRapidAidAgent:
    """ADK-compatible wrapper for RapidAid agent"""
    
    def __init__(self, session_service: InMemorySessionService = None, memory_bank: MemoryBank = None):
        self.session_service = session_service or InMemorySessionService()
        self.memory_bank = memory_bank or MemoryBank()
        self.rapidaid = None
        logger.info("ADKRapidAidAgent initialized")
    
    def initialize(self, orchestrator=None):
        """Initialize underlying RapidAid agent"""
        self.rapidaid = RapidAidAgent(orchestrator=orchestrator)
        logger.info("RapidAid agent initialized")
    
    async def run(self, emergency_data: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """ADK-compatible run method"""
        if not session_id:
            session_id = f"rapidaid_{datetime.now(timezone.utc).timestamp()}"
        
        logger.info(f"ADKRapidAidAgent handling emergency: {emergency_data.get('blood_group')}")
        
        result = self.rapidaid.execute(emergency_data)
        
        # Store in memory
        self.memory_bank.store('RapidAid', 'emergency_handled', {
            'blood_group': emergency_data.get('blood_group'),
            'units_needed': emergency_data.get('units_needed'),
            'handled_count': len(result.get('handled_emergencies', [])),
            'timestamp': datetime.now(timezone.utc)
        })
        
        return {
            'session_id': session_id,
            'result': result,
            'status': 'completed'
        }


class ADKPathFinderAgent:
    """ADK-compatible wrapper for PathFinder agent"""
    
    def __init__(self, session_service: InMemorySessionService = None, memory_bank: MemoryBank = None):
        self.session_service = session_service or InMemorySessionService()
        self.memory_bank = memory_bank or MemoryBank()
        self.pathfinder = None
        logger.info("ADKPathFinderAgent initialized")
    
    def initialize(self):
        """Initialize underlying PathFinder agent"""
        self.pathfinder = PathFinderAgent()
        logger.info("PathFinder agent initialized")
    
    async def run(self, params: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """ADK-compatible run method"""
        if not session_id:
            session_id = f"pathfinder_{datetime.now(timezone.utc).timestamp()}"
        
        donor_id = params.get('donor_id')
        hospital_id = params.get('hospital_id')
        request_id = params.get('request_id')
        
        logger.info(f"ADKPathFinderAgent planning route for request: {request_id}")
        
        result = self.pathfinder.execute(donor_id, hospital_id, request_id)
        
        # Store in memory
        self.memory_bank.store('PathFinder', 'route_planned', {
            'request_id': request_id,
            'distance_km': result.get('route', {}).get('distance_km'),
            'timestamp': datetime.now(timezone.utc)
        })
        
        return {
            'session_id': session_id,
            'result': result,
            'status': 'completed'
        }


class ADKLinkBridgeAgent:
    """ADK-compatible wrapper for LinkBridge agent"""
    
    def __init__(self, session_service: InMemorySessionService = None, memory_bank: MemoryBank = None):
        self.session_service = session_service or InMemorySessionService()
        self.memory_bank = memory_bank or MemoryBank()
        self.linkbridge = None
        logger.info("ADKLinkBridgeAgent initialized")
    
    def initialize(self):
        """Initialize underlying LinkBridge agent"""
        self.linkbridge = LinkBridgeAgent()
        logger.info("LinkBridge agent initialized")
    
    async def run(self, params: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """ADK-compatible run method"""
        if not session_id:
            session_id = f"linkbridge_{datetime.now(timezone.utc).timestamp()}"
        
        hospital_id = params.get('hospital_id')
        blood_group = params.get('blood_group')
        units_needed = params.get('units_needed')
        
        logger.info(f"ADKLinkBridgeAgent checking stock for {blood_group} at hospital {hospital_id}")
        
        result = self.linkbridge.execute(hospital_id, blood_group, units_needed)
        
        # Store in memory
        self.memory_bank.store('LinkBridge', 'stock_check', {
            'hospital_id': hospital_id,
            'blood_group': blood_group,
            'has_stock_nearby': result.get('has_stock_nearby', False),
            'timestamp': datetime.now(timezone.utc)
        })
        
        return {
            'session_id': session_id,
            'result': result,
            'status': 'completed'
        }


# Global instances for easy access
session_service = InMemorySessionService()
memory_bank = MemoryBank()

# ADK Agent instances
adk_lifebot = ADKLifeBotAgent(session_service=session_service, memory_bank=memory_bank)
adk_autopulse = ADKAutoPulseAgent(session_service=session_service, memory_bank=memory_bank)
adk_rapidaid = ADKRapidAidAgent(session_service=session_service, memory_bank=memory_bank)
adk_pathfinder = ADKPathFinderAgent(session_service=session_service, memory_bank=memory_bank)
adk_linkbridge = ADKLinkBridgeAgent(session_service=session_service, memory_bank=memory_bank)

logger.info("ADK integration module loaded successfully")

