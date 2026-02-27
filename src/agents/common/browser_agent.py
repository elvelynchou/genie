import asyncio
import os
import json
import logging
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
import nodriver as uc
from browserforge.fingerprints import FingerprintGenerator
from browserforge.headers import HeaderGenerator

class BrowserAction(BaseModel):
    action: str = Field(..., description="Action to perform: goto, click, type, scroll, snapshot, wait, hover")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action (url, selector, text, etc.)")

class BrowserAgentInput(BaseModel):
    profile: str = Field("default", description="Browser profile name to maintain session/login.")
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="List of browser actions to execute.")
    headless: bool = Field(False, description="Whether to run in headless mode.")
    keep_open: bool = Field(False, description="Whether to keep the browser window open (max 15 mins).")
    engine: str = Field("nodriver", description="Automation engine: 'nodriver' (Chromium) or 'camoufox' (Firefox).")

class BrowserAgent(BaseAgent):
    name = "stealth_browser"
    description = "Advanced stealth browser agent. Supports 'nodriver' (default) and 'camoufox' (high-stealth Firefox) engines. Uses BrowserForge for fingerprinting."
    input_schema = BrowserAgentInput
    
    PROFILES_BASE_DIR = "/etc/myapp/genie/profiles"
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    def __init__(self):
        super().__init__()
        self.fingerprint_gen = FingerprintGenerator()
        self.header_gen = HeaderGenerator()

    async def run(self, params: BrowserAgentInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Starting {params.engine} browser for {chat_id} (Profile: {params.profile})")
        
        profile_path = os.path.join(self.PROFILES_BASE_DIR, params.profile)
        os.makedirs(profile_path, exist_ok=True)
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

        logs = [{"step": "initialization", "engine": params.engine, "profile": params.profile}]
        
        if params.engine == "camoufox":
            return await self._run_camoufox(params, profile_path, chat_id, logs)
        else:
            return await self._run_nodriver(params, profile_path, chat_id, logs)

    async def _run_nodriver(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        browser = None
        try:
            # Generate a consistent fingerprint for this session if it's a new profile
            fp = self.fingerprint_gen.generate(browser="chrome", os="windows")
            
            browser = await uc.start(
                user_data_dir=profile_path,
                headless=params.headless,
                browser_args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    f"--window-size={fp.screen.width},{fp.screen.height}",
                    f"--user-agent={fp.headers['User-Agent']}"
                ]
            )
            
            page = browser.main_tab
            results_data = await self._execute_actions(page, params.actions, chat_id, params.profile, logs)

            if params.keep_open:
                await asyncio.sleep(900)

            return AgentResult(
                status="SUCCESS",
                data={"results": results_data, "profile": params.profile},
                message=f"Nodriver task completed.",
                logs=logs
            )
        except Exception as e:
            self.logger.error(f"Nodriver failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
        finally:
            if not params.keep_open and browser:
                browser.stop()

    async def _run_camoufox(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        try:
            from camoufox.async_api import AsyncCamoufox
            
            # Camoufox handles most fingerprinting internally via BrowserForge integration
            async with AsyncCamoufox(
                user_data_dir=profile_path,
                headless=params.headless,
                # Additional camoufox config can be added here
            ) as browser:
                page = await browser.new_page()
                # Wrap camoufox page to match nodriver-like interface for _execute_actions
                # Actually, they have different APIs, so we need a shim or separate logic
                results_data = await self._execute_camoufox_actions(page, params.actions, chat_id, params.profile, logs)
                
                if params.keep_open:
                    await asyncio.sleep(900)
                
                return AgentResult(
                    status="SUCCESS",
                    data={"results": results_data, "profile": params.profile},
                    message="Camoufox task completed.",
                    logs=logs
                )
        except Exception as e:
            self.logger.error(f"Camoufox failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)

    async def _execute_actions(self, page, actions, chat_id, profile, logs):
        """Action executor for nodriver (uc)."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            p = item.get("params", {})
            if action == "goto":
                await page.get(p.get("url"))
            elif action == "extract_semantic":
                try:
                    ax_nodes = await page.send(uc.cdp.accessibility.get_full_ax_tree())
                    semantic_tree = []
                    for node in ax_nodes:
                        if node.name and node.name.value:
                            semantic_tree.append({
                                "role": node.role.value if node.role else "unknown",
                                "name": node.name.value,
                                "backend_id": node.backend_dom_node_id
                            })
                    results.append({"type": "semantic_tree", "data": semantic_tree[:100]})
                except Exception as e:
                    self.logger.warning(f"Semantic extraction failed: {e}")
            elif action == "click_node":
                backend_id = p.get("backend_id")
                obj = await page.send(uc.cdp.dom.resolve_node(backend_node_id=backend_id))
                await page.send(uc.cdp.runtime.call_function_on(
                    function_declaration="(elem) => elem.click()",
                    object_id=obj.object_id
                ))
            elif action == "click":
                elem = await page.select(p.get("selector")) if p.get("selector") else await page.find(p.get("text"), best_match=True)
                await elem.click()
            elif action == "type":
                elem = await page.select(p.get("selector"))
                for char in p.get("text"):
                    await elem.send_keys(char)
                    await asyncio.sleep(random.uniform(0.05, 0.15))
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.png")
                await page.save_screenshot(path)
                results.append({"type": "screenshot", "file_path": path})
            elif action == "wait":
                await asyncio.sleep(p.get("seconds", 5))
            logs.append({"step": f"action_{i+1}", "action": action})
        return results

    async def _execute_camoufox_actions(self, page, actions, chat_id, profile, logs):
        """Action executor for camoufox (playwright-based)."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            p = item.get("params", {})
            if action == "goto":
                await page.goto(p.get("url"))
            elif action == "extract_semantic":
                # For playwright, we can use accessibility snapshot
                tree = await page.accessibility.snapshot()
                results.append({"type": "semantic_tree", "data": tree})
            elif action == "click":
                if p.get("selector"):
                    await page.click(p.get("selector"))
                else:
                    await page.get_by_text(p.get("text")).click()
            elif action == "type":
                await page.fill(p.get("selector"), p.get("text"))
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}_fox.png")
                await page.screenshot(path=path)
                results.append({"type": "screenshot", "file_path": path})
            elif action == "wait":
                await asyncio.sleep(p.get("seconds", 5))
            logs.append({"step": f"action_{i+1}", "action": action})
        return results
