import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
import google.generativeai as genai

# ADK Integration imports
try:
    from mcp_tools import MongoDBMCPTools
    MCP_TOOLS_AVAILABLE = True
except ImportError:
    MCP_TOOLS_AVAILABLE = False
    logger.warning("MCP tools not available, using direct MongoDB queries")

try:
    from observability import observability
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False

logger = logging.getLogger(__name__)


class LifeBotAgent:
    """
    LifeBot Explainable AI assistant powered by Google's Agent Development Kit.

    The agent exposes MongoDB access as MCP-style tools (e.g., inventory lookup,
    donor route diagnostics) and can escalate to agent-to-agent (A2A) workflows
    such as orchestrator.handle_emergency. Responses are summarized with Gemini
    to keep the reasoning explainable for admins.
    """

    BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

    def __init__(
        self,
        db,
        admins,
        users,
        notifications,
        admin_id: Optional[str] = None,
        orchestrator: Any = None,
        agents_enabled: bool = False,
    ):
        self.db = db
        self.admins = admins
        self.users = users
        self.notifications = notifications
        self.admin_id = admin_id
        self.orchestrator = orchestrator
        self.agents_enabled = agents_enabled

        # Initialize MCP tools if available
        if MCP_TOOLS_AVAILABLE:
            try:
                self.mcp_tools = MongoDBMCPTools(db, admins, users, notifications)
                self.use_mcp_tools = True
                logger.info("LifeBot: MCP tools initialized")
            except Exception as e:
                logger.warning(f"LifeBot: Failed to initialize MCP tools: {e}")
                self.mcp_tools = None
                self.use_mcp_tools = False
        else:
            self.mcp_tools = None
            self.use_mcp_tools = False

        self.model = None
        model_name = os.getenv('LIFEBOT_MODEL', 'gemini-1.5-flash')
        try:
            self.model = genai.GenerativeModel(model_name)
            self.model_name = model_name
        except Exception as exc:
            logger.warning("LifeBot Gemini model unavailable: %s", exc)
            self.model = None
            self.model_name = None

    # --------------------
    # Public agent tasks
    # --------------------

    def describe_stock(self, blood_group: str) -> Dict[str, Any]:
        # Log with observability if available
        import time
        start_time = time.time()
        trace_id = None
        if OBSERVABILITY_AVAILABLE:
            trace_id = observability.log_agent_start('LifeBot', f"admin_{self.admin_id}", {
                'task': 'describe_stock',
                'blood_group': blood_group
            })
            observability.log_tool_call('LifeBot', trace_id, 'describe_stock', {'blood_group': blood_group})

        blood_group = (blood_group or '').upper()
        if blood_group not in self.BLOOD_GROUPS:
            result = self._error_payload(
                'stock_lookup',
                f"Unsupported blood group '{blood_group}'.",
                tools=['MCP.get_blood_stock'],
            )
            if OBSERVABILITY_AVAILABLE and trace_id:
                observability.log_agent_end('LifeBot', trace_id, result, 0)
            return result

        # Use MCP tool if available, otherwise fallback to direct query
        if self.use_mcp_tools and self.mcp_tools:
            try:
                mcp_result = self.mcp_tools.get_blood_stock(blood_group)
                if OBSERVABILITY_AVAILABLE and trace_id:
                    observability.log_tool_call('LifeBot', trace_id, 'MCP.get_blood_stock', 
                                               {'blood_group': blood_group}, mcp_result)
                
                # Convert MCP result to expected format
                rows = []
                for hospital in mcp_result.get('hospitals', []):
                    rows.append({
                        'hospital_name': hospital.get('hospital_name', 'Unknown'),
                        'hospital_id': hospital.get('hospital_id', ''),
                        'admin_id': hospital.get('hospital_id', ''),
                        'status': hospital.get('status', 'unknown'),
                        'units': hospital.get('units', 0),
                        'last_updated': None,  # MCP tool doesn't return this
                    })
                total_units = mcp_result.get('total_units', 0)
                low_supply = mcp_result.get('low_supply_count', 0)
            except Exception as e:
                logger.warning(f"MCP tool failed, falling back to direct query: {e}")
                # Fallback to direct query
                rows, total_units, low_supply = self._query_stock_direct(blood_group)
        else:
            # Direct MongoDB query (backward compatibility)
            rows, total_units, low_supply = self._query_stock_direct(blood_group)

        context = {
            'blood_group': blood_group,
            'total_units': total_units,
            'low_supply_sites': low_supply,
            'rows': rows[:8],
        }

        explanation = self._explain(
            task='stock_lookup',
            context=context,
            fallback=(
                f"Located {len(rows)} hospitals. Total units of {blood_group}: {total_units}. "
                f"{low_supply} site(s) currently have zero stock."
            ),
        )

        result = {
            'ok': True,
            'task': 'stock_lookup',
            'data': {
                'blood_group': blood_group,
                'total_units': total_units,
                'rows': rows,
                'low_supply_sites': low_supply,
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'MCP.get_blood_stock' if self.use_mcp_tools else 'MCP.MongoAdmins.read',
                'Gemini.Explain' if self.model else None,
            ),
        }
        
        # Log completion with observability
        if OBSERVABILITY_AVAILABLE and trace_id:
            duration = time.time() - start_time
            observability.log_agent_end('LifeBot', trace_id, result, duration)
        
        return result
    
    def _query_stock_direct(self, blood_group: str):
        """Fallback method for direct MongoDB query"""
        rows: List[Dict[str, Any]] = []
        total_units = 0
        low_supply = 0
        result_cursor = self.admins.find(
            {},
            {
                'hospital_name': 1,
                'hospital_id': 1,
                'blood_inventory': 1,
                'status': 1,
                'updated_at': 1,
            },
        )

        for doc in result_cursor:
            inventory = doc.get('blood_inventory') or {}
            units = int(inventory.get(blood_group, 0) or 0)
            total_units += units
            if units == 0:
                low_supply += 1
            rows.append({
                'hospital_name': doc.get('hospital_name', 'Unknown'),
                'hospital_id': doc.get('hospital_id') or str(doc.get('_id')),
                'admin_id': str(doc.get('_id')),
                'status': doc.get('status', 'unknown'),
                'units': units,
                'last_updated': self._format_dt(doc.get('updated_at')),
            })

        rows.sort(key=lambda item: item['units'], reverse=True)
        return rows, total_units, low_supply

    def get_accepted_donors(self, request_id: str) -> Dict[str, Any]:
        # Log with observability if available
        import time
        start_time = time.time()
        trace_id = None
        if OBSERVABILITY_AVAILABLE:
            trace_id = observability.log_agent_start('LifeBot', f"admin_{self.admin_id}", {
                'task': 'get_accepted_donors',
                'request_id': request_id
            })

        if not request_id:
            result = self._error_payload(
                'accepted_donors',
                'Request ID is required.',
                tools=['MCP.get_accepted_donors_for_request'],
            )
            if OBSERVABILITY_AVAILABLE and trace_id:
                observability.log_agent_end('LifeBot', trace_id, result, 0)
            return result

        # Use MCP tool if available
        if self.use_mcp_tools and self.mcp_tools:
            try:
                mcp_result = self.mcp_tools.get_accepted_donors_for_request(request_id)
                if OBSERVABILITY_AVAILABLE and trace_id:
                    observability.log_tool_call('LifeBot', trace_id, 'MCP.get_accepted_donors_for_request',
                                               {'request_id': request_id}, mcp_result)
                
                # Convert MCP result to expected format
                donors = []
                for donor in mcp_result.get('donors', []):
                    donors.append({
                        'user_id': donor.get('user_id'),
                        'name': donor.get('name', 'Unknown'),
                        'blood_group': donor.get('blood_group'),
                        'phone': donor.get('phone', 'N/A'),
                        'email': donor.get('email', 'N/A'),
                        'response_time': donor.get('response_time'),
                        'distance': donor.get('distance'),
                        'request_id': request_id,
                    })
            except Exception as e:
                logger.warning(f"MCP tool failed, falling back to direct query: {e}")
                donors = self._query_accepted_donors_direct(request_id)
        else:
            # Direct MongoDB query (backward compatibility)
            donors = self._query_accepted_donors_direct(request_id)

        context = {
            'request_id': request_id,
            'count': len(donors),
            'donors': donors[:6],
        }

        explanation = self._explain(
            task='accepted_donors',
            context=context,
            fallback=f"Found {len(donors)} accepted donor(s) for request {request_id}.",
        )

        result = {
            'ok': True,
            'task': 'accepted_donors',
            'data': {
                'request_id': request_id,
                'donors': donors,
                'count': len(donors),
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'MCP.get_accepted_donors_for_request' if self.use_mcp_tools else 'MCP.Notifications.read',
                'Gemini.Explain' if self.model else None,
            ),
        }
        
        # Log completion
        if OBSERVABILITY_AVAILABLE and trace_id:
            duration = time.time() - start_time
            observability.log_agent_end('LifeBot', trace_id, result, duration)
        
        return result
    
    def _query_accepted_donors_direct(self, request_id: str):
        """Fallback method for direct MongoDB query"""
        accepted_requests = list(self.notifications.find({
            'request_id': request_id,
            'status': 'responded',
            'response': 'accepted'
        }))

        donors: List[Dict[str, Any]] = []
        for req in accepted_requests:
            donor_id = req.get('user_id')
            donor_oid = ObjectId(donor_id) if donor_id and ObjectId.is_valid(str(donor_id)) else None
            donor_doc = self.users.find_one({'_id': donor_oid}) if donor_oid else None

            donors.append({
                'user_id': donor_id,
                'name': donor_doc.get('name') if donor_doc else 'Unknown',
                'blood_group': donor_doc.get('blood_group') if donor_doc else req.get('data', {}).get('blood_group_needed'),
                'phone': donor_doc.get('phone', 'N/A') if donor_doc else 'N/A',
                'email': donor_doc.get('email', 'N/A') if donor_doc else 'N/A',
                'response_time': self._format_dt(req.get('response_time')),
                'distance': req.get('data', {}).get('distance'),
                'request_id': request_id,
            })
        return donors

    def get_successful_donations(self, limit: int = 10) -> Dict[str, Any]:
        # Log with observability if available
        import time
        start_time = time.time()
        trace_id = None
        if OBSERVABILITY_AVAILABLE:
            trace_id = observability.log_agent_start('LifeBot', f"admin_{self.admin_id}", {
                'task': 'get_successful_donations',
                'limit': limit
            })

        limit = max(1, min(limit or 10, 25))
        
        # Use MCP tool if available
        if self.use_mcp_tools and self.mcp_tools:
            try:
                mcp_result = self.mcp_tools.get_successful_donations(limit)
                if OBSERVABILITY_AVAILABLE and trace_id:
                    observability.log_tool_call('LifeBot', trace_id, 'MCP.get_successful_donations',
                                               {'limit': limit}, mcp_result)
                
                # Convert MCP result to expected format
                timeline = []
                for record in mcp_result.get('records', []):
                    timeline.append({
                        'request_id': record.get('request_id'),
                        'status': record.get('status'),
                        'completed_at': record.get('completed_at'),
                        'donor_name': record.get('donor_name', 'Unknown'),
                        'blood_group': record.get('blood_group'),
                        'distance_km': record.get('distance_km'),
                        'hospital_id': record.get('hospital_id'),
                    })
            except Exception as e:
                logger.warning(f"MCP tool failed, falling back to direct query: {e}")
                timeline = self._query_successful_donations_direct(limit)
        else:
            # Direct MongoDB query (backward compatibility)
            timeline = self._query_successful_donations_direct(limit)

        context = {
            'count': len(timeline),
            'latest': timeline[:5],
        }

        explanation = self._explain(
            task='successful_donations',
            context=context,
            fallback=f"Compiled {len(timeline)} recently completed donor routes.",
        )

        result = {
            'ok': True,
            'task': 'successful_donations',
            'data': {
                'records': timeline,
                'count': len(timeline),
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'MCP.get_successful_donations' if self.use_mcp_tools else 'MCP.DonorRoutes.read',
                'Gemini.Explain' if self.model else None,
            ),
        }
        
        # Log completion
        if OBSERVABILITY_AVAILABLE and trace_id:
            duration = time.time() - start_time
            observability.log_agent_end('LifeBot', trace_id, result, duration)
        
        return result
    
    def _query_successful_donations_direct(self, limit: int):
        """Fallback method for direct MongoDB query"""
        routes = list(
            self.db.donor_routes.find(
                {'status': {'$in': ['completed', 'success', 'completed_by_agent']}}
            )
            .sort('completed_at', -1)
            .limit(limit)
        )

        timeline: List[Dict[str, Any]] = []
        for route in routes:
            request_id = route.get('request_id')
            notification = self.notifications.find_one({'request_id': request_id}) if request_id else None
            donor_id = route.get('donor_id') or (notification or {}).get('user_id')
            donor_doc = None
            if donor_id and ObjectId.is_valid(str(donor_id)):
                donor_doc = self.users.find_one({'_id': ObjectId(donor_id)})

            timeline.append({
                'request_id': request_id,
                'status': route.get('status'),
                'completed_at': self._format_dt(route.get('completed_at') or route.get('updated_at')),
                'donor_name': (donor_doc or {}).get('name', 'Unknown'),
                'blood_group': (notification or {}).get('data', {}).get('blood_group_needed'),
                'distance_km': route.get('distance_km'),
                'hospital_id': route.get('hospital_id'),
            })
        return timeline

    def handle_emergency(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = ['hospital_id', 'blood_group', 'units_needed']
        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            return self._error_payload(
                'handle_emergency',
                f"Missing fields: {', '.join(missing)}",
                tools=['A2A.Orchestrator.handle_emergency'],
            )

        if not self.agents_enabled or not self.orchestrator:
            return self._error_payload(
                'handle_emergency',
                'Agent orchestrator is not available in this environment.',
                tools=['A2A.Orchestrator.handle_emergency'],
            )

        try:
            units = int(payload.get('units_needed', 1))
        except (ValueError, TypeError):
            units = 1

        location = None
        latitude = payload.get('latitude')
        longitude = payload.get('longitude')
        if latitude is not None and longitude is not None:
            try:
                location = {'latitude': float(latitude), 'longitude': float(longitude)}
            except (TypeError, ValueError):
                location = None

        emergency_request = {
            'hospital_id': payload.get('hospital_id'),
            'blood_group': payload.get('blood_group'),
            'units_needed': units,
            'location': location,
            'severity': payload.get('severity', 'high'),
            'description': payload.get('description') or 'LifeBot-triggered emergency',
            'type': 'lifebot',
        }

        result = self.orchestrator.handle_emergency(emergency_request)
        ok = bool(result.get('success'))

        explanation = self._explain(
            task='handle_emergency',
            context={'request': emergency_request, 'result': result},
            fallback='Emergency workflow triggered via orchestrator.',
        )

        return {
            'ok': ok,
            'task': 'handle_emergency',
            'data': {
                'request': emergency_request,
                'result': result,
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'A2A.Orchestrator.handle_emergency',
                'Gemini.Explain' if self.model else None,
            ),
        }

    # --------------------
    # Helper methods
    # --------------------

    def _explain(self, task: str, context: Dict[str, Any], fallback: str) -> str:
        if not self.model:
            return fallback
        try:
            prompt = (
                "You are LifeBot, an explainable hospital assistant built on the Google Agent Development Kit. "
                "Given the structured telemetry below, generate a concise explanation with:\n"
                "1. A short insight sentence.\n"
                "2. Two bullet points referencing concrete numbers.\n"
                "3. A recommended next step.\n"
                "Keep the tone professional and actionable.\n"
                f"TASK: {task}\n"
                f"DATA: {json.dumps(context, default=self._serialize)[:6000]}"
            )
            response = self.model.generate_content(prompt)
            return (response.text or '').strip() or fallback
        except Exception as exc:
            logger.warning("LifeBot explanation fallback (%s): %s", task, exc)
            return fallback

    def _error_payload(self, task: str, message: str, tools: Optional[List[str]] = None) -> Dict[str, Any]:
        return {
            'ok': False,
            'task': task,
            'error': message,
            'explanation': message,
            'tool_invocations': self._tool_trace(*(tools or [])),
            'data': {},
        }

    def _tool_trace(self, *tools: Optional[str]) -> List[str]:
        return [tool for tool in tools if tool]

    def _format_dt(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, dict) and '$date' in value:
            try:
                return datetime.fromtimestamp(value['$date'] / 1000, timezone.utc).isoformat()
            except Exception:
                return str(value['$date'])
        return str(value)

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, ObjectId):
            return str(value)
        return value

