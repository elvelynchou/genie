import asyncio
import os
import sys
import json
import logging

# Ensure local imports work
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.registry import registry
from agents.socialpub.xpub_agent import XPubAgent
from agents.common.browser_agent import BrowserAgent
from gemini_orchestrator import GeminiOrchestrator
from dotenv import load_dotenv

load_dotenv()

# Setup logging to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ManualXTest")

async def run_manual_test():
    # Setup dependencies
    orchestrator = GeminiOrchestrator(api_key=os.getenv("GEMINI_API_KEY"))
    registry.register_agent(BrowserAgent())
    xpub = XPubAgent(orchestrator=orchestrator)
    registry.register_agent(xpub)

    chat_id = "550914711"
    content = "中东局势骤变：IEA警告史上最大石油供应中断，油价重返$100。美外交政策大逆转，为压低油价放宽对俄制裁，引发欧美阵营裂痕。全球市场进入高波动‘定论期’。#财经 #能源危机 #地缘政治"
    image_path = "/etc/myapp/genie/downloads/20260313_142939_550914711.png"
    
    if not os.path.exists(image_path):
        logger.error(f"Image not found at {image_path}")
        return

    logger.info(f"Starting manual GUI X post test...")
    logger.info(f"Content: {content}")
    logger.info(f"Image: {image_path}")

    # Set DISPLAY for GUI
    os.environ["DISPLAY"] = ":20.0"
    os.environ["XAUTHORITY"] = "/home/elvelyn/.Xauthority"

    try:
        # We call run directly to force parameters
        from agents.socialpub.xpub_agent import XPubInput
        params = XPubInput(
            content=content,
            image_path=image_path,
            profile="geclibot_profile",
            headless=False, # GUI MODE
            engine="nodriver"
        )
        
        result = await xpub.run(params, chat_id)
        
        if result.status == "SUCCESS":
            logger.info("🎉 SUCCESS: Manual GUI X post executed!")
            print(f"\nFinal Message: {result.message}")
        else:
            logger.error(f"❌ FAILED: {result.message}")
            if result.errors:
                print(f"Errors: {result.errors}")
                
    except Exception as e:
        logger.error(f"Test crashed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(run_manual_test())
