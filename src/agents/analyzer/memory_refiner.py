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
        
        你的目标是提取“层级化长效知识 (Hierarchical Knowledge)”并将其结构化。
        请输出一个 JSON 对象，包含以下三个层级的分析：

        1. "strategy": {{"insight": "宏观策略总结（为什么要这么做，用户核心意图是什么，50字内）", "entities": ["核心关键词"]}}
        2. "logic": {{"insight": "执行逻辑总结（具体使用了什么工具，避开了什么坑，操作流程是什么）", "entities": ["工具名", "错误码"]}}
        3. "data": {{"insight": "关键事实数据（对话中提到的具体数字、人名、链接内容摘要）", "entities": ["具体实体"]}}

        要求：
        - 语言精炼，输出严格的 JSON 格式。
        - 如果没有新信息，请仅回复 'NO_NEW_INSIGHTS'。

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
                json_str = raw_synthesis.replace("```json", "").replace("```", "").strip()
                hierarchical_data = json.loads(json_str)
            except Exception as e:
                self.logger.warning(f"Failed to parse hierarchical JSON: {e}")
                return AgentResult(status="FAILED", message="Analysis output format error.")

            # 3. 分层存储到 Redis
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            layers = [
                ("strategy", 0), # Strategy Layer
                ("logic", 1),    # Logic Layer
                ("data", 2)      # Data Layer
            ]

            for layer_name, depth_val in layers:
                layer_content = hierarchical_data.get(layer_name, {})
                insight = layer_content.get("insight", "")
                entities = layer_content.get("entities", [])
                
                if not insight or insight == "无": continue

                # Vectorize per layer
                embedding = await loop.run_in_executor(
                    None,
                    lambda: self.orchestrator.get_embedding(insight)
                )

                if embedding:
                    doc_id = f"{layer_name}_{timestamp}_{chat_id}"
                    prefix = "[Strategy]" if depth_val == 0 else "[Logic]" if depth_val == 1 else "[Fact]"
                    await self.redis_mgr.store_vector(
                        doc_id=doc_id,
                        vector=embedding,
                        content=f"{prefix} {insight}",
                        entities=entities,
                        depth=depth_val
                    )
                    logs.append({"step": f"stored_{layer_name}", "id": doc_id, "entities": entities})

            return AgentResult(
                status="SUCCESS",
                data=hierarchical_data,
                message="Hierarchical Memory refined and stored (Strategy/Logic/Data).",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Refinement failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
