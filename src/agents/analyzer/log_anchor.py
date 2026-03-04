import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class LogAnchorInput(BaseModel):
    conversation_history: List[Dict[str, str]] = Field(..., description="The history to anchor into a log.")
    focus_topic: Optional[str] = Field(None, description="Specific topic to focus on in the log.")

class LogAnchorAgent(BaseAgent):
    name = "log_anchor"
    description = "Captures the current technical state and progress into a permanent Markdown log file."
    input_schema = LogAnchorInput
    
    LOG_DIR = "/etc/myapp/genie/logs"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: LogAnchorInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator missing.")

        logs = [{"step": "anchoring_start"}]
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in params.conversation_history])
        
        anchor_prompt = f"""
        你是一个严谨的工程记录员。请基于以下对话历史，提取出“当前项目状态快照”。
        
        要求提取内容包括：
        1. 已实现的里程碑 (Milestones Reached)
        2. 解决的关键技术难题 (Solved Issues)
        3. 当前悬而未决的问题或 Bug (Pending Tasks)
        4. 关键配置变更 (Config Changes)
        
        重点关注：{params.focus_topic or '全量进度'}
        
        输出要求：
        - 必须使用标准的 Markdown 格式。
        - 语言必须为中文。
        - 简洁有力，仅保留核心事实。

        对话历史：
        {history_text}
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(anchor_prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            state_md = processed.get("content", "Log generation failed.")

            # Save to permanent log file
            os.makedirs(self.LOG_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            file_name = f"state_{date_str}.md"
            file_path = os.path.join(self.LOG_DIR, file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# Project State Anchor - {date_str}\n\n")
                f.write(state_md)
            
            logs.append({"step": "log_saved", "path": file_path})

            return AgentResult(
                status="SUCCESS",
                data={"log_path": file_path, "content": state_md},
                message=f"Project state has been anchored to {file_path}.",
                logs=logs
            )

        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
