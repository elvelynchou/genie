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
    description = "Advanced stealth browser agent. Actions: goto (url), click (selector/text), type (selector, text), wait (seconds), snapshot, extract_semantic, inject_semantic_proxy. IMPORTANT: You MUST include 'extract_semantic' as an action to actually get the page content back."
    input_schema = BrowserAgentInput
    
    PROFILES_BASE_DIR = "/etc/myapp/genie/profiles"
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    # 核心进化：Page-Native Semantic Proxy Script
    SEMANTIC_PROXY_JS = """
    window.GenieBridge = {
        findEntity: (query) => {
            // Priority 1: X.com specific data-testid
            let el = document.querySelector(`[data-testid="${query}"]`);
            if (el) return el;
            
            // Priority 2: Precise text match for buttons/links
            const targets = document.querySelectorAll('button, a, [role="button"]');
            for (let t of targets) {
                if (t.innerText.trim().toLowerCase() === query.toLowerCase()) return t;
            }
            
            // Priority 3: Aria-label
            el = document.querySelector(`[aria-label="${query}"]`);
            if (el) return el;

            return null;
        },
        semanticClick: async (query) => {
            const el = window.GenieBridge.findEntity(query);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                await new Promise(r => setTimeout(r, 500));
                el.click();
                return true;
            }
            return false;
        },
        semanticType: async (query, text) => {
            const el = window.GenieBridge.findEntity(query);
            if (el) {
                el.focus();
                return true;
            }
            return false;
        }
    };
    """

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

    def _expand_selector(self, selector: str) -> str:
        """智能化选择器转换：将语义 ID 转换为 data-testid 选择器"""
        if not selector: return selector
        # 如果不是标准的 CSS 选择器且不包含特殊字符，认为是 X 的 data-testid
        if all(c not in selector for c in ['[', ']', '#', '.', '>', ' ']):
            return f"[data-testid='{selector}']"
        return selector

    async def run(self, params: BrowserAgentInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Starting {params.engine} browser for {chat_id} (Profile: {params.profile}, Headless: {params.headless})")
        
        processed_actions = [a for a in params.actions if a and a.get("action")]
        if not processed_actions:
            return AgentResult(status="FAILED", message="No valid actions.")

        profile_path = os.path.join(self.PROFILES_BASE_DIR, params.profile)
        os.makedirs(profile_path, exist_ok=True)
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

        logs = [{"step": "initialization", "engine": params.engine, "profile": params.profile}]
        
        try:
            if params.engine == "camoufox":
                result = await self._run_camoufox(params, profile_path, chat_id, logs)
            else:
                result = await self._run_nodriver(params, profile_path, chat_id, logs)
            return result
        except Exception as e:
            self.logger.error(f"Global browser run error: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)

    async def _run_nodriver(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        browser = None
        try:
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

            # 生成真实的指纹和分辨率
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

            page_content = ""
            for r in results_data:
                if r.get("type") in ["semantic_tree", "page_content"]:
                    if len(str(r.get("data", ""))) > len(page_content):
                        page_content = str(r.get("data", ""))

            return AgentResult(status="SUCCESS", data={"results": results_data, "page_content": page_content, "profile": params.profile}, logs=logs)
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
        finally:
            if not params.keep_open and browser:
                browser.stop()

    def _compress_ax_tree(self, nodes) -> str:
        """
        核心进化：将原始 CDP 语义节点压缩为 LLM 友好的精简文本。
        """
        # 兼容性处理：Nodriver 某些版本返回 dict {'nodes': [...]}
        actual_nodes = nodes
        if isinstance(nodes, dict) and 'nodes' in nodes:
            actual_nodes = nodes['nodes']
        
        if not isinstance(actual_nodes, list):
            return "No readable nodes found."

        compressed = []
        interesting_roles = ['button', 'link', 'textbox', 'heading', 'checkbox', 'searchbox', 'menuitem']
        
        for node in actual_nodes:
            # 兼容性处理：node 可能是对象也可能是字典
            if hasattr(node, 'name'):
                name = node.name.value if node.name and node.name.value else ""
                role = node.role.value if node.role else "unknown"
            else:
                # 字典模式
                name_val = node.get('name', {})
                name = name_val.get('value', '') if isinstance(name_val, dict) else ''
                role_val = node.get('role', {})
                role = role_val.get('value', 'unknown') if isinstance(role_val, dict) else 'unknown'
            
            if not name.strip() and role not in interesting_roles:
                continue
            
            if role == 'statictext' or role == 'unknown':
                if len(name.strip()) > 5:
                    compressed.append(f"Text: {name.strip()}")
            else:
                compressed.append(f"[{role.upper()}] {name.strip()}")
        
        return "\n".join(compressed[:150])

    async def _run_camoufox(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        try:
            from camoufox.async_api import AsyncCamoufox
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

            # 使用真实的指纹
            fp = self.fingerprint_gen.generate(browser="firefox", os="windows")

            async with AsyncCamoufox(
                headless=params.headless,
                human=True,
                screen=fp.screen,
                headers=fp.headers
            ) as browser:
                page = await browser.new_page()
                results_data = await self._execute_camoufox_actions(page, params.actions, chat_id, params.profile, logs)
                if params.keep_open: await asyncio.sleep(900)
                page_content = ""
                for r in results_data:
                    if r.get("type") in ["semantic_tree", "page_content"]:
                        if len(str(r.get("data", ""))) > len(page_content):
                            page_content = str(r.get("data", ""))
                return AgentResult(status="SUCCESS", data={"results": results_data, "page_content": page_content}, logs=logs)
        except Exception as e:
            return AgentResult(status="FAILED", errors=str(e), logs=logs)

    async def _execute_actions(self, page, actions, chat_id, profile, logs):
        """Nodriver executor with expanded selectors and semantic proxy."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            if not action: continue
            p = item.get("params", {}); effective_params = {**item, **p}
            
            # 智能扩展选择器
            selector = effective_params.get("selector")
            expanded_selector = self._expand_selector(selector) if selector else None
            self.logger.info(f"Nodriver {action} on {expanded_selector}")

            if action == "goto":
                await page.get(effective_params.get("url"))
            elif action == "inject_semantic_proxy":
                await page.evaluate(self.SEMANTIC_PROXY_JS)
            elif action == "click":
                # 优先语义代理
                try:
                    if selector:
                        if await page.evaluate(f"window.GenieBridge ? window.GenieBridge.semanticClick('{selector}') : false"):
                            continue
                except: pass
                if expanded_selector:
                    elem = await page.select(expanded_selector)
                    if elem: await elem.click()
            elif action == "type":
                try:
                    if selector: await page.evaluate(f"window.GenieBridge ? window.GenieBridge.semanticType('{selector}') : false")
                except: pass
                if expanded_selector:
                    elem = await page.select(expanded_selector)
                    if elem:
                        await elem.focus()
                        async def nt(c): await elem.send_keys(c)
                        async def nb(): await elem.send_keys("\b")
                        await HumanBehavior.human_type(nt, nb, str(effective_params.get("text", "")))
            elif action == "extract_semantic":
                nodes = await page.send(uc.cdp.accessibility.get_full_ax_tree())
                data = self._compress_ax_tree(nodes)
                results.append({"type": "semantic_tree", "data": data})
            elif action == "wait":
                await asyncio.sleep(float(effective_params.get("seconds", 5)))
        return results

    async def _execute_camoufox_actions(self, page, actions, chat_id, profile, logs):
        """Camoufox executor with expanded selectors."""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            if not action: continue
            p = item.get("params", {}); effective_params = {**item, **p}
            selector = effective_params.get("selector")
            expanded_selector = self._expand_selector(selector) if selector else None

            if action == "goto":
                await page.goto(effective_params.get("url"), wait_until="domcontentloaded")
            elif action == "inject_semantic_proxy":
                await page.evaluate(self.SEMANTIC_PROXY_JS)
            elif action == "click":
                try:
                    if selector:
                        if await page.evaluate(f"window.GenieBridge ? window.GenieBridge.semanticClick('{selector}') : false"): continue
                except: pass
                if expanded_selector: await page.click(expanded_selector)
            elif action == "type":
                try:
                    if selector: await page.evaluate(f"window.GenieBridge ? window.GenieBridge.semanticType('{selector}') : false")
                except: pass
                if expanded_selector:
                    await page.focus(expanded_selector)
                    async def ft(c): await page.keyboard.type(c)
                    async def fb(): await page.keyboard.press("Backspace")
                    await HumanBehavior.human_type(ft, fb, str(effective_params.get("text", "")))
            elif action == "extract_semantic":
                if hasattr(page, 'accessibility'):
                    snap = await page.accessibility.snapshot()
                    data = self._compress_playwright_ax(snap)
                    results.append({"type": "semantic_tree", "data": data})
            elif action == "wait":
                await asyncio.sleep(float(effective_params.get("seconds", 5)))
        return results

    def _compress_playwright_ax(self, snapshot, level=0) -> str:
        lines = []
        name = snapshot.get('name', ''); role = snapshot.get('role', '')
        if name and len(name.strip()) > 2: lines.append(f"{'  ' * level}[{role}] {name}")
        for child in snapshot.get('children', []): lines.append(self._compress_playwright_ax(child, level + 1))
        return "\n".join([l for l in lines if l.strip()])[:5000]
