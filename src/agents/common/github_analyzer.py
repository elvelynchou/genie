import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class GithubAnalyzerInput(BaseModel):
    raw_contents: str = Field(..., description="The combined raw text data to analyze.")
    target: str = Field("general", description="The analysis target: 'social' (for X/Threads), 'evolution' (for project optimization), or 'general'.")
    save_report: bool = Field(True, description="Whether to save the analysis as a markdown report file.")

class GithubAnalyzerAgent(BaseAgent):
    name = "github_analyzer"
    description = "Analyzes raw GitHub trend data and generates structured insights for social media or project evolution."
    input_schema = GithubAnalyzerInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: GithubAnalyzerInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator not provided to Analyzer Agent.")

        logs = [{"step": "initialization", "target": params.target}]
        
        # Select Prompt Template
        prompts = {
            "social": "你是一个资深科技博主。请根据以下 GitHub 趋势内容，写一份吸引人的、适合在 X 和 Threads 上发布的社交媒体文案。包含 Emoji、热门项目点评和相关 Hashtags。要求专业且具有前瞻性。",
            "evolution": "你是一个 AI 架构师。请深入分析以下 GitHub 趋势内容，寻找对当前 'GenieBot (Multi-Agent 系统)' 项目有优化、进化参考价值的技术、库或思路。请给出具体的代码改进建议或新功能构想。",
            "general": "你是一个技术分析师。请总结以下 GitHub 趋势，指出当下的技术风向标，并列出 3-5 个最值得关注的项目及其核心价值。"
        }
        
        base_prompt = prompts.get(params.target, prompts["general"])
        # Ensure raw_contents is clean and capped
        content_to_analyze = params.raw_contents[:10000].replace("{", "{{").replace("}", "}}")
        full_prompt = f"{base_prompt}\n\nContent to analyze:\n{content_to_analyze}"

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.orchestrator.chat(full_prompt, [])
            )
            processed = self.orchestrator.process_response(response)
            analysis_text = processed.get("content", "Analysis failed.")

            result_data = {"analysis": analysis_text}

            # Save as report file
            if params.save_report:
                os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
                date_str = datetime.now().strftime("%Y%m%d")
                file_name = f"{date_str}_{chat_id}_analysis_{params.target}.md"
                file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# GitHub Trend Analysis - {params.target.upper()} - {date_str}\n\n")
                    f.write(analysis_text)
                
                result_data["file_path"] = file_path
                logs.append({"step": "report_saved", "path": file_path})

            return AgentResult(
                status="SUCCESS",
                data=result_data,
                message=f"GitHub analysis for {params.target} complete.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
