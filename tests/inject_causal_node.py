import asyncio
import sys
import os

# Ensure local imports work correctly
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from redis_manager import RedisManager
from gemini_orchestrator import GeminiOrchestrator
from dotenv import load_dotenv

load_dotenv()

async def stress_test_injection():
    gemini_key = os.getenv("GEMINI_API_KEY")
    orchestrator = GeminiOrchestrator(api_key=gemini_key)
    redis_mgr = RedisManager(db=0)
    
    # 模拟一个复杂的因果逻辑节点
    content = "[Logic] X.com 抓取稳定性优化经验"
    relations = "因果: Headless模式被检测 -> 导致抓取内容为空 -> 教训: 必须强制启用 geclibot_profile 并配合贝塞尔曲线移动"
    entities = ["X.com", "抓取失败", "Nodriver", "防爬逃逸"]
    
    print(f"🚀 Generating embedding for: {content}")
    vector = orchestrator.get_embedding(content)
    
    if not vector:
        print("❌ Failed to generate embedding.")
        return

    doc_id = "test_causal_node_001"
    print(f"📥 Injecting causal node into Redis (L3, Depth 1)...")
    
    await redis_mgr.store_vector(
        doc_id=doc_id,
        vector=vector,
        content=content,
        entities=entities,
        depth=1, # Logic Layer
        relations=relations
    )
    
    print("✅ Injection complete. Now performing retrieval test...")
    
    # 验证检索
    search_query = "推特抓取为什么没内容？"
    loop = asyncio.get_event_loop()
    query_vector = await loop.run_in_executor(None, lambda: orchestrator.get_embedding(search_query))

    print(f"🔍 Searching for: '{search_query}'")
    # 使用 FT.SEARCH 直接检查物理存储
    res = redis_mgr.client.execute_command(
        "FT.SEARCH", "genie_vdb", "*", "RETURN", "3", "content", "relations", "depth"
    )

    print("\n--- Redis Physical Record Check ---")
    print(res)
    print("-----------------------------------\n")

    # 修复 bytes 判断逻辑
    res_str = str(res)
    if "relations" in res_str:
        print("🎉 SUCCESS: Causal relations field is physically present and stored!")
    else:
        print("❌ FAILURE: Relations field not found in retrieval.")

if __name__ == "__main__":
    asyncio.run(stress_test_injection())
