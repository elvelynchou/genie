import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import pytz
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class HeartbeatInput(BaseModel):
    is_manual: bool = Field(False, description="Whether the heartbeat was triggered manually.")
    force_task: Optional[str] = Field(None, description="Manually force a specific task.")
    message_thread_id: Optional[int] = Field(None, description="The Telegram message thread ID.")

class HeartbeatAgent(BaseAgent):
    name = "heartbeat"
    description = "Intelligent pulse agent. Wakes up, checks HEARTBEAT.md and task_status.json, and dispatches tasks."
    input_schema = HeartbeatInput

    PROTOCOL_PATH = "/etc/myapp/genie/HEARTBEAT.md"
    STATUS_PATH = "/etc/myapp/genie/src/agents/task_status.json"
    LOG_PATH = "/etc/myapp/genie/logs/heartbeat.log"

    def __init__(self, orchestrator=None, bot=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.bot = bot
        self.tz = pytz.timezone('Asia/Shanghai')

    async def _safe_send(self, chat_id: str, text: str, message_thread_id: Optional[int] = None):
        if not self.bot or not text: return
        CHUNK_SIZE = 3500
        chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        for chunk in chunks:
            try:
                await self.bot.send_message(chat_id, chunk, parse_mode="Markdown", message_thread_id=message_thread_id)
            except:
                try: await self.bot.send_message(chat_id, chunk, parse_mode=None, message_thread_id=message_thread_id)
                except: pass
            await asyncio.sleep(0.5)

    async def run(self, params: HeartbeatInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator dependency missing.")

        now = datetime.now(self.tz)
        now_iso = now.isoformat()
        
        # 1. Perception
        protocol = ""
        if os.path.exists(self.PROTOCOL_PATH):
            with open(self.PROTOCOL_PATH, "r", encoding="utf-8") as f:
                protocol = f.read()
        
        status_data = {}
        if os.path.exists(self.STATUS_PATH):
            with open(self.STATUS_PATH, "r", encoding="utf-8") as f:
                status_data = json.load(f)

        # 2. Decision
        decision_prompt = f"""
        你是一个自主运行的系统调度员。现在是北京时间：{now_iso}。
        
        【任务协议 (HEARTBEAT.md)】：
        {protocol}
        
        【任务运行历史 (task_status.json)】：
        {json.dumps(status_data, indent=2)}
        
        【你的任务】：
        对比当前时间和运行历史，根据协议判断现在是否需要执行任何任务。
        
        要求：
        1. 输出严格的 JSON 格式。
        2. "tasks_to_run" 是待执行的 Agent 列表（只能选: ["finance_monitor", "daily_report", "dreamer", "sys_check"]）。
        3. 如果没有任务需要运行，返回 empty 列表。
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(decision_prompt, []))
            processed = self.orchestrator.process_response(response)
            
            raw_decision = processed.get("content", "{}")
            json_str = raw_decision.replace("```json", "").replace("```", "").strip()
            decision = json.loads(json_str)
            
            tasks = decision.get("tasks_to_run", [])
            if params.force_task: tasks = [params.force_task]

            if not tasks:
                return AgentResult(status="SUCCESS", message="HEARTBEAT_OK")

            # 3. Execution & Dispatch
            final_results = []
            for t_name in tasks:
                self.logger.info(f"Dispatching: {t_name}")
                agent = registry.get_agent(t_name)
                if not agent: continue

                # Update status
                status_data[t_name] = {"last_run_time": now_iso, "status": "running"}
                
                try:
                    # Pass message_thread_id if available to sub-agents
                    res = await agent.execute(chat_id, message_thread_id=params.message_thread_id)
                    status_data[t_name]["status"] = res.status
                    
                    # Specialized Output Handling
                    if t_name == "finance_monitor" and res.status == "SUCCESS":
                        report = res.data.get("report")
                        if report:
                            await self._safe_send(chat_id, f"📊 **财经自动快报** ({now.strftime('%H:%M')}):\n\n{report}", message_thread_id=params.message_thread_id)
                        elif params.is_manual:
                            await self.bot.send_message(chat_id, "ℹ️ 财经监控完成，暂无重大新增。", message_thread_id=params.message_thread_id)
                    
                    elif t_name == "daily_report" and res.status == "SUCCESS":
                        for r in res.data.get("reports", []):
                            title = "📑 **每日趋势总结**" if r['target'] == "general" else "🚀 **项目进化建议**"
                            await self._safe_send(chat_id, f"{title}\n\n{r['text']}", message_thread_id=params.message_thread_id)
                    
                    elif t_name == "dreamer" and res.status == "SUCCESS":
                        if "No new patterns" not in res.message:
                            await self.bot.send_message(chat_id, "🌙 **离线梦境报告**：已完成记忆巩固与升华。", message_thread_id=params.message_thread_id)

                    final_results.append({"task": t_name, "status": res.status})
                except Exception as e:
                    self.logger.error(f"Task {t_name} failed: {e}")
                    status_data[t_name]["status"] = f"error: {str(e)}"

            # Save status
            with open(self.STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(status_data, f, indent=2)

            return AgentResult(status="SUCCESS", message=f"Heartbeat complete: {final_results}")

        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e))
