import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class XPubInput(BaseModel):
    content: str = Field(..., description="The text content to post on X.")
    profile: str = Field("default", description="The browser profile to use.")
    headless: bool = Field(True, description="Whether to run in headless mode.")

class XPubAgent(BaseAgent):
    name = "xpub"
    description = "Automates posting content to X (Twitter) using specialized stealth workflows."
    input_schema = XPubInput
    
    WORKFLOW_PATH = "/etc/myapp/genie/src/agents/socialpub/x_workflow.json"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: XPubInput, chat_id: str) -> AgentResult:
        if not os.path.exists(self.WORKFLOW_PATH):
            return AgentResult(status="FAILED", message="X workflow configuration missing.")

        with open(self.WORKFLOW_PATH, "r") as f:
            config = json.load(f)
            raw_steps = config.get("workflows", {}).get("post_tweet", [])

        if not raw_steps:
            return AgentResult(status="FAILED", message="Post tweet workflow not defined in config.")

        # 1. 注入内容到模板
        processed_actions = []
        for step in raw_steps:
            action = step.copy()
            if "params" in action and "text" in action["params"]:
                action["params"]["text"] = action["params"]["text"].replace("{content}", params.content)
            processed_actions.append(action)

        # 2. 调用 stealth_browser 执行
        browser = registry.get_agent("stealth_browser")
        self.logger.info(f"Initiating X post for profile: {params.profile}")
        
        try:
            res = await browser.execute(
                chat_id, 
                engine="camoufox", 
                headless=params.headless, 
                profile=params.profile,
                actions=processed_actions
            )
            
            if res.status == "SUCCESS":
                return AgentResult(
                    status="SUCCESS",
                    message=f"Successfully posted to X using profile '{params.profile}'.",
                    data={"profile": params.profile, "content_length": len(params.content)}
                )
            else:
                return AgentResult(status="FAILED", errors=res.errors, message="Browser failed to complete X workflow.")
                
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e))
