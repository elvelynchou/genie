import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import trafilatura

class LinkExtractorInput(BaseModel):
    url: str = Field(..., description="The full URL to extract content from")
    format: str = Field("markdown", description="Output format: markdown or text")
    save_to_file: bool = Field(True, description="Whether to save the output as a .md file")

class LinkContentAgent(BaseAgent):
    name = "link_content_extractor"
    description = "Extracts main content from standard webpages and converts it to clean Markdown. DO NOT use this tool for X (Twitter), Weibo, or YouTube links; use specialized fetchers instead."
    input_schema = LinkExtractorInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads/web"

    async def run(self, params: LinkExtractorInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Extracting content from {params.url} for {chat_id}")
        
        logs = [{"step": "initialization", "url": params.url}]
        
        try:
            # 1. Fetch HTML using Playwright
            html_content = await self._fetch_html(params.url, logs)
            
            # 2. Extract content using Trafilatura
            extracted_content = trafilatura.extract(
                html_content, 
                output_format='txt' if params.format == 'text' else 'markdown',
                include_links=True,
                include_images=True
            )
            
            if not extracted_content:
                return AgentResult(
                    status="FAILED",
                    message="Failed to extract any meaningful content from the page.",
                    logs=logs
                )
            
            result_data = {"content": extracted_content}
            
            # 3. Save to file if requested
            if params.save_to_file:
                os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
                # Date + chat_id + safe_url
                date_str = datetime.now().strftime("%Y%m%d")
                safe_url = "".join([c for c in params.url if c.isalnum() or c in ('-', '_')]).strip()[:30]
                file_name = f"{date_str}_{chat_id}_{safe_url}.md"
                file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Content from {params.url}\n\n")
                    f.write(extracted_content)
                
                result_data["file_path"] = file_path
                logs.append({"step": "file_saved", "path": file_path})

            return AgentResult(
                status="SUCCESS",
                data=result_data,
                message=f"Successfully extracted content from {params.url}.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Extraction failed: {e}", exc_info=True)
            return AgentResult(
                status="FAILED",
                errors=str(e),
                message=f"Failed to extract content: {e}",
                logs=logs
            )

    async def _fetch_html(self, url: str, logs: list) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)
            
            logs.append({"step": "browser_navigating", "url": url})
            
            try:
                # Use 'domcontentloaded' instead of 'networkidle' for better reliability
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Small wait for dynamic content
                await asyncio.sleep(3)
                # Optional: Scroll down to trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
            except Exception as e:
                self.logger.warning(f"Initial navigation failed for {url}: {e}. Retrying with minimal wait...")
                # Fallback: Just wait for the initial commit
                await page.goto(url, wait_until="commit", timeout=30000)
                await asyncio.sleep(5)
            
            html = await page.content()
            await browser.close()
            
            logs.append({"step": "html_fetched", "size": len(html)})
            return html
