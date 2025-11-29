import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
import google.generativeai as genai

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
        blood_group = (blood_group or '').upper()
        if blood_group not in self.BLOOD_GROUPS:
            return self._error_payload(
                'stock_lookup',
                f"Unsupported blood group '{blood_group}'.",
                tools=['MCP.MongoAdmins.read'],
            )

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

        return {
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
                'MCP.MongoAdmins.read',
                'Gemini.Explain' if self.model else None,
            ),
        }

    def get_accepted_donors(self, request_id: str) -> Dict[str, Any]:
        if not request_id:
            return self._error_payload(
                'accepted_donors',
                'Request ID is required.',
                tools=['MCP.Notifications.read'],
            )

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

        return {
            'ok': True,
            'task': 'accepted_donors',
            'data': {
                'request_id': request_id,
                'donors': donors,
                'count': len(donors),
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'MCP.Notifications.read',
                'MCP.Users.read',
                'Gemini.Explain' if self.model else None,
            ),
        }

    def get_successful_donations(self, limit: int = 10) -> Dict[str, Any]:
        limit = max(1, min(limit or 10, 25))
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

        context = {
            'count': len(timeline),
            'latest': timeline[:5],
        }

        explanation = self._explain(
            task='successful_donations',
            context=context,
            fallback=f"Compiled {len(timeline)} recently completed donor routes.",
        )

        return {
            'ok': True,
            'task': 'successful_donations',
            'data': {
                'records': timeline,
                'count': len(timeline),
            },
            'explanation': explanation,
            'tool_invocations': self._tool_trace(
                'MCP.DonorRoutes.read',
                'Gemini.Explain' if self.model else None,
            ),
        }

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

