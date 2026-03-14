import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from agents.registry import registry

class XPubInput(BaseModel):
    content: str = Field(..., description="The text content to post on X.")
    image_path: Optional[str] = Field(None, description="Local path to an image to upload.")
    profile: str = Field("geclibot_profile", description="The browser profile to use.")
    headless: bool = Field(True, description="Whether to run in headless mode.")
    engine: str = Field("nodriver", description="The browser engine to use (nodriver or camoufox).")

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
            if "params" in action:
                if "text" in action["params"]:
                    action["params"]["text"] = action["params"]["text"].replace("{content}", params.content)
                if "file_path" in action["params"] and params.image_path:
                    action["params"]["file_path"] = action["params"]["file_path"].replace("{image_path}", params.image_path)
            
            # 如果没有图片但步骤是关于图片的，可以跳过
            if "step" in action and "image" in action["step"] and not params.image_path:
                continue
                
            processed_actions.append(action)

        # 2. 调用 stealth_browser 执行
        browser = registry.get_agent("stealth_browser")
        self.logger.info(f"Initiating X post for profile: {params.profile} using engine: {params.engine}")
        
        try:
            res = await browser.execute(
                chat_id, 
                engine=params.engine, 
                headless=params.headless, 
                profile=params.profile,
                actions=processed_actions
            )
            
            if res.status == "SUCCESS":
                # 检查结果中是否有错误动作
                action_errors = [r["data"] for r in res.data.get("results", []) if r.get("type") == "error"]
                if action_errors:
                    return AgentResult(status="FAILED", errors="; ".join(action_errors), message="One or more actions in the X workflow failed.")

                # 提取可能的截图路径用于调试
                snapshot_path = None
                for r in res.data.get("results", []):
                    if r.get("type") == "screenshot":
                        snapshot_path = r.get("file_path")

                return AgentResult(
                    status="SUCCESS",
                    message=f"Successfully executed X workflow using profile '{params.profile}'.",
                    data={
                        "profile": params.profile, 
                        "content_length": len(params.content),
                        "debug_snapshot": snapshot_path
                    }
                )
            else:
                return AgentResult(status="FAILED", errors=res.errors, message="Browser failed to complete X workflow.")
                
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e))
