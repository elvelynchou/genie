import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class FinanceMonitorInput(BaseModel):
    sources: List[str] = Field(default=["Reuters", "Bloomberg", "WSJ"], description="The news sources to monitor.")
    keywords: List[str] = Field(default=["market", "economy", "fed", "rate"], description="Focus keywords.")

class FinanceMonitorAgent(BaseAgent):
    name = "finance_monitor"
    description = "Monitors financial news from X, Google News, and Reddit every 30 mins and generates a consolidated MD report."
    input_schema = FinanceMonitorInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: FinanceMonitorInput, chat_id: str) -> AgentResult:
        if not self.orchestrator or not self.redis_mgr:
            return AgentResult(status="FAILED", message="Dependencies missing.")

        self.logger.info(f"Starting finance monitoring for {chat_id}")
        logs = [{"step": "initialization", "sources": params.sources}]
        
        # 1. Target Sources (Mapping handle names for X)
        x_handles = {
            "Reuters": "https://x.com/Reuters",
            "Bloomberg": "https://x.com/business",
            "WSJ": "https://x.com/WSJ"
        }

        combined_raw_data = ""
        
        # 2. Data Gathering Phase
        xfetcher = registry.get_agent("gemini_cli_executor")
        
        for source in params.sources:
            url = x_handles.get(source)
            if not url: continue
            
            self.logger.info(f"Gathering from {source}...")
            logs.append({"step": f"fetching_{source}", "url": url})
            
            # Using our pure skill xfetcher via CLI
            # Note: We ask it to get the timeline/recent posts
            cmd_prompt = f"Use x-tweet-fetcher to get the latest 5 posts from {url} and return as text."
            
            try:
                res = await xfetcher.execute(chat_id, action="execute", prompt=cmd_prompt, yolo=True)
                if res.status == "SUCCESS":
                    content = res.data.get("output", "")
                    combined_raw_data += f"\n--- Source: {source} ---\n{content}\n"
                else:
                    self.logger.warning(f"Failed to fetch {source}: {res.errors}")
            except Exception as e:
                self.logger.error(f"Error fetching {source}: {e}")

        # 3. Analysis & Synthesis Phase
        analysis_prompt = f"""
        你是一个专业的华尔街高级分析师。请分析以下最新的财经资讯摘要：
        
        {combined_raw_data[:8000]}
        
        任务：
        1. 提炼出当前市场最核心的 3 个动态。
        2. 识别是否有任何重大的利好或利空预警。
        3. 对 elvelyn 的投资操作给出一个简短的“情绪评分”（1-10，10为极度乐观）。
        
        输出要求：
        - 使用标准的 Markdown 格式。
        - 必须包含今日日期和具体来源。
        - 语言为中文。
        """

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(analysis_prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            report_text = processed.get("content", "Analysis failed.")

            # 4. Save to Disk
            os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            file_name = f"finance_report_{date_str}.md"
            file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# 财经半小时快报 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write(report_text)
            
            logs.append({"step": "report_saved", "path": file_path})

            # 5. Update State in Redis (Record the timestamp of last check)
            await self.redis_mgr.set_state(chat_id, {"last_finance_check": datetime.now().isoformat()})

            return AgentResult(
                status="SUCCESS",
                data={"file_path": file_path, "content": report_text},
                message=f"Finance report generated at {file_path}",
                logs=logs,
                next_steps=["file_sender"]
            )

        except Exception as e:
            self.logger.error(f"Synthesis failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
