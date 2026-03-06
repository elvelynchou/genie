import asyncio
import os
import sys

# Add src to path
sys.path.append("/etc/myapp/genie/src")

from agents.registry import registry
from agents.common.browser_agent import BrowserAgent

async def main():
    registry.register_agent(BrowserAgent())
    agent = registry.get_agent('stealth_browser')
    
    # Force GUI environment
    os.environ["DISPLAY"] = ":20" # Common for CRD, fallback to :0 if needed
    
    print("Launching Camoufox in GUI mode...")
    result = await agent.execute(
        chat_id='manual_login',
        engine='camoufox',
        profile='geclibot_profile',
        headless=False,
        keep_open=True,
        actions=[{'action': 'goto', 'params': {'url': 'https://x.com/login'}}]
    )
    print(f"Agent finished: {result.status}")

if __name__ == "__main__":
    asyncio.run(main())
