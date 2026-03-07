import asyncio
import sys
import os

# Ensure local imports work
sys.path.append(os.path.join(os.path.dirname(__file__)))

from redis_manager import RedisManager

async def seed():
    redis_mgr = RedisManager(db=0)
    
    print("🚀 Seeding L0 Instincts...")
    
    # 1. 财经监控本能
    await redis_mgr.set_instinct(
        trigger="/run_finance",
        agent_name="finance_monitor",
        args={}
    )
    print("✅ Seeded: /run_finance -> finance_monitor")

    # 2. X 登录本能
    await redis_mgr.set_instinct(
        trigger="/x_login",
        agent_name="stealth_browser",
        args={
            "engine": "nodriver",
            "headless": False,
            "profile": "geclibot_profile",
            "keep_open": True,
            "actions": [{"action": "goto", "params": {"url": "https://x.com/login"}}]
        }
    )
    print("✅ Seeded: /x_login -> stealth_browser (Chrome GUI)")

    print("\n🎉 L0 Layer Primed. Bot will now react with 'Muscle Memory' to these commands.")

if __name__ == "__main__":
    asyncio.run(seed())
