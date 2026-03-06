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
            import traceback
            tb = traceback.format_exc()
            self.logger.error(f"Agent {self.name} failed: {e}\n{tb}")
            return AgentResult(
                status="FAILED",
                errors=f"{str(e)}\n{tb}",
                message=f"Agent {self.name} encountered an error: {e}",
                logs=logs
            )

    def get_tool_declaration(self) -> Dict[str, Any]:
        """Generates a strictly compliant JSON Schema for Gemini Tool definition."""
        schema = self.input_schema.model_json_schema()
        
        def clean_schema(obj):
            if not isinstance(obj, dict):
                return obj
            
            # Fields allowed by Gemini Function Declaration
            allowed_fields = {"type", "properties", "required", "items", "description", "enum", "format"}
            
            # Create a copy to avoid mutation issues during iteration
            cleaned = {k: clean_schema(v) for k, v in obj.items() if k in allowed_fields}
            
            # Special case: if it's an object type, ensure properties exists if needed
            if obj.get("type") == "object" and "properties" in obj:
                cleaned["properties"] = {k: clean_schema(v) for k, v in obj["properties"].items()}
            
            # Special case: handle arrays
            if obj.get("type") == "array" and "items" in obj:
                cleaned["items"] = clean_schema(obj["items"])
                
            return cleaned

        return {
            "name": self.name,
            "description": self.description,
            "parameters": clean_schema(schema)
        }
