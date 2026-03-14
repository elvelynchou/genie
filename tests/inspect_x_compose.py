import asyncio
import os
import sys

# Ensure local imports work
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.common.browser_agent import BrowserAgent, BrowserAgentInput

async def inspect_x_compose():
    agent = BrowserAgent()
    params = BrowserAgentInput(
        engine="nodriver",
        headless=False,
        profile="geclibot_profile",
        actions=[
            {"action": "goto", "params": {"url": "https://x.com/compose/post"}},
            {"action": "wait", "params": {"seconds": 10}},
            {"action": "extract_semantic"}
        ]
    )
    
    print("🚀 Inspecting X Compose Page...")
    # Set DISPLAY for GUI
    os.environ["DISPLAY"] = ":20.0"
    os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"
    
    result = await agent.run(params, chat_id="inspect_x")
    if result.status == "SUCCESS":
        content = result.data.get("page_content", "")
        print("\n--- Semantic Tree ---")
        print(content)
        print("--------------------")
    else:
        print(f"Failed: {result.errors}")

if __name__ == "__main__":
    asyncio.run(inspect_x_compose())
