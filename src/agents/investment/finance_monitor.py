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
    description = "Drives the financial monitoring pipeline: Batch Browser -> Stable Serial AI Processing -> Report."
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

        # 1. 加载配置
        sources = []
        if params.custom_sources:
            sources = params.custom_sources
        else:
            if os.path.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    sources = config.get("finance_sources", [])
        
        if not sources: return AgentResult(status="FAILED", message="No sources defined.")

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
        
        # 2. 浏览器抓取
        res = await browser.execute(chat_id, engine="camoufox", headless=True, actions=all_actions)
        if res.status != "SUCCESS":
            return AgentResult(status="FAILED", errors=res.errors, message="Batch browsing failed.")

        # 3. 解析与处理
        results = res.data.get("results", [])
        semantic_data_blocks = [r["data"] for r in results if r.get("type") == "semantic_tree"]
        
        digest_payload = ""
        generated_files = []
        date_str = datetime.now().strftime("%Y%m%d_%H%M")

        for idx, raw_text in enumerate(semantic_data_blocks):
            if idx >= len(source_order): break
            name = source_order[idx]
            self.logger.info(f"Processing {name} ({idx+1}/{len(semantic_data_blocks)})...")
            
            try:
                # 3.1 清洗
                clean_res = await cleaner.run(params=cleaner.input_schema(raw_text=str(raw_text), source_name=name), chat_id=chat_id)
                if clean_res.status != "SUCCESS" or not clean_res.data.get("clean_md"): continue
                
                clean_md = clean_res.data["clean_md"]
                item_hash = hashlib.md5(clean_md.encode()).hexdigest()
                
                # 3.2 落地文件 (无论是否重复，始终产生文件用于发送)
                os.makedirs(self.SOURCE_DIR, exist_ok=True)
                f_path = os.path.join(self.SOURCE_DIR, f"{name}_{date_str}.md")
                with open(f_path, "w", encoding="utf-8") as f:
                    f.write(f"# {name} - {date_str}\n\n{clean_md}")
                generated_files.append(f_path)

                # 3.3 去重校验：仅将“新内容”加入摘要分析和 RAG
                is_seen = self.redis_mgr.client.sismember(f"seen_finance:{chat_id}", item_hash)
                
                if not is_seen or "🚨" in clean_md:
                    # 向量化与实体提取 (Data Layer)
                    loop = asyncio.get_event_loop()
                    embedding = await asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.get_embedding(clean_md)), timeout=60)
                    entities = await asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.extract_entities(clean_md)), timeout=60)
                    
                    if embedding:
                        await self.redis_mgr.store_vector(
                            doc_id=f"fin_{name}_{date_str}_{chat_id}",
                            vector=embedding,
                            content=f"Source: {name} | Date: {date_str}\n{clean_md}",
                            entities=entities,
                            depth=2
                        )
                    
                    digest_payload += f"\n--- {name} ---\n{clean_md}\n"
                    self.redis_mgr.client.sadd(f"seen_finance:{chat_id}", item_hash)
                    self.redis_mgr.client.expire(f"seen_finance:{chat_id}", 172800)
                else:
                    self.logger.info(f"{name} content is duplicate. Skipping digest inclusion.")

            except Exception as e:
                self.logger.error(f"Failed to process {name}: {e}")

        # 4. 发送所有抓取到的分源文件 (核心改进：无论摘要结果如何都发送)
        self.logger.info(f"Sending {len(generated_files)} source files...")
        for f in generated_files:
            await registry.get_agent("file_sender").execute(chat_id, file_path=f, delete_after_send=False)

        if not digest_payload:
            return AgentResult(status="SUCCESS", message="No significant new changes in digest, but sources updated and sent.")

        # 5. 生成对比简报 (AI)
        self.logger.info("Generating final contextual report...")
        last_report = self.redis_mgr.client.get(f"last_finance_digest:{chat_id}")
        last_report_text = last_report.decode('utf-8') if last_report else "无上期报告。"

        analysis_prompt = f"对比上期：{last_report_text[:1500]}\n分析本期：{digest_payload[:10000]}\n仅报告新增重大事件。中文Markdown格式。"
        
        try:
            loop = asyncio.get_event_loop()
            resp = await asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.chat(analysis_prompt, [])), timeout=90)
            digest_text = self.orchestrator.process_response(resp).get("content", "Analysis failed.")
        except:
            digest_text = "分析生成超时，请查看原始分源文件。"

        # 6. 归档与返回
        if "暂无重大新变动" not in digest_text:
            self.redis_mgr.client.set(f"last_finance_digest:{chat_id}", digest_text)
            os.makedirs(self.FINANCE_DIR, exist_ok=True)
            report_path = os.path.join(self.FINANCE_DIR, f"Research_Report_{date_str}.md")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"# 财经研究报告 - {date_str}\n\n{digest_text}")
            
            return AgentResult(
                status="SUCCESS",
                data={"file_path": report_path, "report": digest_text},
                message=f"Pipeline complete. {len(generated_files)} sources processed."
            )
        else:
            return AgentResult(status="SUCCESS", message="No significant new changes in digest.")
