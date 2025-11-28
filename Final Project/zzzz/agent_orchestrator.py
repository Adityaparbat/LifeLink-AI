"""
Compatibility wrapper for AgentOrchestrator.
The actual implementation now lives in agents.agent_orchestrator.
"""
from agents.agent_orchestrator import AgentOrchestrator, orchestrator

__all__ = ["AgentOrchestrator", "orchestrator"]

