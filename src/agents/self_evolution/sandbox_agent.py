import asyncio
import os
import logging
import traceback
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.self_evolution.sandbox_manager import SandboxManager

class SandboxInput(BaseModel):
    code: str = Field(..., description="The Python code of the agent to test.")
    agent_class_name: str = Field(..., description="The name of the class to instantiate.")
    test_params: Dict[str, Any] = Field(..., description="A dictionary of input parameters to pass to the agent's run method.")

class SandboxAgent(BaseAgent):
    name = "sandbox_tester"
    description = "Tests dynamically generated agent code in a safe, restricted environment before deployment."
    input_schema = SandboxInput

    def __init__(self):
        super().__init__()
        self.sandbox = SandboxManager()

    async def run(self, params: SandboxInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Sandbox Testing Agent: {params.agent_class_name}")

        try:
            result = await self.sandbox.run_agent_in_sandbox(
                agent_code=params.code,
                agent_class_name=params.agent_class_name,
                params=params.test_params,
                chat_id=chat_id
            )

            # Check if result is an AgentResult or a dict error
            if isinstance(result, dict) and "error" in result:
                return AgentResult(
                    status="FAILED",
                    errors=result.get("error"),
                    message=f"Sandbox test of {params.agent_class_name} FAILED."
                )
            
            # If it's already an AgentResult (from within the sandbox), return it
            return result

        except Exception as e:
            self.logger.error(f"Sandbox test failed with exception: {e}")
            return AgentResult(status="FAILED", errors=str(e), message="Sandbox process crashed.")
