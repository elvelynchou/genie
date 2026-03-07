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

        # 1. Load Config
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
        
        # 2. Browser Extraction
        res = await browser.execute(chat_id, engine="camoufox", headless=True, actions=all_actions)
        if res.status != "SUCCESS":
            return AgentResult(status="FAILED", errors=res.errors, message="Batch browsing failed.")

        # 3. Processing
        results = res.data.get("results", [])
        semantic_data_blocks = [r["data"] for r in results if r.get("type") == "semantic_tree"]
        
        digest_payload = ""
        full_status_quo = "" # 用于在无更新时描述当前情况
        generated_files = []
        date_str = datetime.now().strftime("%Y%m%d_%H%M")

        for idx, raw_text in enumerate(semantic_data_blocks):
            if idx >= len(source_order): break
            name = source_order[idx]
            self.logger.info(f"Processing {name} ({idx+1}/{len(semantic_data_blocks)})...")
            
            try:
                # 3.1 AI Cleaning
                clean_res = await cleaner.run(params=cleaner.input_schema(raw_text=str(raw_text), source_name=name), chat_id=chat_id)
                if clean_res.status != "SUCCESS" or not clean_res.data.get("clean_md"):
                    self.logger.warning(f"Cleaning failed for {name}")
                    continue
                
                clean_md = clean_res.data["clean_md"]
                full_status_quo += f"\n--- {name} ---\n{clean_md[:500]}...\n" # 记录概要
                
                # 3.2 落地文件 (无论是否重复)
                os.makedirs(self.SOURCE_DIR, exist_ok=True)
                f_path = os.path.join(self.SOURCE_DIR, f"{name}_{date_str}.md")
                with open(f_path, "w", encoding="utf-8") as f:
                    f.write(f"# {name} - {date_str}\n\n{clean_md}")
                generated_files.append({"name": name, "path": f_path})

                # 3.3 去重逻辑 (仅影响摘要和RAG)
                item_hash = hashlib.md5(clean_md.encode()).hexdigest()
                is_seen = self.redis_mgr.client.sismember(f"seen_finance:{chat_id}", item_hash)
                
                if not is_seen or "🚨" in clean_md:
                    self.logger.info(f"New content/alert detected for {name}. Indexing...")
                    loop = asyncio.get_event_loop()
                    try:
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
                    except Exception as ai_e:
                        self.logger.error(f"AI enrichment failed for {name}: {ai_e}")
                else:
                    self.logger.info(f"{name} is duplicate. Skipping digest.")

            except Exception as e:
                self.logger.error(f"Critical error processing {name}: {e}")

        # 4. 强制发送分源文件
        self.logger.info(f"Sending {len(generated_files)} source files...")
        file_sender = registry.get_agent("file_sender")
        for f_info in generated_files:
            try:
                await file_sender.execute(chat_id, file_path=f_info["path"], delete_after_send=False)
            except Exception as fe:
                self.logger.error(f"Failed to send file {f_info['path']}: {fe}")

        # 构造文件列表说明文本
        file_list_msg = "\n".join([f"- {f['name']}: `{f['path']}`" for f in generated_files])

        if not digest_payload:
            return AgentResult(
                status="SUCCESS", 
                data={"files": file_list_msg, "status_quo": full_status_quo},
                message="No significant new changes in digest."
            )

        # 5. 生成总结报告
        self.logger.info("Generating final report...")
        last_report = self.redis_mgr.client.get(f"last_finance_digest:{chat_id}")
        last_report_text = last_report.decode('utf-8') if last_report else "无上期报告。"

        analysis_prompt = f"对比上期：{last_report_text[:1500]}\n分析本期：{digest_payload[:10000]}\n仅报告新增重大事件。中文Markdown格式。"
        
        try:
            loop = asyncio.get_event_loop()
            resp = await asyncio.wait_for(loop.run_in_executor(None, lambda: self.orchestrator.chat(analysis_prompt, [])), timeout=90)
            digest_text = self.orchestrator.process_response(resp).get("content", "Analysis failed.")
        except:
            digest_text = "摘要分析超时，请查看上方分源原始文件。"

        if "暂无重大新变动" in digest_text:
            return AgentResult(
                status="SUCCESS", 
                data={"files": file_list_msg, "status_quo": full_status_quo, "report": digest_text},
                message="No significant new changes in digest."
            )

        # 6. 归档与返回最终摘要
        self.redis_mgr.client.set(f"last_finance_digest:{chat_id}", digest_text)
        os.makedirs(self.FINANCE_DIR, exist_ok=True)
        report_path = os.path.join(self.FINANCE_DIR, f"Research_Report_{date_str}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 财经研究报告 - {date_str}\n\n{digest_text}")

        return AgentResult(
            status="SUCCESS",
            data={"file_path": report_path, "report": digest_text, "files": file_list_msg},
            message=f"Pipeline complete. {len(generated_files)} sources processed."
        )
