from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel, Field
import logging
import time

class AgentResult(BaseModel):
    """Standardized output for every agent execution."""
    status: str = Field(..., description="SUCCESS, FAILED, NEED_INFO, or CONTINUE")
    data: Dict[str, Any] = Field(default_factory=dict, description="The actual payload produced by the agent")
    message: str = Field("", description="Human-readable summary of the result")
    logs: List[Dict[str, Any]] = Field(default_factory=list, description="Step-by-step execution logs")
    errors: Optional[str] = None
    next_steps: List[str] = Field(default_factory=list, description="Suggested next agents to call")

class BaseAgent(ABC):
    name: str
    description: str
    # Pydantic model class for input validation
    input_schema: Type[BaseModel] 

    def __init__(self):
        self.logger = logging.getLogger(f"agent.{self.name}")

    @abstractmethod
    async def run(self, params: BaseModel, chat_id: str) -> AgentResult:
        """The core execution logic. Subclasses implement this."""
        pass

    async def execute(self, chat_id: str, **kwargs) -> AgentResult:
        """
        Wrapper that handles logging, timing, and validation.
        """
        start_time = time.time()
        logs = []
        
        try:
            # 1. Validate Input
            input_data = self.input_schema(**kwargs)
            logs.append({"step": "validation", "status": "passed", "input": kwargs})
            
            # 2. Run Agent Logic
            result: AgentResult = await self.run(input_data, chat_id)
            
            # 3. Finalize Logs
            duration = time.time() - start_time
            result.logs = logs + result.logs
            result.logs.append({"step": "execution_complete", "duration": f"{duration:.2f}s"})
            
            return result
            
        except Exception as e:
            self.logger.error(f"Agent {self.name} failed: {e}", exc_info=True)
            return AgentResult(
                status="FAILED",
                errors=str(e),
                message=f"Agent {self.name} encountered an error: {e}",
                logs=logs
            )

    def get_tool_declaration(self) -> Dict[str, Any]:
        """Generates a clean JSON Schema for Gemini Tool definition."""
        schema = self.input_schema.model_json_schema()
        # Remove Pydantic internal fields that Gemini doesn't like
        schema.pop("title", None)
        schema.pop("description", None)
        if "properties" in schema:
            for prop in schema["properties"].values():
                prop.pop("title", None)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema
        }
