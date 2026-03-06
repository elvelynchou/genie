import asyncio
import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GUI_Final")

sys.path.append("/etc/myapp/genie/src")

from agents.registry import registry
from agents.common.browser_agent import BrowserAgent

async def main():
    try:
        # Mandatory environment variables for GUI
        os.environ["DISPLAY"] = ":20"
        os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"
        
        registry.register_agent(BrowserAgent())
        agent = registry.get_agent('stealth_browser')
        
        print(f"Launching stealth_browser (Camoufox) on DISPLAY {os.environ['DISPLAY']}...")
        print(f"Using profile: geclibot_profile")
        
        result = await agent.execute(
            chat_id='manual_login',
            engine='camoufox',
            profile='geclibot_profile',
            headless=False,  # FORCE GUI
            keep_open=True,
            actions=[
                {"action": "goto", "params": {"url": "https://x.com/login"}},
                {"action": "wait", "params": {"seconds": 5}}
            ]
        )
        print(f"Result Status: {result.status}")
        if result.status == "SUCCESS":
            print("Window opened successfully. Waiting for manual login...")
            await asyncio.sleep(900) # Keep open for 15 mins
        else:
            print(f"Failure: {result.errors}")
            
    except Exception as e:
        print(f"Fatal Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
