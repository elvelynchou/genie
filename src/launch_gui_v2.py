import asyncio
import os
import sys
import logging

# Setup logging to see errors
logging.basicConfig(level=logging.INFO, filename='/etc/myapp/genie/gui_debug.log', filemode='w')
logger = logging.getLogger("GUI_Launcher")

sys.path.append("/etc/myapp/genie/src")

async def main():
    try:
        from camoufox.async_api import AsyncCamoufox
        
        # Explicitly set DISPLAY and XAUTHORITY in the environment
        os.environ["DISPLAY"] = ":20"
        os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"
        
        logger.info("Starting Camoufox in GUI mode...")
        print("Attempting to open browser window on DISPLAY :20...")
        
        async with AsyncCamoufox(
            headless=False,
            # We don't use user_data_dir here to avoid the earlier error, 
            # but we can try to use a persistent context if needed later.
        ) as browser:
            page = await browser.new_page()
            logger.info("Navigating to X login...")
            await page.goto("https://x.com/login")
            print("Success! Window should be visible now.")
            # Keep it open for 15 mins
            await asyncio.sleep(900)
            
    except Exception as e:
        logger.error(f"Failed to launch GUI: {e}", exc_info=True)
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
