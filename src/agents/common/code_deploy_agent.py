import os
import shutil
import importlib
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class CodeDeployInput(BaseModel):
    temp_file_path: str = Field(..., description="The full path to the temporary file containing the agent code.")
    confirm: bool = Field(False, description="Explicit confirmation for deployment.")

class CodeDeployAgent(BaseAgent):
    name = "code_deploy_agent"
    description = "Deploys a reviewed agent from a temporary file to the official agents directory and dynamically registers it."
    input_schema = CodeDeployInput
    
    AGENTS_DIR = "/etc/myapp/genie/src/agents/common"

    async def run(self, params: CodeDeployInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Deployment request for {params.temp_file_path} from {chat_id}")
        
        if not params.confirm:
            return AgentResult(status="NEED_INFO", message="Deployment requires explicit confirmation.")

        if not os.path.exists(params.temp_file_path):
            return AgentResult(status="FAILED", message=f"Proposed file not found at {params.temp_file_path}")

        logs = [{"step": "initialization", "path": params.temp_file_path}]

        try:
            # 1. Read the agent file to get the class name and agent name
            with open(params.temp_file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            import re
            # Extract class name and agent name (from name = "...")
            class_match = re.search(r"class\s+(\w+Agent)\(BaseAgent\):", content)
            agent_name_match = re.search(r"name\s*=\s*['\"](\w+)['\"]", content)
            
            if not class_match or not agent_name_match:
                return AgentResult(status="FAILED", message="Could not find valid BaseAgent class or agent name in the file.")
            
            class_name = class_match.group(1)
            agent_name = agent_name_match.group(1)
            
            # 2. Define target path
            target_file_name = f"{agent_name}.py"
            target_file_path = os.path.join(self.AGENTS_DIR, target_file_name)
            
            # 3. Move the file
            shutil.copy2(params.temp_file_path, target_file_path)
            logs.append({"step": "file_deployed", "target": target_file_path})
            
            # 4. Dynamic Loading
            # We need to import it. Since it's in a package, we need the correct path.
            # Assuming current work dir is project root.
            module_name = f"agents.common.{agent_name}"
            
            # Reload module if it exists, otherwise import it
            spec = importlib.util.spec_from_file_location(module_name, target_file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 5. Instantiate and Register
            agent_class = getattr(module, class_name)
            
            # Note: Some agents might require orchestrator or bot_instance in their __init__
            # For simplicity, we assume they take no arguments or we need a factory.
            # Most newly generated agents should be simple.
            try:
                # Attempt to instantiate with defaults
                agent_instance = agent_class()
            except TypeError:
                # If it needs arguments, we might have a problem unless we know what it needs.
                # For now, let's assume it can be instantiated without args.
                return AgentResult(status="FAILED", message=f"Agent class {class_name} requires initialization arguments that were not provided.")

            registry.register_agent(agent_instance)
            logs.append({"step": "dynamic_registration", "agent": agent_name})

            return AgentResult(
                status="SUCCESS",
                data={"agent_name": agent_name, "target_path": target_file_path},
                message=f"Agent '{agent_name}' has been successfully deployed and registered.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Deployment failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
