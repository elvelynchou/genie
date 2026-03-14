import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class DreamerInput(BaseModel):
    depth_to_process: int = Field(2, description="The depth layer to scan (default is Fact layer).")

class DreamerAgent(BaseAgent):
    name = "dreamer"
    description = "Offline memory consolidation agent. Synthesizes high-level insights from raw facts."
    input_schema = DreamerInput

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: DreamerInput, chat_id: str) -> AgentResult:
        if not self.orchestrator or not self.redis_mgr:
            return AgentResult(status="FAILED", message="Dependencies missing.")

        self.logger.info(f"Starting Dreaming Phase for {chat_id}...")
        logs = [{"step": "dreaming_started", "chat_id": chat_id}]

        # 1. Fetch raw facts (depth=2)
        # For simplicity, we fetch the latest 50 facts across the system or specific to user
        facts = await self.redis_mgr.get_all_by_depth(depth=params.depth_to_process, limit=50)
        
        if not facts:
            return AgentResult(status="SUCCESS", message="No facts found to consolidate.")

        # Filter facts related to this chat_id if needed, but 'dreaming' is often global/cross-context
        # For now, let's process all available facts to find global patterns
        fact_texts = []
        for f in facts:
            text = f"- [{f.get('entities', 'unknown')}] {f.get('content', '')}"
            if f.get('relations'):
                text += f"\n  [Known Relations]: {f.get('relations')}"
            fact_texts.append(text)
        
        full_fact_corpus = "\n".join(fact_texts)
        
        # 2. Ask Gemini to find patterns and synthesize
        consolidation_prompt = f"""
        你是一个顶尖的系统架构师和投资研究主管。
        你正在进行“离线梦境”阶段：复盘并合并过去积累的碎片化事实与因果联系，将其升华为长效策略。

        【待处理的事实与因果碎片】：
        {full_fact_corpus[:15000]}

        【任务】：
        1. 寻找深层关联：哪些事实和已知因果指向了同一个宏观趋势或逻辑缺陷？
        2. 提取策略：生成新的“宏观策略节点 (Strategy, depth=0)”。
        3. 优化逻辑：生成新的“执行逻辑节点 (Logic, depth=1)”，并明确标注其“因果关系（为什么这么做）”。

        要求输出严格的 JSON 格式：
        {{
          "new_strategies": [
            {{"insight": "策略描述", "entities": ["关键词"], "causal_summary": "该策略背后的因果推导"}}
          ],
          "new_logics": [
            {{"insight": "逻辑描述", "entities": ["工具名"], "relations": "因果链条描述"}}
          ]
        }}

        如果没有显著的模式发现，请仅回复：NO_PATTERNS_FOUND
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(consolidation_prompt, []))
            processed = self.orchestrator.process_response(response)
            raw_synthesis = processed.get("content", "").strip()

            if "NO_PATTERNS_FOUND" in raw_synthesis:
                return AgentResult(status="SUCCESS", message="No new patterns found in this dream.")

            # Parse JSON
            try:
                json_str = raw_synthesis.replace("```json", "").replace("```", "").strip()
                dream_data = json.loads(json_str)
            except:
                return AgentResult(status="FAILED", message="Failed to parse dream synthesis.")

            # 3. Store synthesized insights
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Store Strategies (depth=0)
            for s in dream_data.get("new_strategies", []):
                content = s.get("insight")
                entities = s.get("entities", [])
                causal = s.get("causal_summary", "")
                vector = await loop.run_in_executor(None, lambda: self.orchestrator.get_embedding(content))
                if vector:
                    await self.redis_mgr.store_vector(
                        f"strat_dream_{timestamp}", vector, f"[Synthesized Strategy] {content}", 
                        entities, depth=0, relations=causal
                    )
            
            # Store Logics (depth=1)
            for l in dream_data.get("new_logics", []):
                content = l.get("insight")
                entities = l.get("entities", [])
                rel = l.get("relations", "")
                vector = await loop.run_in_executor(None, lambda: self.orchestrator.get_embedding(content))
                if vector:
                    await self.redis_mgr.store_vector(
                        f"logic_dream_{timestamp}", vector, f"[Synthesized Logic] {content}", 
                        entities, depth=1, relations=rel
                    )

            self.logger.info("Dreaming Phase complete. New insights stored.")
            return AgentResult(
                status="SUCCESS",
                data=dream_data,
                message="Dreaming Phase complete. Memory consolidated and synthesized.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Dreaming failed: {e}")
            return AgentResult(status="FAILED", errors=str(e))
