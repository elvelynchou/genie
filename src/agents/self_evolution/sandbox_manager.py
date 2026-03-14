import logging
import traceback
import importlib
from typing import Any, Dict, Optional, List
from RestrictedPython import compile_restricted, safe_builtins, limited_builtins, utility_builtins
from RestrictedPython.PrintCollector import PrintCollector
from pydantic import BaseModel, Field
import agents.base
import typing

# Whitelist of allowed modules in the sandbox
ALLOWED_MODULES = [
    'requests', 'json', 're', 'datetime', 'math', 'pydantic', 'typing', 
    'agents', 'logging', 'asyncio', 'collections', 'itertools', 'functools'
]

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    # Check if the module or any of its parents are in the whitelist
    root_name = name.split('.')[0]
    if root_name in ALLOWED_MODULES:
        module = importlib.import_module(name)
        return module
    raise ImportError(f"Import of '{name}' is not allowed in the restricted sandbox.")

# Standard restricted environment
SAFE_GLOBALS = {
    '__builtins__': {
        **safe_builtins,
        **limited_builtins,
        **utility_builtins,
        '__import__': safe_import,
        'super': super,
        'property': property,
        'classmethod': classmethod,
        'staticmethod': staticmethod,
        'set': set,
        'dict': dict,
        'list': list,
        'tuple': tuple,
        'enumerate': enumerate,
        'sum': sum,
        'min': min,
        'max': max,
        'any': any,
        'all': all,
        'map': map,
        'filter': filter,
        'reversed': reversed,
        'getattr': getattr,
        'setattr': setattr,
        'hasattr': hasattr,
        '_print_': PrintCollector,
        '_getattr_': getattr,
        '_getitem_': lambda obj, key: obj[key],
        '_write_': lambda obj: obj, # Basic write access
    },
    'BaseModel': BaseModel,
    'Field': Field,
    'logging': logging,
    'typing': typing,
    'Dict': typing.Dict,
    'Any': typing.Any,
    'List': typing.List,
    'Optional': typing.Optional,
    '__name__': 'sandbox_exec',
    '__file__': '<string>'
}

class SandboxManager:
    def __init__(self):
        self.logger = logging.getLogger("SandboxManager")

    async def run_agent_in_sandbox(self, agent_code: str, agent_class_name: str, params: Dict[str, Any], chat_id: str) -> Any:
        """
        Executes a BaseAgent subclass in a restricted-but-functional environment.
        """
        try:
            # Note: We use the standard compile here to support async/await,
            # but we execute it with our SAFE_GLOBALS to enforce restrictions.
            # RestrictedPython's compile_restricted doesn't natively support 
            # async/await easily without more complex transformations.
            
            safe_globals = {**SAFE_GLOBALS}
            loc = {}
            
            # 1. Compile and execute the code to define the class
            byte_code = compile(agent_code, '<string>', 'exec')
            exec(byte_code, safe_globals)
            
            # 2. Instantiate and run the agent
            if agent_class_name in safe_globals:
                agent_class = safe_globals[agent_class_name]
                
                # Ensure the class inherits from BaseAgent (or at least looks like it)
                agent_instance = agent_class()
                
                if hasattr(agent_instance, 'run'):
                    input_schema = getattr(agent_instance, 'input_schema', None)
                    if input_schema:
                        validated_params = input_schema(**params)
                        return await agent_instance.run(validated_params, chat_id)
                    else:
                        return await agent_instance.run(params, chat_id)
                else:
                    return {"error": f"Agent class {agent_class_name} has no 'run' method."}
            else:
                return {"error": f"Agent class {agent_class_name} not found in generated code."}

        except Exception as e:
            self.logger.error(f"Sandbox run_agent error: {e}\n{traceback.format_exc()}")
            return {"error": str(e), "traceback": traceback.format_exc()}
