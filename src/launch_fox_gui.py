import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    os.environ["DISPLAY"] = ":20.0"
    os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"
    
    print("Launching Firefox...")
    async with async_playwright() as p:
        # Launch with no sandbox and no gpu
        browser = await p.firefox.launch(
            headless=False,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page()
        print("Navigating...")
        await page.goto("https://x.com/login")
        print("Window should be open. Please check your desktop.")
        await asyncio.sleep(900)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
