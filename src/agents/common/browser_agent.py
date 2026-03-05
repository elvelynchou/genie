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
            
            # AsyncCamoufox launch doesn't take user_data_dir directly in most versions
            # If persistence is needed, it's usually handled via context params, 
            # but for stealth news scraping, a fresh context is often better.
            async with AsyncCamoufox(
                headless=params.headless,
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
            if not isinstance(p, dict): p = {}
            effective_params = {**item, **p}
            
            if action == "goto":
                url = effective_params.get("url")
                if not url: raise ValueError(f"Action 'goto' missing 'url' parameter")
                await page.get(url)
            elif action == "extract_semantic":
                try:
                    ax_nodes = await page.send(uc.cdp.accessibility.get_full_ax_tree())
                    # 进化：使用压缩算法处理语义树
                    compressed_view = self._compress_ax_tree(ax_nodes)
                    results.append({"type": "semantic_tree", "data": compressed_view})
                except Exception as e:
                    self.logger.warning(f"Semantic extraction failed: {e}")
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.png")
                await page.save_screenshot(path)
                results.append({"type": "screenshot", "file_path": path})
            elif action == "wait":
                seconds = effective_params.get("seconds", 5)
                await asyncio.sleep(float(seconds))
            logs.append({"step": f"action_{i+1}", "action": action})
        return results

    def _compress_ax_tree(self, nodes) -> str:
        """
        核心进化：将原始 CDP 语义节点压缩为 LLM 友好的精简文本。
        过滤冗余容器，仅保留交互元素和核心文本。
        """
        compressed = []
        interesting_roles = ['button', 'link', 'textbox', 'heading', 'checkbox', 'searchbox', 'menuitem']
        
        for node in nodes:
            name = node.name.value if node.name and node.name.value else ""
            role = node.role.value if node.role else "unknown"
            
            # 过滤规则：必须有名字，或者是重要的交互角色
            if not name.strip() and role not in interesting_roles:
                continue
            
            # 进一步精简描述
            if role == 'statictext' or role == 'unknown':
                if len(name.strip()) > 5: # 忽略太短的杂碎文字
                    compressed.append(f"Text: {name.strip()}")
            else:
                compressed.append(f"[{role.upper()}] {name.strip()}")
        
        return "\n".join(compressed[:150]) # 限制长度防止 Token 溢出

    async def _execute_camoufox_actions(self, page, actions, chat_id, profile, logs):
        """Action executor for camoufox (playwright-based)."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            p = item.get("params", {})
            if not isinstance(p, dict): p = {}
            effective_params = {**item, **p}

            if action == "goto":
                url = effective_params.get("url")
                if not url: raise ValueError("goto requires url")
                await page.goto(url)
            elif action == "extract_semantic":
                # 进化：为 Camoufox 也增加语义压缩逻辑
                try:
                    text_content = ""
                    if hasattr(page, 'accessibility'):
                        snapshot = await page.accessibility.snapshot()
                        text_content = self._compress_playwright_ax(snapshot)
                    else:
                        # 兜底：使用 JS 提取精简 DOM 树
                        text_content = await page.evaluate("""() => {
                            const items = [];
                            document.querySelectorAll('button, a, input, h1, h2, h3, p').forEach(el => {
                                const text = el.innerText || el.placeholder || el.value;
                                if (text && text.length > 5) items.push(`[${el.tagName}] ${text.trim()}`);
                            });
                            return items.join('\n');
                        }""")
                    results.append({"type": "semantic_tree", "data": text_content})
                except Exception as e:
                    self.logger.warning(f"Camoufox semantic failed: {e}")
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}_fox.png")
                await page.screenshot(path=path)
                results.append({"type": "screenshot", "file_path": path})
            elif action == "wait":
                seconds = effective_params.get("seconds", 5)
                await asyncio.sleep(float(seconds))
            logs.append({"step": f"action_{i+1}", "action": action})
        return results

    def _compress_playwright_ax(self, snapshot, level=0) -> str:
        """递归处理 Playwright 语义快照"""
        lines = []
        name = snapshot.get('name', '')
        role = snapshot.get('role', '')
        
        if name and len(name.strip()) > 2:
            lines.append(f"{'  ' * level}[{role}] {name}")
            
        for child in snapshot.get('children', []):
            lines.append(self._compress_playwright_ax(child, level + 1))
            
        return "\n".join([l for l in lines if l.strip()])[:5000]
