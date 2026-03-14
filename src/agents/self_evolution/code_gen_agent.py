import asyncio
import os
import json
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class CodeGenInput(BaseModel):
    agent_name: str = Field(..., description="The name of the new agent class (e.g., 'WeatherAgent').")
    description: str = Field(..., description="A detailed description of what the agent should do and its inputs/outputs.")
    required_libraries: List[str] = Field(default_factory=list, description="List of libraries that the agent might need.")

class CodeGenAgent(BaseAgent):
    name = "code_gen_agent"
    description = "Generates a complete BaseAgent subclass based on natural language requirements."
    input_schema = CodeGenInput

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: CodeGenInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator dependency missing.")

        self.logger.info(f"Generating code for agent: {params.agent_name}")

        prompt = f"""
        You are a Senior Software Architect specializing in the GenieBot Multi-Agent System.
        Your task is to generate a valid, production-ready Python subclass of `BaseAgent`.

        【New Agent Requirements】:
        - Class Name: {params.agent_name}
        - Functional Description: {params.description}
        - Required External Libraries: {params.required_libraries}

        【Project Structure & Constraints】:
        - Base Class: `from agents.base import BaseAgent, AgentResult`
        - Schema: Use `pydantic.BaseModel` for `input_schema`.
        - Imports: All required imports must be included.
        - Async: The `run` method MUST be `async`.
        - Logging: Use `self.logger.info(...)` for tracking steps.
        - Result: Always return an `AgentResult` object.
        - Persistence: If the agent needs to save files, use the `downloads/` or `img_output/` directories.
        - Security: DO NOT use `os.system` or `subprocess` without extreme caution. Prefer standard library alternatives.
        
        【Code Template】:
        ```python
        from pydantic import BaseModel, Field
        from typing import Dict, Any, List, Optional
        from agents.base import BaseAgent, AgentResult
        # ... other imports ...

        class {params.agent_name}Input(BaseModel):
            # Define fields here based on description
            pass

        class {params.agent_name}(BaseAgent):
            name = "{params.agent_name.lower()}" # Must be unique
            description = "{params.description[:100]}..."
            input_schema = {params.agent_name}Input

            def __init__(self, **kwargs):
                super().__init__()
                # Initialize any dependencies passed in
                for k, v in kwargs.items():
                    setattr(self, k, v)

            async def run(self, params: {params.agent_name}Input, chat_id: str) -> AgentResult:
                # 1. Implementation logic
                # 2. Return AgentResult(status="SUCCESS", data={{...}}, message="...")
                pass
        ```

        Output ONLY the raw Python code. Do not include any markdown block markers like ```python unless strictly necessary for formatting (but the prompt is for code generation, so just the code is better).
        Wait, actually, wrap it in a markdown block so I can parse it more easily if needed, or just plain text.
        Let's go with raw Python code.
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(prompt, []))
            processed = self.orchestrator.process_response(response)
            
            raw_code = processed.get("content", "")
            
            # Clean up the code if the model included backticks
            clean_code = re.sub(r"```python\n", "", raw_code)
            clean_code = re.sub(r"```", "", clean_code).strip()

            if not clean_code or "from agents.base" not in clean_code:
                return AgentResult(status="FAILED", message="Failed to generate valid BaseAgent code.", logs=[{"raw": raw_code}])

            # Save the code to a temporary file for review
            save_path = f"/etc/myapp/genie/src/agents/self_evolution/tmp_{params.agent_name.lower()}.py"
            with open(save_path, "w") as f:
                f.write(clean_code)

            return AgentResult(
                status="SUCCESS",
                data={
                    "agent_name": params.agent_name,
                    "generated_code": clean_code,
                    "save_path": save_path
                },
                message=f"Agent code for {params.agent_name} generated successfully and saved to {save_path}."
            )
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), message="Code generation process crashed.")
