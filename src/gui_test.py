import asyncio
from playwright.async_api import async_playwright
import os

async def run():
    print(f"Testing GUI on DISPLAY: {os.environ.get('DISPLAY')}")
    try:
        async with async_playwright() as p:
            # Try to launch Firefox
            browser = await p.firefox.launch(headless=False)
            page = await browser.new_page()
            await page.goto("https://x.com/login")
            print("Successfully opened Firefox GUI!")
            await asyncio.sleep(30)
            await browser.close()
    except Exception as e:
        print(f"Error launching GUI: {e}")

if __name__ == "__main__":
    asyncio.run(run())
