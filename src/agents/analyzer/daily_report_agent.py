import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class DailyReportInput(BaseModel):
    send_raw_files: bool = Field(False, description="Whether to send the raw markdown files from sources.")

class DailyReportAgent(BaseAgent):
    name = "daily_report"
    description = "Orchestrates the daily tech trend scanning and analysis pipeline."
    input_schema = DailyReportInput

    CONFIG_PATH = "/etc/myapp/genie/src/agents/analyzer/trend_sources.json"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: DailyReportInput, chat_id: str) -> AgentResult:
        self.logger.info("Starting daily report pipeline...")
        
        # 1. Load Sources
        tasks = []
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    tasks = config.get("tech_sources", [])
            except Exception as e:
                self.logger.error(f"Failed to load tech sources: {e}")
        
        if not tasks:
            tasks = [
                {"name": "Global", "url": "https://github.com/trending"},
                {"name": "AI Agent", "url": "https://github.com/search?q=ai+agent&type=repositories&s=stars&o=desc"}
            ]

        extractor = registry.get_agent("link_content_extractor")
        analyzer = registry.get_agent("trend_analyzer")
        
        combined_text = ""
        raw_file_paths = []

        # 2. Extract
        for task in tasks:
            res = await extractor.execute(chat_id, url=task["url"], save_to_file=True)
            if res.status == "SUCCESS":
                combined_text += f"\n--- Source: {task['name']} ---\n{res.data.get('content', '')[:3000]}"
                raw_file_paths.append(res.data.get("file_path"))

        # 3. Analyze
        targets = ["general", "evolution"]
        reports = []
        
        for target in targets:
            analysis_res = await analyzer.execute(chat_id, raw_contents=combined_text, target=target)
            if analysis_res.status == "SUCCESS":
                reports.append({
                    "target": target,
                    "text": analysis_res.data.get("analysis", ""),
                    "file_path": analysis_res.data.get("file_path")
                })

        # 4. Cleanup/Return (Sending is handled by the caller or specialized tool)
        return AgentResult(
            status="SUCCESS",
            data={
                "reports": reports,
                "raw_files": raw_file_paths if params.send_raw_files else []
            },
            message=f"Daily report generated from {len(tasks)} sources."
        )
