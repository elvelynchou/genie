import os
import json
import asyncio
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class NewspaperInput(BaseModel):
    summary_text: str = Field(..., description="The financial summary text.")

class NewspaperAgent(BaseAgent):
    name = "newspaper_renderer"
    description = "v3.0 Ultra-Dense Landscape: Renders a wide, information-packed vintage newspaper."
    input_schema = NewspaperInput
    
    TEMPLATE_PATH = "/etc/myapp/genie/src/agents/imgtools/genimgtemplate/newspaper.json"
    FINANCE_DIR = "/etc/myapp/genie/downloads/finance"

    def __init__(self, orchestrator=None, redis_mgr=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.redis_mgr = redis_mgr

    async def run(self, params: NewspaperInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator missing.")

        # 1. 物理读取全文
        content_to_analyze = params.summary_text
        today_pattern = os.path.join(self.FINANCE_DIR, f"Research_Report_{datetime.now().strftime('%Y%m%d')}*.md")
        report_files = glob.glob(today_pattern)
        if report_files:
            latest_report = max(report_files, key=os.path.getctime)
            with open(latest_report, "r", encoding="utf-8") as f:
                content_to_analyze = f.read()
        elif self.redis_mgr:
            tid = getattr(params, "message_thread_id", None)
            mem_key = f"{chat_id}:{tid or 'main'}"
            redis_data = self.redis_mgr.client.get(f"last_finance_digest:{mem_key}")
            if redis_data:
                content_to_analyze = redis_data.decode('utf-8')

        if not content_to_analyze: return AgentResult(status="FAILED", message="No content.")

        # 2. 深度主编逻辑：提取详细的版面内容 (要求输出更多细节)
        extraction_prompt = f"""
        你是一个顶尖财经报纸的总编。请为今日【横版大报】进行排版设计。
        
        待处理报告：
        {content_to_analyze}
        
        要求提取：
        1. 能源与地缘：提炼震撼头条 + 100字深度综述。
        2. 金融体系：提炼专栏标题 + 80字关键细节。
        3. 贸易与AI：提炼专栏标题 + 80字关键细节。
        4. 综合商业预警：提炼底部通报。
        
        输出 JSON 格式：
        {{
          "h1": "能源大头条", "b1": "深度摘要内容...",
          "h2": "金融专栏标题", "b2": "细节内容...",
          "h3": "政策专栏标题", "b3": "细节内容...",
          "footer": "底部简讯",
          "illus": "极简英文描述插图主题"
        }}
        """
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.orchestrator.chat(extraction_prompt, []))
            processed = self.orchestrator.process_response(response)
            data = json.loads(processed.get("content", "{}").replace("```json", "").replace("```", "").strip())
            
            today_str = datetime.now().strftime("%B %d, %Y")

            # 3. 构造 3:2 横版高密度 Prompt
            final_prompt = f"""
            Landscape 1950s financial broadsheet. Thin masthead '半小时金融与企业监控' at the top.
            Date line: '{today_str.upper()}'.
            
            LAYOUT:
            - TINY ILLUSTRATION: A small 1-inch ink sketch of {data.get('illus')} tucked in a corner.
            - COLUMN 1 (Leading): Headline: "{data.get('h1')}". Full Article: "{data.get('b1')}".
            - COLUMN 2: Headline: "{data.get('h2')}". Full Article: "{data.get('b2')}".
            - COLUMN 3: Headline: "{data.get('h3')}". Full Article: "{data.get('b3')}".
            - FOOTER: "{data.get('footer')}".
            
            STYLE: Extremely dense small serif text in 4 vertical columns. Very minimal white space. 
            Yellowed vintage newsprint texture. Authentic financial journal vibe. 
            Landscape orientation. Text must dominate the page.
            """

            # 4. 执行生图 (指定 3:2)
            vertex = registry.get_agent("vertex_generator")
            return await vertex.execute(chat_id, prompt_or_template=final_prompt, aspect_ratio="3:2")

        except Exception as e:
            self.logger.error(f"Newspaper v3 failed: {e}")
            return AgentResult(status="FAILED", errors=str(e))
