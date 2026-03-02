import os
import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class CodeGenInput(BaseModel):
    agent_name: str = Field(..., description="The name of the new agent in snake_case (e.g., 'weather_agent')")
    description: str = Field(..., description="A brief description of what the agent does.")
    requirements: str = Field(..., description="Detailed functional requirements and any specific libraries to use.")
    input_fields: Dict[str, str] = Field(..., description="A dictionary of field names and their types/descriptions for the input schema.")

class CodeGenAgent(BaseAgent):
    name = "code_gen_agent"
    description = "Generates a new Python agent based on requirements. The code will follow the BaseAgent structure and use Pydantic for input validation."
    input_schema = CodeGenInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"
    AGENTS_DIR = "/etc/myapp/genie/src/agents/common"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: CodeGenInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator not provided to CodeGen Agent.")

        logs = [{"step": "initialization", "agent_name": params.agent_name}]
        
        # 1. Prepare the Prompt
        input_fields_str = "\n".join([f"- {name}: {desc}" for name, desc in params.input_fields.items()])
        
        prompt = f"""
你是一个高级 Python 开发工程师，专门为 GenieBot (Multi-Agent 系统) 编写新的 Agent。
请根据以下需求编写一个新的 Agent 类。

### 基础信息:
- **Agent Name**: {params.agent_name}
- **Description**: {params.description}
- **Requirements**: {params.requirements}

### Input Schema (Pydantic):
{input_fields_str}

### 编写指南:
1.  **类名**: 使用 {params.agent_name.title().replace('_', '')}Agent。
2.  **继承**: 必须继承自 `agents.base.BaseAgent`。
3.  **输入验证**: 使用 Pydantic 定义 `Input` 类。
4.  **异步**: `run` 方法必须是 `async` 的。
5.  **日志**: 使用 `self.logger` 进行记录。
6.  **结果**: 必须返回 `agents.base.AgentResult`。
7.  **代码风格**: 严谨、高效、包含必要的注释和错误处理。
8.  **依赖**: 如果需要第三方库，请在注释中说明。

### 模板示例 (不要直接复制，按需修改):
```python
import os
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class {params.agent_name.title().replace('_', '')}Input(BaseModel):
    # 定义输入字段
    pass

class {params.agent_name.title().replace('_', '')}Agent(BaseAgent):
    name = "{params.agent_name}"
    description = "{params.description}"
    input_schema = {params.agent_name.title().replace('_', '')}Input

    async def run(self, params: {params.agent_name.title().replace('_', '')}Input, chat_id: str) -> AgentResult:
        self.logger.info(f"Executing {{self.name}} for {{chat_id}}")
        logs = []
        try:
            # 实现核心逻辑
            # ...
            return AgentResult(status="SUCCESS", data={{}}, message="Done", logs=logs)
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
```

请直接输出完整的 Python 代码，不要包含任何 Markdown 包裹以外的解释。
"""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            generated_code = processed.get("content", "")

            # Extract code block if Gemini included markdown
            code_match = re.search(r"```python\n(.*?)\n```", generated_code, re.DOTALL)
            if code_match:
                final_code = code_match.group(1)
            else:
                final_code = generated_code

            # 2. Save to temporary file for review
            os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
            temp_file_name = f"proposed_{params.agent_name}_{chat_id}.py"
            temp_file_path = os.path.join(self.DOWNLOAD_DIR, temp_file_name)
            
            with open(temp_file_path, "w", encoding="utf-8") as f:
                f.write(final_code)
            
            logs.append({"step": "code_generated", "path": temp_file_path})

            return AgentResult(
                status="SUCCESS",
                data={
                    "code": final_code,
                    "file_path": temp_file_path,
                    "agent_name": params.agent_name
                },
                message=f"Agent '{params.agent_name}' has been generated and is ready for review. Path: {temp_file_path}",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Code generation failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
