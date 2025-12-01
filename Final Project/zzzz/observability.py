"""
Observability and Logging Module for LifeLink System

Provides comprehensive logging, tracing, and monitoring capabilities
for ADK agents to meet Kaggle Agent Intensive requirements.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from functools import wraps
import traceback

logger = logging.getLogger(__name__)


class ObservabilityLogger:
    """
    Centralized observability logger for all agents.
    Provides structured logging with trace IDs and agent context.
    """
    
    def __init__(self):
        self.traces: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {
            'agent_invocations': {},
            'tool_calls': {},
            'errors': [],
            'performance': {}
        }
        logger.info("ObservabilityLogger initialized")
    
    def log_agent_start(self, agent_name: str, session_id: str, params: Dict[str, Any] = None):
        """Log agent start"""
        trace_id = f"trace_{datetime.now(timezone.utc).timestamp()}"
        
        log_entry = {
            'trace_id': trace_id,
            'agent': agent_name,
            'session_id': session_id,
            'event': 'agent_start',
            'params': params or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.info(f"[{agent_name}] Agent started - Trace ID: {trace_id}, Session: {session_id}")
        
        # Update metrics
        if agent_name not in self.metrics['agent_invocations']:
            self.metrics['agent_invocations'][agent_name] = 0
        self.metrics['agent_invocations'][agent_name] += 1
        
        return trace_id
    
    def log_agent_end(self, agent_name: str, trace_id: str, result: Dict[str, Any], 
                      duration_seconds: float):
        """Log agent completion"""
        log_entry = {
            'trace_id': trace_id,
            'agent': agent_name,
            'event': 'agent_end',
            'success': result.get('ok', result.get('success', False)),
            'duration_seconds': duration_seconds,
            'result_summary': {
                'has_data': 'data' in result or 'result' in result,
                'has_error': 'error' in result
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.info(f"[{agent_name}] Agent completed - Trace ID: {trace_id}, Duration: {duration_seconds:.2f}s")
        
        # Update performance metrics
        if agent_name not in self.metrics['performance']:
            self.metrics['performance'][agent_name] = []
        self.metrics['performance'][agent_name].append(duration_seconds)
    
    def log_tool_call(self, agent_name: str, trace_id: str, tool_name: str, 
                     params: Dict[str, Any], result: Any = None):
        """Log tool invocation"""
        log_entry = {
            'trace_id': trace_id,
            'agent': agent_name,
            'event': 'tool_call',
            'tool': tool_name,
            'params': params,
            'result_summary': str(result)[:200] if result else None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.info(f"[{agent_name}] Tool called: {tool_name} - Trace ID: {trace_id}")
        
        # Update tool metrics
        if tool_name not in self.metrics['tool_calls']:
            self.metrics['tool_calls'][tool_name] = 0
        self.metrics['tool_calls'][tool_name] += 1
    
    def log_error(self, agent_name: str, trace_id: str, error: Exception, context: Dict = None):
        """Log error with full context"""
        error_entry = {
            'trace_id': trace_id,
            'agent': agent_name,
            'event': 'error',
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'context': context or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(error_entry)
        self.metrics['errors'].append({
            'agent': agent_name,
            'error_type': type(error).__name__,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        logger.error(f"[{agent_name}] Error occurred - Trace ID: {trace_id}, Error: {str(error)}")
    
    def log_mcp_tool(self, tool_name: str, params: Dict[str, Any], result: Any, 
                    duration_seconds: float):
        """Log MCP tool execution"""
        log_entry = {
            'event': 'mcp_tool',
            'tool': tool_name,
            'params': params,
            'duration_seconds': duration_seconds,
            'result_size': len(str(result)) if result else 0,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.info(f"MCP Tool executed: {tool_name} - Duration: {duration_seconds:.2f}s")
    
    def log_session_created(self, session_id: str, agent_name: str = None):
        """Log session creation"""
        log_entry = {
            'event': 'session_created',
            'session_id': session_id,
            'agent': agent_name,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.info(f"Session created: {session_id}")
    
    def log_memory_stored(self, agent_name: str, event: str):
        """Log memory storage"""
        log_entry = {
            'event': 'memory_stored',
            'agent': agent_name,
            'memory_event': event,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.traces.append(log_entry)
        logger.debug(f"Memory stored: {agent_name} - {event}")
    
    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """Get all log entries for a trace ID"""
        return [entry for entry in self.traces if entry.get('trace_id') == trace_id]
    
    def get_agent_traces(self, agent_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent traces for an agent"""
        agent_traces = [entry for entry in self.traces if entry.get('agent') == agent_name]
        return sorted(agent_traces, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        summary = {
            'total_traces': len(self.traces),
            'agent_invocations': self.metrics['agent_invocations'].copy(),
            'tool_calls': self.metrics['tool_calls'].copy(),
            'error_count': len(self.metrics['errors']),
            'performance_avg': {}
        }
        
        # Calculate average performance
        for agent, durations in self.metrics['performance'].items():
            if durations:
                summary['performance_avg'][agent] = sum(durations) / len(durations)
        
        return summary
    
    def export_traces(self, filename: str = 'observability_traces.json'):
        """Export all traces to JSON"""
        output = {
            'export_date': datetime.now(timezone.utc).isoformat(),
            'total_traces': len(self.traces),
            'traces': self.traces[-1000:],  # Last 1000 traces
            'metrics': self.get_metrics_summary()
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        logger.info(f"Traces exported to {filename}")
        return filename


# Global observability logger instance
observability = ObservabilityLogger()


def trace_agent(agent_name: str):
    """Decorator to trace agent execution"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            session_id = kwargs.get('session_id') or f"session_{datetime.now(timezone.utc).timestamp()}"
            trace_id = observability.log_agent_start(agent_name, session_id, kwargs)
            
            start_time = datetime.now(timezone.utc)
            
            try:
                result = await func(*args, **kwargs)
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                observability.log_agent_end(agent_name, trace_id, result, duration)
                
                return result
                
            except Exception as e:
                observability.log_error(agent_name, trace_id, e, {'args': str(args), 'kwargs': str(kwargs)})
                raise
        
        return wrapper
    return decorator


def trace_tool(tool_name: str):
    """Decorator to trace tool calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            trace_id = f"tool_{datetime.now(timezone.utc).timestamp()}"
            agent_name = kwargs.get('agent_name', 'unknown')
            
            start_time = datetime.now(timezone.utc)
            
            try:
                result = func(*args, **kwargs)
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                observability.log_tool_call(agent_name, trace_id, tool_name, kwargs, result)
                
                return result
                
            except Exception as e:
                observability.log_error(agent_name, trace_id, e)
                raise
        
        return wrapper
    return decorator


# Configure logging
def setup_observability_logging(level=logging.INFO):
    """Setup structured logging for observability"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(agent)s] - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('lifelink_observability.log')
        ]
    )
    
    # Add custom formatter for agent context
    class AgentFormatter(logging.Formatter):
        def format(self, record):
            if not hasattr(record, 'agent'):
                record.agent = 'system'
            return super().format(record)
    
    for handler in logging.root.handlers:
        handler.setFormatter(AgentFormatter())
    
    logger.info("Observability logging configured")


logger.info("Observability module loaded successfully")

