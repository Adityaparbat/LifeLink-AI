"""
Agent Evaluation Scripts for LifeLink System

Provides evaluation and testing capabilities for all agents to meet Kaggle requirements.
Includes unit tests, integration tests, and trace examples.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
import asyncio

from adk_integration import (
    adk_lifebot, adk_autopulse, adk_rapidaid, adk_pathfinder, adk_linkbridge,
    session_service, memory_bank
)
from mcp_tools import MongoDBMCPTools

logger = logging.getLogger(__name__)


class AgentEvaluator:
    """Evaluates agent performance and correctness"""
    
    def __init__(self):
        self.test_results: List[Dict[str, Any]] = []
        logger.info("AgentEvaluator initialized")
    
    def evaluate_autopulse(self, admin_id: str = None) -> Dict[str, Any]:
        """Evaluate AutoPulse agent"""
        logger.info("Evaluating AutoPulse agent...")
        
        test_name = "AutoPulse Inventory Monitoring"
        start_time = datetime.now(timezone.utc)
        
        try:
            # Initialize agent if needed
            if adk_autopulse.autopulse is None:
                adk_autopulse.initialize(orchestrator=None)
            
            # Run agent
            result = asyncio.run(adk_autopulse.run({'admin_id': admin_id}))
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            # Check result structure
            has_result = 'result' in result
            has_status = 'status' in result
            has_session = 'session_id' in result
            
            passed = has_result and has_status and has_session
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'duration_seconds': duration,
                'checks': {
                    'has_result': has_result,
                    'has_status': has_status,
                    'has_session_id': has_session
                },
                'result_sample': str(result)[:200] if result else None,
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"AutoPulse evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"AutoPulse evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def evaluate_rapidaid(self, emergency_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Evaluate RapidAid agent"""
        logger.info("Evaluating RapidAid agent...")
        
        test_name = "RapidAid Emergency Response"
        start_time = datetime.now(timezone.utc)
        
        try:
            if emergency_data is None:
                emergency_data = {
                    'type': 'manual',
                    'hospital_id': 'test_hospital_id',
                    'blood_group': 'O+',
                    'units_needed': 2,
                    'severity': 'high'
                }
            
            if adk_rapidaid.rapidaid is None:
                adk_rapidaid.initialize(orchestrator=None)
            
            result = asyncio.run(adk_rapidaid.run(emergency_data))
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            has_result = 'result' in result
            has_status = 'status' in result
            
            passed = has_result and has_status
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'duration_seconds': duration,
                'checks': {
                    'has_result': has_result,
                    'has_status': has_status
                },
                'result_sample': str(result)[:200] if result else None,
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"RapidAid evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"RapidAid evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def evaluate_pathfinder(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Evaluate PathFinder agent"""
        logger.info("Evaluating PathFinder agent...")
        
        test_name = "PathFinder Route Planning"
        start_time = datetime.now(timezone.utc)
        
        try:
            if params is None:
                params = {
                    'donor_id': 'test_donor_id',
                    'hospital_id': 'test_hospital_id',
                    'request_id': 'test_request_id'
                }
            
            if adk_pathfinder.pathfinder is None:
                adk_pathfinder.initialize()
            
            result = asyncio.run(adk_pathfinder.run(params))
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            has_result = 'result' in result
            has_status = 'status' in result
            
            passed = has_result and has_status
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'duration_seconds': duration,
                'checks': {
                    'has_result': has_result,
                    'has_status': has_status
                },
                'result_sample': str(result)[:200] if result else None,
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"PathFinder evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"PathFinder evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def evaluate_linkbridge(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Evaluate LinkBridge agent"""
        logger.info("Evaluating LinkBridge agent...")
        
        test_name = "LinkBridge Hospital Coordination"
        start_time = datetime.now(timezone.utc)
        
        try:
            if params is None:
                params = {
                    'hospital_id': 'test_hospital_id',
                    'blood_group': 'O+',
                    'units_needed': 3
                }
            
            if adk_linkbridge.linkbridge is None:
                adk_linkbridge.initialize()
            
            result = asyncio.run(adk_linkbridge.run(params))
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            has_result = 'result' in result
            has_stock_info = 'has_stock_nearby' in result.get('result', {})
            
            passed = has_result and has_stock_info
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'duration_seconds': duration,
                'checks': {
                    'has_result': has_result,
                    'has_stock_info': has_stock_info
                },
                'result_sample': str(result)[:200] if result else None,
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"LinkBridge evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"LinkBridge evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def evaluate_lifebot(self, query: str = None) -> Dict[str, Any]:
        """Evaluate LifeBot agent"""
        logger.info("Evaluating LifeBot agent...")
        
        test_name = "LifeBot Explainable AI Assistant"
        start_time = datetime.now(timezone.utc)
        
        try:
            if query is None:
                query = "Show me the stock for O- blood group"
            
            # Note: LifeBot needs DB initialization - this is a simplified test
            result = asyncio.run(adk_lifebot.run(query))
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            has_result = 'result' in result
            has_session = 'session_id' in result
            has_explanation = 'explanation' in result.get('result', {})
            
            passed = has_result and has_session
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'duration_seconds': duration,
                'checks': {
                    'has_result': has_result,
                    'has_session_id': has_session,
                    'has_explanation': has_explanation
                },
                'query': query,
                'result_sample': str(result)[:200] if result else None,
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"LifeBot evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"LifeBot evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def evaluate_mcp_tools(self, mcp_tools: MongoDBMCPTools) -> Dict[str, Any]:
        """Evaluate MCP tools"""
        logger.info("Evaluating MCP tools...")
        
        test_name = "MCP Tools Functionality"
        start_time = datetime.now(timezone.utc)
        
        try:
            # Test get_blood_stock
            stock_result = mcp_tools.get_blood_stock('O+')
            has_stock_tool = 'total_units' in stock_result
            
            # Test get_all_tools
            all_tools = mcp_tools.get_all_tools()
            has_tools_list = isinstance(all_tools, list) and len(all_tools) > 0
            
            passed = has_stock_tool and has_tools_list
            
            test_result = {
                'test_name': test_name,
                'passed': passed,
                'checks': {
                    'get_blood_stock_works': has_stock_tool,
                    'get_all_tools_works': has_tools_list,
                    'tool_count': len(all_tools) if has_tools_list else 0
                },
                'timestamp': start_time.isoformat()
            }
            
            self.test_results.append(test_result)
            logger.info(f"MCP Tools evaluation: {'PASSED' if passed else 'FAILED'}")
            
            return test_result
            
        except Exception as e:
            logger.error(f"MCP Tools evaluation error: {str(e)}")
            return {
                'test_name': test_name,
                'passed': False,
                'error': str(e),
                'timestamp': start_time.isoformat()
            }
    
    def run_all_evaluations(self, mcp_tools: MongoDBMCPTools = None) -> Dict[str, Any]:
        """Run all agent evaluations"""
        logger.info("Running all agent evaluations...")
        
        results = {
            'autopulse': self.evaluate_autopulse(),
            'rapidaid': self.evaluate_rapidaid(),
            'pathfinder': self.evaluate_pathfinder(),
            'linkbridge': self.evaluate_linkbridge(),
            'lifebot': self.evaluate_lifebot()
        }
        
        if mcp_tools:
            results['mcp_tools'] = self.evaluate_mcp_tools(mcp_tools)
        
        # Calculate summary
        total_tests = len(results)
        passed_tests = sum(1 for r in results.values() if r.get('passed', False))
        
        summary = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'pass_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        results['summary'] = summary
        
        logger.info(f"Evaluation complete: {passed_tests}/{total_tests} tests passed")
        
        return results
    
    def generate_trace_example(self) -> Dict[str, Any]:
        """Generate a trace example for documentation"""
        trace = {
            'agent': 'LifeBot',
            'session_id': 'example_session_123',
            'query': 'Show me the stock for O- blood group',
            'steps': [
                {
                    'step': 1,
                    'action': 'Parse query',
                    'result': 'Identified task: stock_lookup, blood_group: O-',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                {
                    'step': 2,
                    'action': 'Call MCP tool: get_blood_stock',
                    'tool': 'MCP.MongoDB.get_blood_stock',
                    'parameters': {'blood_group': 'O-'},
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                {
                    'step': 3,
                    'action': 'MongoDB query executed',
                    'result': 'Found 5 hospitals, total units: 42',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                {
                    'step': 4,
                    'action': 'Generate explanation with Gemini',
                    'tool': 'Gemini.Explain',
                    'result': 'Located 5 active hospitals. Total O- units: 42. 2 sites currently have zero stock.',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                {
                    'step': 5,
                    'action': 'Store in memory bank',
                    'result': 'Memory stored: LifeBot - stock_lookup',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            ],
            'final_result': {
                'ok': True,
                'task': 'stock_lookup',
                'data': {
                    'blood_group': 'O-',
                    'total_units': 42,
                    'hospitals': 5
                },
                'explanation': 'Located 5 active hospitals. Total O- units: 42. 2 sites currently have zero stock.',
                'tool_invocations': ['MCP.MongoDB.get_blood_stock', 'Gemini.Explain']
            },
            'duration_seconds': 1.23
        }
        
        return trace
    
    def export_results(self, filename: str = 'evaluation_results.json'):
        """Export evaluation results to JSON"""
        output = {
            'evaluation_date': datetime.now(timezone.utc).isoformat(),
            'test_results': self.test_results,
            'memory_bank_summary': {
                'total_memories': len(memory_bank.memories),
                'recent_memories': memory_bank.get_recent(5)
            },
            'session_summary': {
                'total_sessions': len(session_service.sessions),
                'session_ids': list(session_service.sessions.keys())[:10]
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        
        logger.info(f"Evaluation results exported to {filename}")
        return filename


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    evaluator = AgentEvaluator()
    
    # Run evaluations (requires DB connection)
    # results = evaluator.run_all_evaluations()
    # print(json.dumps(results, indent=2, default=str))
    
    # Generate trace example
    trace = evaluator.generate_trace_example()
    print(json.dumps(trace, indent=2))
    
    logger.info("Agent evaluation module ready")

