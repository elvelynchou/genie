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
import math

class HumanBehavior:
    """Helper to simulate human-like interactions (Bezier curves, jitter, etc.)"""
    
    @staticmethod
    def generate_bezier_curve(start, end, steps=20):
        """Generates a cubic Bezier curve with randomized control points."""
        x1, y1 = start
        x2, y2 = end
        
        # Randomize control points to simulate human 'arc' and overshoot
        cx1 = x1 + (x2 - x1) * random.uniform(0.1, 0.4) + random.randint(-50, 50)
        cy1 = y1 + (y2 - y1) * random.uniform(0.1, 0.4) + random.randint(-50, 50)
        cx2 = x1 + (x2 - x1) * random.uniform(0.6, 0.9) + random.randint(-50, 50)
        cy2 = y1 + (y2 - y1) * random.uniform(0.6, 0.9) + random.randint(-50, 50)
        
        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier formula
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * cx1 + 3*(1-t) * t**2 * cx2 + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * cy1 + 3*(1-t) * t**2 * cy2 + t**3 * y2
            points.append((x, y))
        return points

    @staticmethod
    async def human_type(type_func, backspace_func, text: str, error_rate=0.03):
        """
        Simulates human typing: variable speed, occasional typos, and backspace corrections.
        type_func: async function to type a single char.
        backspace_func: async function to press backspace.
        """
        for char in text:
            # Occasional typo logic
            if random.random() < error_rate:
                typo_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                await type_func(typo_char)
                await asyncio.sleep(random.uniform(0.2, 0.5)) # Human 'oops' realization
                await backspace_func()
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            await type_func(char)
            # Natural variance in typing speed (faster for common patterns, slower for transitions)
            await asyncio.sleep(random.uniform(0.05, 0.25))

class BrowserAction(BaseModel):
    action: str = Field(..., description="Action to perform: goto, click, type, scroll, snapshot, wait, hover")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action (url, selector, text, etc.)")

class BrowserAgentInput(BaseModel):
    profile: str = Field("default", description="Browser profile name to maintain session/login.")
    actions: List[Dict[str, Any]] = Field(
        ..., 
        description="List of actions to execute. Example: [{'action': 'goto', 'params': {'url': 'https://example.com'}}, {'action': 'wait', 'params': {'seconds': 5}}, {'action': 'extract_semantic'}]",
    )
    headless: bool = Field(True, description="Whether to run in headless mode.")
    keep_open: bool = Field(False, description="Whether to keep the browser window open (max 15 mins).")
    engine: str = Field("camoufox", description="Automation engine: 'nodriver' (Chromium) or 'camoufox' (Firefox).")

class BrowserAgent(BaseAgent):
    name = "stealth_browser"
    description = "Advanced stealth browser agent. Actions: goto (url), click (selector/text), type (selector, text), wait (seconds), snapshot, extract_semantic. IMPORTANT: You MUST include 'extract_semantic' as an action to actually get the page content back."
    input_schema = BrowserAgentInput
    
    PROFILES_BASE_DIR = "/etc/myapp/genie/profiles"
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    def __init__(self):
        super().__init__()
        self.fingerprint_gen = FingerprintGenerator()
        self.header_gen = HeaderGenerator()
        self.last_mouse_pos = (0, 0)

    async def _human_mouse_move(self, page, target_x, target_y, engine="camoufox"):
        """Moves mouse to target using a Bezier curve."""
        steps = random.randint(15, 30)
        points = HumanBehavior.generate_bezier_curve(self.last_mouse_pos, (target_x, target_y), steps=steps)
        
        for x, y in points:
            if engine == "camoufox":
                await page.mouse.move(x, y)
            else:
                await page.mouse_move(x, y)
            # Human-like micro-delay
            await asyncio.sleep(random.uniform(0.005, 0.015))
        
        self.last_mouse_pos = (target_x, target_y)

    async def run(self, params: BrowserAgentInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Starting {params.engine} browser for {chat_id} (Profile: {params.profile}, Headless: {params.headless})")
        
        # 最后的防线：如果 actions 为空或包含空字典，尝试自动补全（针对急躁的模型）
        processed_actions = [a for a in params.actions if a and a.get("action")]
        if not processed_actions:
            self.logger.warning("Agent received empty actions. This usually means the LLM failed to generate parameters. Returning failure to force retry.")
            return AgentResult(status="FAILED", message="No valid browser actions provided. Please specify 'goto' and 'extract_semantic'.", logs=[])

        self.logger.info(f"Planned actions: {processed_actions}")
        
        profile_path = os.path.join(self.PROFILES_BASE_DIR, params.profile)
        os.makedirs(profile_path, exist_ok=True)
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

        logs = [{"step": "initialization", "engine": params.engine, "profile": params.profile}]
        
        try:
            if params.engine == "camoufox":
                result = await self._run_camoufox(params, profile_path, chat_id, logs)
            else:
                result = await self._run_nodriver(params, profile_path, chat_id, logs)
            
            self.logger.info(f"Browser agent run finished with status: {result.status}")
            return result
        except Exception as e:
            self.logger.error(f"Global browser run error: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)

    async def _run_nodriver(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        browser = None
        try:
            # Ensure DISPLAY is set for GUI mode
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

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

            # 核心优化：将提取到的最长文本直接扁平化到 data 根目录，方便 Orchestrator 读取
            page_content = ""
            for r in results_data:
                if r.get("type") in ["semantic_tree", "page_content", "page_text"]:
                    if len(str(r.get("data", ""))) > len(page_content):
                        page_content = str(r.get("data", ""))

            return AgentResult(
                status="SUCCESS",
                data={
                    "results": results_data, 
                    "page_content": page_content,
                    "profile": params.profile
                },
                message=f"{params.engine.capitalize()} task completed. Content length: {len(page_content)}",
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
            
            # Ensure DISPLAY is set for GUI mode
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

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
                
                # 核心优化：将提取到的最长文本直接扁平化到 data 根目录
                page_content = ""
                for r in results_data:
                    if r.get("type") in ["semantic_tree", "page_content", "page_text"]:
                        if len(str(r.get("data", ""))) > len(page_content):
                            page_content = str(r.get("data", ""))

                return AgentResult(
                    status="SUCCESS",
                    data={
                        "results": results_data, 
                        "page_content": page_content,
                        "profile": params.profile
                    },
                    message=f"Camoufox task completed. Content length: {len(page_content)}",
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
            if not action:
                self.logger.warning(f"Skipping action {i+1} because 'action' key is missing: {item}")
                continue
                
            p = item.get("params", {})
            if not isinstance(p, dict): p = {}
            effective_params = {**item, **p}
            
            self.logger.info(f"Executing Nodriver action {i+1}: {action} with params {effective_params}")
            
            if action == "goto":
                url = effective_params.get("url")
                timeout = effective_params.get("timeout", 60000) # Default to 60s
                if not url: raise ValueError(f"Action 'goto' missing 'url' parameter")
                try:
                    await page.get(url)
                except Exception as e:
                    self.logger.error(f"Nodriver goto failed for {url}: {e}")
                    results.append({"type": "error", "data": f"Goto failed: {str(e)}"})
            elif action == "click" or action == "hover":
                selector = effective_params.get("selector")
                text = effective_params.get("text")
                elem = None
                if selector:
                    elem = await page.select(selector)
                elif text:
                    elem = await page.find(text, best_match=True)
                
                if elem:
                    # 获取坐标并执行贝塞尔移动
                    # Note: nodriver elem has attributes for position
                    x = elem.attributes.get('x', random.randint(100, 500))
                    y = elem.attributes.get('y', random.randint(100, 500))
                    await self._human_mouse_move(page, x, y, engine="nodriver")
                    
                    if action == "click":
                        await elem.click()
                else:
                    raise ValueError(f"Element not found for {action}")
            elif action == "type":
                selector = effective_params.get("selector")
                text = str(effective_params.get("text", ""))
                elem = await page.select(selector)
                if elem:
                    await elem.focus()
                    # 使用统一的人类打字模拟引擎 (支持拼写错误回删)
                    async def nodriver_type(c): await elem.send_keys(c)
                    async def nodriver_backspace(): await elem.send_keys("\b")
                    await HumanBehavior.human_type(nodriver_type, nodriver_backspace, text)
            elif action == "extract_semantic":
                try:
                    ax_nodes = await page.send(uc.cdp.accessibility.get_full_ax_tree())
                    # 进化：使用压缩算法处理语义树
                    compressed_view = self._compress_ax_tree(ax_nodes)
                    # 同时标记为 semantic_tree 和 page_content 满足模型预期
                    results.append({"type": "semantic_tree", "data": compressed_view})
                    results.append({"type": "page_content", "data": compressed_view})
                    self.logger.info(f"Extracted semantic tree ({len(compressed_view)} chars)")
                except Exception as e:
                    self.logger.warning(f"Semantic extraction failed: {e}")
                    results.append({"type": "error", "data": f"Nodriver semantic failed: {str(e)}"})
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.png")
                await page.save_screenshot(path)
                results.append({"type": "screenshot", "file_path": path})
                self.logger.info(f"Saved screenshot to {path}")
            elif action == "wait":
                seconds = effective_params.get("seconds", 5)
                self.logger.info(f"Waiting for {seconds}s...")
                await asyncio.sleep(float(seconds))
            logs.append({"step": f"action_{i+1}", "action": action})
        return results

    # ... (rest of methods)

    async def _execute_camoufox_actions(self, page, actions, chat_id, profile, logs):
        """Action executor for camoufox (playwright-based)."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            if not action:
                self.logger.warning(f"Skipping Camoufox action {i+1} because 'action' key is missing: {item}")
                continue

            p = item.get("params", {})
            if not isinstance(p, dict): p = {}
            effective_params = {**item, **p}

            self.logger.info(f"Executing Camoufox action {i+1}: {action} with params {effective_params}")

            if action == "goto":
                url = effective_params.get("url")
                timeout = effective_params.get("timeout", 60000) # Default to 60s
                if not url: raise ValueError("goto requires url")
                try:
                    # 使用 60s 超时并等待 DOMContentLoaded 以提高速度
                    await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                except Exception as e:
                    self.logger.error(f"Camoufox goto failed for {url}: {e}")
                    results.append({"type": "error", "data": f"Goto failed: {str(e)}"})
            elif action == "click" or action == "hover":
                selector = effective_params.get("selector")
                text = effective_params.get("text")
                elem = None
                if selector:
                    elem = await page.wait_for_selector(selector)
                elif text:
                    elem = await page.get_by_text(text).first
                
                if elem:
                    box = await elem.bounding_box()
                    if box:
                        # 计算中心点 + 随机偏移
                        cx = box['x'] + box['width'] / 2 + random.randint(-5, 5)
                        cy = box['y'] + box['height'] / 2 + random.randint(-5, 5)
                        await self._human_mouse_move(page, cx, cy, engine="camoufox")
                        
                        if action == "click":
                            await page.mouse.click(cx, cy)
                    else:
                        # 兜底：如果拿不到 box，直接用 playwright 原生点击
                        await elem.click()
                else:
                    raise ValueError(f"Element not found for {action}")
            elif action == "type":
                selector = effective_params.get("selector")
                text = str(effective_params.get("text", ""))
                if selector:
                    await page.focus(selector)
                    # 使用统一的人类打字模拟引擎
                    async def fox_type(c): await page.keyboard.type(c)
                    async def fox_backspace(): await page.keyboard.press("Backspace")
                    await HumanBehavior.human_type(fox_type, fox_backspace, text)
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
                            return items.join('\\n');
                        }""")
                    results.append({"type": "semantic_tree", "data": text_content})
                    results.append({"type": "page_content", "data": text_content})
                    self.logger.info(f"Extracted semantic content ({len(text_content)} chars)")
                except Exception as e:
                    self.logger.warning(f"Camoufox semantic failed: {e}")
                    results.append({"type": "error", "data": f"Semantic extraction failed: {str(e)}"})
            elif action == "snapshot":
                path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}_fox.png")
                await page.screenshot(path=path)
                results.append({"type": "screenshot", "file_path": path})
                self.logger.info(f"Saved snapshot to {path}")
            elif action == "wait":
                seconds = effective_params.get("seconds", 5)
                self.logger.info(f"Waiting for {seconds}s...")
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
