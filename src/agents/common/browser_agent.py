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
        cx1 = x1 + (x2 - x1) * random.uniform(0.1, 0.4) + random.randint(-50, 50)
        cy1 = y1 + (y2 - y1) * random.uniform(0.1, 0.4) + random.randint(-50, 50)
        cx2 = x1 + (x2 - x1) * random.uniform(0.6, 0.9) + random.randint(-50, 50)
        cy2 = y1 + (y2 - y1) * random.uniform(0.6, 0.9) + random.randint(-50, 50)
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**3 * x1 + 3*(1-t)**2 * t * cx1 + 3*(1-t) * t**2 * cx2 + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2 * t * cy1 + 3*(1-t) * t**2 * cy2 + t**3 * y2
            points.append((x, y))
        return points

    @staticmethod
    async def human_type(type_func, backspace_func, text: str, error_rate=0.03):
        for char in text:
            if random.random() < error_rate:
                typo_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                await type_func(typo_char)
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await backspace_func()
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await type_func(char)
            await asyncio.sleep(random.uniform(0.05, 0.25))

class BrowserAgentInput(BaseModel):
    profile: str = Field("default", description="Browser profile name.")
    actions: List[Dict[str, Any]] = Field(..., description="List of actions to execute.")
    headless: bool = Field(True, description="Whether to run in headless mode.")
    keep_open: bool = Field(False, description="Whether to keep the browser window open.")
    engine: str = Field("camoufox", description="Automation engine: 'nodriver' or 'camoufox'.")

class BrowserAgent(BaseAgent):
    name = "stealth_browser"
    description = "Advanced stealth browser agent with Semantic Object Control (A11yTree). Supports role-based interaction and human-like behavior."
    input_schema = BrowserAgentInput
    
    PROFILES_BASE_DIR = "/etc/myapp/genie/profiles"
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    A11Y_EXTRACTOR_JS = """
    (() => {
        const results = [];
        const interactiveSelectors = 'button, a, input, textarea, select, [role], [aria-label], [data-testid]';
        const elements = document.querySelectorAll(interactiveSelectors);
        
        elements.forEach((el, index) => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || el.offsetWidth === 0) return;
            
            const rect = el.getBoundingClientRect();
            const role = el.getAttribute('role') || el.tagName.toLowerCase();
            const name = el.innerText?.trim() || el.getAttribute('aria-label') || el.placeholder || el.value || '';
            
            if (!name && !['input', 'textarea'].includes(el.tagName.toLowerCase())) return;
            
            results.push({
                role: role,
                name: name.substring(0, 100),
                pos: [Math.round(rect.left + rect.width/2), Math.round(rect.top + rect.height/2)]
            });
        });
        
        document.querySelectorAll('p, h1, h2, h3').forEach(el => {
            if (el.innerText.trim().length > 50) {
                results.push({ role: 'text', name: el.innerText.trim().substring(0, 300) });
            }
        });

        return results.map(r => r.role === 'text' ? `Text: ${r.name}` : `[${r.role.toUpperCase()}] "${r.name}" (pos: ${r.pos})`).join('\\n');
    })()
    """

    SEMANTIC_PROXY_JS = """
    window.GenieBridge = {
        findByRole: (role, name) => {
            const selectorMap = {
                'button': 'button, [role="button"]',
                'link': 'a',
                'textbox': 'input[type="text"], input:not([type]), textarea',
                'checkbox': 'input[type="checkbox"]',
                'heading': 'h1, h2, h3, h4, h5, h6',
                'combobox': 'input, select, [role="combobox"]'
            };
            const selector = selectorMap[role.toLowerCase()] || role;
            const elements = document.querySelectorAll(selector);
            for (let el of elements) {
                const text = (el.innerText || el.ariaLabel || el.placeholder || el.value || "").toLowerCase();
                if (text.includes(name.toLowerCase())) return el;
            }
            return null;
        }
    };
    """

    def __init__(self):
        super().__init__()
        self.fingerprint_gen = FingerprintGenerator()
        self.header_gen = HeaderGenerator()
        self.last_mouse_pos = (0, 0)

    async def _human_mouse_move(self, page, target_x, target_y, engine="camoufox"):
        steps = random.randint(15, 30)
        points = HumanBehavior.generate_bezier_curve(self.last_mouse_pos, (target_x, target_y), steps=steps)
        for x, y in points:
            if engine == "camoufox": await page.mouse.move(x, y)
            else: await page.mouse_move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.015))
        self.last_mouse_pos = (target_x, target_y)

    def _expand_selector(self, selector: str) -> str:
        if not selector: return selector
        if all(c not in selector for c in ['[', ']', '#', '.', '>', ' ']):
            return f"[data-testid='{selector}']"
        return selector

    async def run(self, params: BrowserAgentInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Starting {params.engine} for {chat_id} (Headless: {params.headless})")
        profile_path = os.path.join(self.PROFILES_BASE_DIR, params.profile)
        os.makedirs(profile_path, exist_ok=True)
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)

        logs = [{"step": "initialization", "engine": params.engine, "profile": params.profile}]
        try:
            if params.engine == "camoufox":
                return await self._run_camoufox(params, profile_path, chat_id, logs)
            return await self._run_nodriver(params, profile_path, chat_id, logs)
        except Exception as e:
            self.logger.error(f"Global browser error: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)

    async def _run_nodriver(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        browser = None
        try:
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

            browser = await uc.start(user_data_dir=profile_path, headless=params.headless, browser_args=["--no-sandbox"])
            page = browser.main_tab
            results_data = await self._execute_actions(page, params.actions, chat_id, params.profile, logs)
            if params.keep_open: await asyncio.sleep(900)

            page_content = ""
            for r in results_data:
                if r.get("type") in ["semantic_tree", "page_content"]:
                    if len(str(r.get("data", ""))) > len(page_content):
                        page_content = str(r.get("data", ""))

            return AgentResult(status="SUCCESS", data={"results": results_data, "page_content": page_content}, logs=logs)
        finally:
            if not params.keep_open and browser: browser.stop()

    async def _run_camoufox(self, params: BrowserAgentInput, profile_path: str, chat_id: str, logs: list) -> AgentResult:
        try:
            from camoufox.async_api import AsyncCamoufox
            if not params.headless:
                os.environ["DISPLAY"] = os.getenv("DISPLAY", ":20.0")
                os.environ["XAUTHORITY"] = os.getenv("XAUTHORITY", "/home/elvelyn/.Xauthority")

            async with AsyncCamoufox(headless=params.headless) as browser:
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
        """Nodriver 执行器"""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            if not action: continue
            p = item.get("params", {}); effective_params = {**item, **p}
            selector = effective_params.get("selector"); expanded = self._expand_selector(selector)
            self.logger.info(f"Action {i+1}: {action}")

            try:
                if action == "goto": await page.get(effective_params.get("url"))
                elif action == "wait": await asyncio.sleep(float(effective_params.get("seconds", 5)))
                elif action == "inject_semantic_proxy": await page.evaluate(self.SEMANTIC_PROXY_JS)
                elif action == "extract_semantic":
                    data = await page.evaluate(self.A11Y_EXTRACTOR_JS)
                    results.append({"type": "semantic_tree", "data": data})
                    self.logger.info(f"Extracted {len(data)} chars via JS-A11y.")
                elif action == "click":
                    if expanded:
                        elem = await page.select(expanded)
                        if elem: await elem.click()
                elif action == "type":
                    if expanded:
                        elem = await page.select(expanded)
                        if elem:
                            await elem.focus()
                            async def nt(c): await elem.send_keys(c)
                            async def nb(): await elem.send_keys("\b")
                            await HumanBehavior.human_type(nt, nb, str(effective_params.get("text", "")))
                elif action == "upload":
                    if expanded and effective_params.get("file_path"):
                        f_path = os.path.abspath(effective_params.get("file_path"))
                        self.logger.info(f"CDP-Injecting file: {f_path}")
                        try:
                            # 1. 使用物理选择器锁定元素
                            elem = await page.select(expanded)
                            if elem:
                                # 2. 通过后端节点 ID 进行 CDP 原生注入
                                await page.send(uc.cdp.dom.set_file_input_files(
                                    files=[f_path], 
                                    backend_node_id=elem.backend_node_id
                                ))
                                self.logger.info("✅ Native CDP upload command sent.")
                                # 3. 物理触发一次页面重绘/激活
                                await page.evaluate("window.dispatchEvent(new Event('resize'))")
                                await asyncio.sleep(5)
                            else:
                                self.logger.error(f"Upload failed: Element {expanded} not found.")
                        except Exception as ue:
                            self.logger.error(f"CDP upload failed: {ue}")
                elif action == "click_role":
                    role = effective_params.get("role"); name = effective_params.get("name")
                    await page.evaluate(f"GenieBridge.findByRole('{role}', '{name}').click()")
                elif action == "type_role":
                    role = effective_params.get("role"); name = effective_params.get("name")
                    text = str(effective_params.get("text", ""))
                    await page.evaluate(f"(() => {{ const el = GenieBridge.findByRole('{role}', '{name}'); el.value = '{text}'; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }})()")
                elif action == "snapshot":
                    path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.png")
                    await page.save_screenshot(path)
                    results.append({"type": "screenshot", "file_path": path})
            except Exception as e:
                self.logger.error(f"Action {action} failed: {e}")
                results.append({"type": "error", "data": str(e)})
        return results

    async def _execute_camoufox_actions(self, page, actions, chat_id, profile, logs):
        """Camoufox 执行器"""
        results = []
        for i, item in enumerate(actions):
            action = item.get("action")
            if not action: continue
            p = item.get("params", {}); effective_params = {**item, **p}
            selector = effective_params.get("selector"); expanded = self._expand_selector(selector)
            self.logger.info(f"Action {i+1}: {action}")

            try:
                if action == "goto":
                    await page.goto(effective_params.get("url"), wait_until="domcontentloaded", timeout=60000)
                elif action == "wait":
                    await asyncio.sleep(float(effective_params.get("seconds", 5)))
                elif action == "inject_semantic_proxy":
                    await page.evaluate(self.SEMANTIC_PROXY_JS)
                elif action == "click_role":
                    role = effective_params.get("role"); name = effective_params.get("name")
                    locator = page.get_by_role(role, name=name).first
                    await locator.scroll_into_view_if_needed()
                    box = await locator.bounding_box()
                    if box:
                        await self._human_mouse_move(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await page.mouse.click(self.last_mouse_pos[0], self.last_mouse_pos[1])
                    else: await locator.click()
                elif action == "type_role":
                    role = effective_params.get("role"); name = effective_params.get("name")
                    text = str(effective_params.get("text", ""))
                    locator = page.get_by_role(role, name=name).first
                    await locator.focus()
                    async def ft(c): await page.keyboard.type(c)
                    async def fb(): await page.keyboard.press("Backspace")
                    await HumanBehavior.human_type(ft, fb, text)
                elif action == "extract_semantic":
                    data = await page.evaluate(self.A11Y_EXTRACTOR_JS)
                    results.append({"type": "semantic_tree", "data": data})
                    self.logger.info(f"Extracted {len(data)} chars via JS-A11y.")
                elif action == "click":
                    if expanded: await page.click(expanded, timeout=10000)
                elif action == "type":
                    if expanded:
                        await page.focus(expanded)
                        await page.keyboard.type(str(effective_params.get("text", "")))
                elif action == "upload":
                    if expanded and effective_params.get("file_path"):
                        await page.set_input_files(expanded, os.path.abspath(effective_params.get("file_path")))
                elif action == "snapshot":
                    path = os.path.join(self.DOWNLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.png")
                    await page.screenshot(path=path)
                    results.append({"type": "screenshot", "file_path": path})
            except Exception as e:
                self.logger.error(f"Action {action} failed: {e}")
                results.append({"type": "error", "data": str(e)})
        return results
