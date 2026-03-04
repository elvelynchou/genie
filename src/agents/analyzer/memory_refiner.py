import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class MemoryRefinerInput(BaseModel):
    history: List[Dict[str, str]] = Field(..., description="The raw conversation history to refine.")
    session_status: str = Field("SUCCESS", description="The outcome of the session (SUCCESS or FAILED).")

class MemoryRefinerAgent(BaseAgent):
    name = "memory_refiner"
    description = "Extracts long-term 'instincts', user preferences, and technical lessons from conversation logs and stores them in RAG."
    input_schema = MemoryRefinerInput

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: MemoryRefinerInput, chat_id: str) -> AgentResult:
        if not self.orchestrator or not self.redis_mgr:
            return AgentResult(status="FAILED", message="Dependencies (Orchestrator/Redis) missing.")

        logs = [{"step": "refining_start", "history_len": len(params.history)}]

        # 1. Prepare Refinement Prompt
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in params.history])
        
        refine_prompt = f"""
        复盘并总结以下 AI 对话经验。
        当前会话状态：{params.session_status}
        
        请从以下三个维度提取“核心价值信息”：
        1. 用户偏好 (User Preferences)：用户喜欢的参数、风格、工作流习惯。
        2. 工具使用心得 (Tool Instincts)：哪个工具在什么场景下最好用，遇到了什么报错及如何规避。
        3. 核心事实 (Key Facts)：对话中提到的重要知识点。

        要求：
        - 语言精炼，每条经验不超过 50 字。
        - 必须输出为结构化的中文。
        - 如果没有新信息，请返回 'NO_NEW_INSIGHTS'。

        原始对话流：
        {history_text}
        """

        try:
            # 2. Call Gemini to synthesize
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(refine_prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            synthesis = processed.get("content", "").strip()

            if "NO_NEW_INSIGHTS" in synthesis or len(synthesis) < 5:
                return AgentResult(status="SUCCESS", message="No significant insights to store.")

            # 3. Vectorize and Store into L3 (RAG)
            # We break synthesis into points if needed, but for now store as one block
            embedding = await loop.run_in_executor(
                None,
                lambda: self.orchestrator.get_embedding(synthesis)
            )

            if embedding:
                doc_id = f"instinct_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}"
                await self.redis_mgr.store_vector(
                    doc_id=doc_id,
                    vector=embedding,
                    content=f"[Learned Experience]: {synthesis}"
                )
                logs.append({"step": "stored_to_rag", "id": doc_id})

            return AgentResult(
                status="SUCCESS",
                data={"insight": synthesis},
                message="Memory refined and stored as learned instinct.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Refinement failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
