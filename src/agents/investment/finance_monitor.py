import os
import asyncio
import json
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class FinanceMonitorInput(BaseModel):
    # Now driven by JSON, but allows override
    custom_sources: Optional[List[Dict[str, str]]] = Field(None, description="Optional list of {name, url} to monitor.")

class FinanceMonitorAgent(BaseAgent):
    name = "finance_monitor"
    description = "Drives the financial monitoring pipeline: Browser -> Cleaner -> RAG -> Report."
    input_schema = FinanceMonitorInput
    
    CONFIG_PATH = "/etc/myapp/genie/src/agents/investment/sources.json"
    SOURCE_DIR = "/etc/myapp/genie/downloads/web"
    FINANCE_DIR = "/etc/myapp/genie/downloads/finance"

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: FinanceMonitorInput, chat_id: str) -> AgentResult:
        if not self.orchestrator or not self.redis_mgr:
            return AgentResult(status="FAILED", message="Dependencies missing.")

        # 1. Load Sources
        sources = []
        if params.custom_sources:
            sources = params.custom_sources
        else:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    sources = config.get("finance_sources", [])
        
        if not sources:
            return AgentResult(status="FAILED", message="No sources defined.")

        self.logger.info(f"Starting pipeline for {len(sources)} sources.")
        logs = [{"step": "initialization", "count": len(sources)}]
        
        browser = registry.get_agent("stealth_browser")
        cleaner = registry.get_agent("finance_cleaner")
        
        digest_payload = ""
        generated_files = []
        date_str = datetime.now().strftime("%Y%m%d_%H%M")

        for s in sources:
            name = s["name"]
            url = s["url"]
            self.logger.info(f"Processing source: {name}")
            
            try:
                # 2. Stealth Browse
                actions = [
                    {"action": "goto", "params": {"url": url}},
                    {"action": "wait", "params": {"seconds": 10}},
                    {"action": "extract_semantic"}
                ]
                res = await browser.execute(chat_id, engine="camoufox", headless=True, actions=actions)
                
                if res.status != "SUCCESS": continue
                
                raw_text = ""
                for r in res.data.get("results", []):
                    if r.get("type") in ["semantic_tree", "page_text"]:
                        raw_text = str(r.get("data", ""))
                        break
                
                if not raw_text: continue

                # 3. Clean Data via Cleaner Agent
                clean_res = await cleaner.run(params=cleaner.input_schema(raw_text=raw_text, source_name=name), chat_id=chat_id)
                
                if clean_res.status == "SUCCESS":
                    clean_md = clean_res.data["clean_md"]
                    
                    # 4. Check Deduplication
                    item_hash = hashlib.md5(clean_md.encode()).hexdigest()
                    is_seen = self.redis_mgr.client.sismember(f"seen_finance:{chat_id}", item_hash)
                    
                    if not is_seen or "🚨" in clean_md:
                        # 5. Save Source MD (Per source) - Into 'web' folder
                        os.makedirs(self.SOURCE_DIR, exist_ok=True)
                        file_path = os.path.join(self.SOURCE_DIR, f"{name}_{date_str}.md")
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(f"# {name} - {date_str}\nURL: {url}\n\n{clean_md}")
                        generated_files.append(file_path)
                        
                        # 6. Store to RAG
                        embedding = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: self.orchestrator.get_embedding(clean_md)
                        )
                        if embedding:
                            await self.redis_mgr.store_vector(
                                doc_id=f"fin_{name}_{date_str}_{chat_id}",
                                vector=embedding,
                                content=f"Source: {name} | Date: {date_str}\n{clean_md}"
                            )
                        
                        digest_payload += f"\n--- {name} ---\n{clean_md}\n"
                        self.redis_mgr.client.sadd(f"seen_finance:{chat_id}", item_hash)
                        self.redis_mgr.client.expire(f"seen_finance:{chat_id}", 172800)

            except Exception as e:
                self.logger.error(f"Source {name} failed: {e}")

        if not digest_payload:
            return AgentResult(status="SUCCESS", message="No new content found across all sources.")

        # 获取上一次的报告内容以进行对比（减少冗余）
        last_report = self.redis_mgr.client.get(f"last_finance_digest:{chat_id}")
        last_report_text = last_report.decode('utf-8') if last_report else "无上期报告。"

        # 7. Generate Final Digest (Research Report) - Strict filtering
        analysis_prompt = f"""
        你是一个专业的财经研究员。请对比分析以下最新的多个来源的情报汇总。
        
        【参考背景：上期报告摘要】（请勿在此基础上重复）：
        {last_report_text[:2000]}

        【本期最新情报内容】：
        {digest_payload[:10000]}
        
        要求输出：
        1. 🚨 **新增/转折事件**：仅报告自上期以来新出现的事件或已有事件的重大转折。
        2. **增量影响评估**：这些新动态对市场产生的最新边际影响。
        3. 1-2 条具体的最新交易建议。
        
        【重要准则】：
        - **严禁重复**：如果某条新闻在上期已经出现且没有新进展，请彻底忽略。
        - **极度精简**：如果没有重大的新变动，请仅回复：今日市场暂无重大新变动。
        
        语言：中文。格式：Markdown。
        """
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(analysis_prompt, []))
        digest_text = self.orchestrator.process_response(response).get("content", "Analysis failed.")

        if "暂无重大新变动" in digest_text:
            return AgentResult(status="SUCCESS", message="No significant new changes to report.")

        # 更新 Redis 中的上期报告快照
        self.redis_mgr.client.set(f"last_finance_digest:{chat_id}", digest_text)

        os.makedirs(self.FINANCE_DIR, exist_ok=True)
        digest_path = os.path.join(self.FINANCE_DIR, f"Research_Report_{date_str}.md")
        with open(digest_path, "w", encoding="utf-8") as f:
            f.write(f"# 财经研究报告 - {date_str}\n\n{digest_text}")

        # 8. Send individual source files first (as requested)
        for f in generated_files:
            await registry.get_agent("file_sender").execute(chat_id, file_path=f, delete_after_send=False)

        # 9. Return the final report as the main result
        return AgentResult(
            status="SUCCESS",
            data={"file_path": digest_path, "report": digest_text},
            message=f"Finance pipeline complete. {len(generated_files)} sources updated and stored in RAG.",
            logs=logs,
            next_steps=["file_sender"]
        )
