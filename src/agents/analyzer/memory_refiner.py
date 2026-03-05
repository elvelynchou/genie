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
        
        你的目标是提取“长效知识”并将其结构化为图谱节点。
        请输出一个 JSON 对象，包含以下字段：
        1. "insight": 对本次对话核心经验的精炼总结（中文，50字内）。
        2. "entities": 本次对话涉及的核心实体列表（如：公司名、人名、特定技术、偏好关键词）。
        3. "relations": 实体间的关系简述（如：Alba -> 声明 -> 不可抗力）。

        如果没有新信息，请仅回复 'NO_NEW_INSIGHTS'。

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
            raw_synthesis = processed.get("content", "").strip()

            if "NO_NEW_INSIGHTS" in raw_synthesis or len(raw_synthesis) < 5:
                return AgentResult(status="SUCCESS", message="No significant insights to store.")

            # Parse JSON from model response
            try:
                # Basic JSON extraction if model adds markdown
                json_str = raw_synthesis.replace("```json", "").replace("```", "").strip()
                data = json.loads(json_str)
                synthesis = data.get("insight", "")
                entities = data.get("entities", [])
                # Relations can be added to the content for now
                relations = data.get("relations", [])
            except:
                synthesis = raw_synthesis
                entities = []
                relations = []

            # 3. Vectorize and Store into L3 (RAG) with Entities
            embedding = await loop.run_in_executor(
                None,
                lambda: self.orchestrator.get_embedding(synthesis)
            )

            if embedding:
                doc_id = f"instinct_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}"
                content_block = f"[Learned Experience]: {synthesis}"
                if relations:
                    content_block += f"\n[Relations]: {', '.join(relations)}"
                
                await self.redis_mgr.store_vector(
                    doc_id=doc_id,
                    vector=embedding,
                    content=content_block,
                    entities=entities
                )
                logs.append({"step": "stored_to_graph_rag", "id": doc_id, "entities": entities})

            return AgentResult(
                status="SUCCESS",
                data={"insight": synthesis, "entities": entities},
                message="Memory refined and stored in Lightweight Logic Graph.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Refinement failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
