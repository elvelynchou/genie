import os
import asyncio
from dotenv import load_dotenv
import redis

async def test_env_and_redis():
    load_dotenv()
    
    print("--- Environment Check ---")
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    print(f"TELEGRAM_BOT_TOKEN: {'[FOUND]' if tg_token and 'your_' not in tg_token else '[MISSING or DEFAULT]'}")
    print(f"GEMINI_API_KEY: {'[FOUND]' if gemini_key and 'your_' not in gemini_key else '[MISSING or DEFAULT]'}")

    print("\n--- Redis Check ---")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("Redis Connection: [OK]")
    except Exception as e:
        print(f"Redis Connection: [FAILED] - {e}")

if __name__ == "__main__":
    asyncio.run(test_env_and_redis())
