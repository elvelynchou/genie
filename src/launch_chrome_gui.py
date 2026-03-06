import asyncio
import os
import sys
import nodriver as uc

async def main():
    try:
        # Try to detect or force DISPLAY
        os.environ["DISPLAY"] = ":20"
        os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"
        
        print(f"Attempting to launch Nodriver (Chrome) on {os.environ['DISPLAY']}...")
        
        browser = await uc.start(
            user_data_dir="/etc/myapp/genie/profiles/geclibot_profile",
            headless=False,
            browser_args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        page = browser.main_tab
        print("Navigating to X login...")
        await page.get("https://x.com/login")
        
        print("Success! If you see the window, please login.")
        # Keep open for 15 mins
        await asyncio.sleep(900)
        
    except Exception as e:
        print(f"Nodriver GUI failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
