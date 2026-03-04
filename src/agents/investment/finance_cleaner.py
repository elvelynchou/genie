import os
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class FinanceCleanerInput(BaseModel):
    raw_text: str = Field(..., description="The messy raw text or semantic tree string from browser.")
    source_name: str = Field(..., description="The name of the news source.")

class FinanceCleanerAgent(BaseAgent):
    name = "finance_cleaner"
    description = "Specialized agent to clean raw financial news text into structured Markdown."
    input_schema = FinanceCleanerInput

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: FinanceCleanerInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator missing.")

        clean_prompt = f"""
        你是一个专业的新闻编辑。请将以下来自【{params.source_name}】的原始网页文本清洗为结构化的 Markdown。
        
        要求：
        1. 仅保留新闻标题、发布时间（如有）和内容摘要。
        2. 剔除所有广告、导航栏、版权声明和社交媒体分享按钮等噪音。
        3. 如果内容包含突发事件（Breaking News），请在标题前加上 🚨。
        4. 确保格式整洁，使用二级或三级标题。

        原始文本内容：
        {params.raw_text[:8000]}
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(clean_prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            clean_md = processed.get("content", "Cleaning failed.")

            return AgentResult(
                status="SUCCESS",
                data={"clean_md": clean_md},
                message=f"Cleaned news for {params.source_name}."
            )
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e))
