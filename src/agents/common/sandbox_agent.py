import os
import asyncio
import logging
import traceback
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

# Attempt to use RestrictedPython if available
try:
    from RestrictedPython import compile_restricted, safe_globals
    from RestrictedPython.PrintCollector import PrintCollector
    HAS_RESTRICTED = True
except ImportError:
    HAS_RESTRICTED = False

class SandboxInput(BaseModel):
    code: str = Field(..., description="The Python code to execute.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Variables to pass as locals.")
    timeout: int = Field(10, description="Execution timeout in seconds.")

class SandboxAgent(BaseAgent):
    name = "sandbox_executor"
    description = "Executes Python code in a restricted environment to verify it works safely. Use this to test generated agents."
    input_schema = SandboxInput

    async def run(self, params: SandboxInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Sandbox execution request for {chat_id}")
        logs = [{"step": "initialization"}]
        
        if not HAS_RESTRICTED:
            # Fallback to a slightly less secure method if RestrictedPython is missing
            # (though we should have it as we just installed it)
            return await self._run_insecure(params, logs)

        try:
            # Prepare Restricted Environment
            _globals = safe_globals.copy()
            _globals['_print_'] = PrintCollector
            
            # Remove or add specific safe modules if needed
            # For now, let's keep it very restricted.
            
            # Compile the code
            try:
                byte_code = compile_restricted(params.code, filename='<sandbox>', mode='exec')
            except SyntaxError as e:
                return AgentResult(status="FAILED", message=f"Syntax Error: {e}", logs=logs)

            # Execution logic
            # Note: exec is synchronous. For async code, this gets complex.
            # But we can allow the user to define a sync entry point or use a wrapper.
            
            # Since our agents are async, we might need a special handler.
            # For now, let's just run it as standard sync code.
            
            local_vars = params.params.copy()
            
            def execute_sync():
                exec(byte_code, _globals, local_vars)
                return local_vars, _globals.get('_print')()

            # Run in a thread to prevent blocking and allow timeout
            loop = asyncio.get_event_loop()
            try:
                result_vars, output = await asyncio.wait_for(
                    loop.run_in_executor(None, execute_sync),
                    timeout=params.timeout
                )
                
                logs.append({"step": "execution_complete"})
                return AgentResult(
                    status="SUCCESS",
                    data={
                        "output": str(output),
                        "result_vars": {k: str(v) for k, v in result_vars.items() if not k.startswith('_')}
                    },
                    message="Sandbox execution finished successfully.",
                    logs=logs
                )
            except asyncio.TimeoutError:
                return AgentResult(status="FAILED", message="Execution timed out.", logs=logs)

        except Exception as e:
            self.logger.error(f"Sandbox failure: {e}")
            return AgentResult(
                status="FAILED",
                errors=traceback.format_exc(),
                message=f"Sandbox execution error: {e}",
                logs=logs
            )

    async def _run_insecure(self, params: SandboxInput, logs: list) -> AgentResult:
        # Very basic restricted globals
        safe_locals = params.params.copy()
        safe_globals_insecure = {
            "__builtins__": {
                "print": print,
                "range": range,
                "len": len,
                "int": int,
                "float": float,
                "str": str,
                "list": list,
                "dict": dict,
                "set": set,
                "bool": bool,
                "abs": abs,
                "min": min,
                "max": max,
                "sum": sum,
            }
        }
        
        try:
            exec(params.code, safe_globals_insecure, safe_locals)
            return AgentResult(
                status="SUCCESS",
                data={"result_vars": {k: str(v) for k, v in safe_locals.items() if not k.startswith('_')}},
                message="Sandbox (Insecure Mode) execution finished.",
                logs=logs
            )
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), message=f"Error: {e}", logs=logs)
