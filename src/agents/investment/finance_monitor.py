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
    custom_sources: Optional[List[Dict[str, str]]] = Field(None, description="Optional list of {name, url} to monitor.")

class FinanceMonitorAgent(BaseAgent):
    name = "finance_monitor"
    description = "Drives the financial monitoring pipeline: Batch Browser -> Parallel AI Processing -> Report."
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
        
        all_actions = []
        source_order = []
        for s in sources:
            all_actions.append({"action": "goto", "params": {"url": s["url"]}})
            all_actions.append({"action": "wait", "params": {"seconds": 8}})
            all_actions.append({"action": "extract_semantic"})
            source_order.append(s["name"])

        browser = registry.get_agent("stealth_browser")
        cleaner = registry.get_agent("finance_cleaner")
        
        # 2. 浏览器抓取阶段
        self.logger.info("Step 1: Executing batch stealth browsing...")
        res = await browser.execute(chat_id, engine="camoufox", headless=True, actions=all_actions)
        
        if res.status != "SUCCESS":
            return AgentResult(status="FAILED", errors=res.errors, message="Batch browsing failed.")

        # 3. 解析结果并并行清洗
        results = res.data.get("results", [])
        semantic_data_blocks = [r["data"] for r in results if r.get("type") == "semantic_tree"]
        
        total_blocks = len(semantic_data_blocks)
        if total_blocks == 0:
            return AgentResult(status="SUCCESS", message="No content extracted.")

        self.logger.info(f"Step 2: Processing {total_blocks} source blocks in PARALLEL...")
        digest_payload = ""
        generated_files = []
        date_str = datetime.now().strftime("%Y%m%d_%H%M")

        # 核心优化：并行处理函数
        async def process_single_source(idx, raw_text):
            if idx >= len(source_order): return None
            name = source_order[idx]
            try:
                # 3.1 AI 清洗
                clean_res = await cleaner.run(params=cleaner.input_schema(raw_text=str(raw_text), source_name=name), chat_id=chat_id)
                if clean_res.status != "SUCCESS" or not clean_res.data.get("clean_md"): return None
                
                clean_md = clean_res.data["clean_md"]
                item_hash = hashlib.md5(clean_md.encode()).hexdigest()
                is_seen = self.redis_mgr.client.sismember(f"seen_finance:{chat_id}", item_hash)
                
                if not is_seen or "🚨" in clean_md:
                    # 3.2 AI 向量化与实体提取 (并行)
                    loop = asyncio.get_event_loop()
                    tasks = [
                        asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.get_embedding(clean_md)), timeout=60),
                        asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.extract_entities(clean_md)), timeout=60)
                    ]
                    embedding, entities = await asyncio.gather(*tasks)
                    
                    # 3.3 存储与归档
                    if embedding:
                        await self.redis_mgr.store_vector(
                            doc_id=f"fin_{name}_{date_str}_{chat_id}",
                            vector=embedding,
                            content=f"Source: {name} | Date: {date_str}\n{clean_md}",
                            entities=entities,
                            depth=2
                        )
                    
                    os.makedirs(self.SOURCE_DIR, exist_ok=True)
                    file_path = os.path.join(self.SOURCE_DIR, f"{name}_{date_str}.md")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"# {name} - {date_str}\n\n{clean_md}")
                    
                    self.redis_mgr.client.sadd(f"seen_finance:{chat_id}", item_hash)
                    self.redis_mgr.client.expire(f"seen_finance:{chat_id}", 172800)
                    return {"name": name, "md": clean_md, "path": file_path}
            except Exception as e:
                self.logger.error(f"Parallel process failed for {name}: {e}")
            return None

        # 启动并行任务流
        process_tasks = [process_single_source(i, text) for i, text in enumerate(semantic_data_blocks)]
        processed_results = await asyncio.gather(*process_tasks)

        for r_res in processed_results:
            if r_res:
                digest_payload += f"\n--- {r_res['name']} ---\n{r_res['md']}\n"
                generated_files.append(r_res['path'])

        if not digest_payload:
            return AgentResult(status="SUCCESS", message="No new content found.")

        # 4. 生成对比简报 (AI)
        self.logger.info("Step 3: Generating final digest...")
        last_report = self.redis_mgr.client.get(f"last_finance_digest:{chat_id}")
        last_report_text = last_report.decode('utf-8') if last_report else "无上期报告。"

        analysis_prompt = f"""
        你是一个专业的财经研究员。请对比分析以下情报汇总。
        【上期报告摘要】：{last_report_text[:1500]}
        【本期最新情报】：{digest_payload[:10000]}
        
        要求：仅报告新增或重大转折事件。如果没有变动，回复“今日市场暂无重大新变动”。
        语言：中文。格式：Markdown。
        """
        
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self.orchestrator.chat(analysis_prompt, [])),
                timeout=90
            )
            digest_text = self.orchestrator.process_response(response).get("content", "Analysis failed.")
        except:
            digest_text = "分析生成超时，请查看原始文件。"

        if "暂无重大新变动" in digest_text:
            return AgentResult(status="SUCCESS", message="No significant new changes.")

        self.redis_mgr.client.set(f"last_finance_digest:{chat_id}", digest_text)
        os.makedirs(self.FINANCE_DIR, exist_ok=True)
        digest_path = os.path.join(self.FINANCE_DIR, f"Research_Report_{date_str}.md")
        with open(digest_path, "w", encoding="utf-8") as f:
            f.write(f"# 财经研究报告 - {date_str}\n\n{digest_text}")

        # 发送原始文件
        for f in generated_files:
            await registry.get_agent("file_sender").execute(chat_id, file_path=f, delete_after_send=False)

        return AgentResult(
            status="SUCCESS",
            data={"file_path": digest_path, "report": digest_text},
            message=f"Pipeline complete. {len(generated_files)} sources processed."
        )
