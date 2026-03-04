import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class TrendAnalyzerInput(BaseModel):
    raw_contents: str = Field(..., description="The combined raw text data to analyze.")
    target: str = Field("general", description="The analysis target: 'social' (for X/Threads), 'evolution' (for project optimization), or 'general'.")
    save_report: bool = Field(True, description="Whether to save the analysis as a markdown report file.")

class TrendAnalyzerAgent(BaseAgent):
    name = "trend_analyzer"
    description = "Analyzes raw trend data (GitHub, X, etc.) and generates structured insights."
    input_schema = TrendAnalyzerInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: TrendAnalyzerInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator not provided to Analyzer Agent.")

        logs = [{"step": "initialization", "target": params.target}]
        
        # Select Prompt Template with deep project context
        prompts = {
            "social": "你是一个资深科技博主。请根据以下趋势内容，写一份吸引人的、适合在 X 和 Threads 上发布的社交媒体文案。包含 Emoji、热门项目点评和相关 Hashtags。要求专业且具有前瞻性。",
            "evolution": f"""你是一个顶尖 AI 架构师。请深入分析以下内容，寻找对当前 'GenieBot' 项目有“降维打击”意义的进化建议。
            
            【当前项目技术栈 & 状态】：
            1. 记忆系统：L1/L2/L3 三层 Redis 混合记忆 + 后台异步 'MemoryRefiner' 认知精炼引擎。
            2. 浏览器能力：集成 'stealth_browser'（基于 Nodriver 和 Camoufox），支持 BrowserForge 指纹伪装和 CDP 级别控制。
            3. 插件架构：采用 Gemini CLI 'Pure Skill' 模式，工具与主程序解耦，按需触发。
            4. 多模态：集成 Vertex AI, Nanobanana, ModelScope 的图生图/文生图，具备 Template Engine 实现 Identity Lock。
            5. 调度层：支持多步推理 (Reasoning Loop) 和状态共享。

            【任务】：
            对比以上趋势内容，如果发现有技术、库或思路在性能、隐身性、或智能化程度上显著优于我们当前的实现，请给出具体的进化建议。
            - 如果某个趋势我们已经实现了（如 Browser-use 类似的控制），除非其方案更优，否则不要重复建议。
            - 关注：更高效的上下文压缩算法、更强的反爬逃逸技术、更自动化的 Agent 自我纠错机制。
            """,
            "general": "你是一个技术分析师。请总结以下趋势，指出当下的技术风向标，并列出 3-5 个最值得关注的项目及其核心价值。"
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
