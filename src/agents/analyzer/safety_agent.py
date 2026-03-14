import asyncio
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class SafetyInput(BaseModel):
    intent: str = Field(..., description="The core intent of the action.")
    proposed_action: str = Field(..., description="The specific code or tool call to execute.")
    expected_outcome: str = Field(..., description="The expected positive result.")
    potential_side_effects: str = Field(..., description="Possible negative impacts.")

class SafetyAgent(BaseAgent):
    name = "safety_gate"
    description = "Causal Intent Auditor. Evaluates risks of high-stakes actions based on historical causal memory."
    input_schema = SafetyInput

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: SafetyInput, chat_id: str) -> AgentResult:
        if not self.orchestrator or not self.redis_mgr:
            return AgentResult(status="FAILED", message="Dependencies missing.")

        self.logger.info(f"Auditing high-risk intent: {params.intent}")
        
        # 1. 查询因果记忆，寻找类似意图的失败经验
        try:
            vector = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.orchestrator.get_embedding(params.intent)
            )
            # 专门搜索 Logic 和 Strategy 层
            past_experiences = await self.redis_mgr.search_hierarchical(vector, k_strategy=3, k_data=0)
            context = "\n".join(past_experiences) if past_experiences else "无相关历史风险记录。"
        except:
            context = "无法获取因果记忆。"

        # 2. 调用 AI 进行风险评估
        audit_prompt = f"""
        你是一个严苛的系统安全审计员。你正在评估一个高风险操作。
        
        【本次操作申请】：
        - 意图: {params.intent}
        - 具体内容: {params.proposed_action}
        - 预期结果: {params.expected_outcome}
        - 声明副作用: {params.potential_side_effects}
        
        【历史因果背景（类似案例）】：
        {context}
        
        【审计任务】：
        请根据历史经验和当前描述，给出风险评分 (GREEN, YELLOW, RED) 和最终判定建议。
        
        判定标准：
        - RED: 历史有致命失败、代码包含危险操作（如硬编码密钥、删除系统目录）。
        - YELLOW: 历史有类似失败记录，或副作用声明不清晰。需用户授权。
        - GREEN: 安全且符合最佳实践。
        
        输出严格 JSON 格式：
        {{
          "score": "GREEN/YELLOW/RED",
          "reason": "审计理由",
          "action_approved": true/false
        }}
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(audit_prompt, []))
            processed = self.orchestrator.process_response(response)
            
            raw_audit = processed.get("content", "{}")
            json_str = raw_audit.replace("```json", "").replace("```", "").strip()
            audit_result = json.loads(json_str)
            
            self.logger.info(f"Audit Result: {audit_result['score']} | {audit_result['reason']}")
            
            return AgentResult(
                status="SUCCESS",
                data=audit_result,
                message=f"Audit complete. Risk Level: {audit_result['score']}"
            )
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), message="Audit process crashed.")
