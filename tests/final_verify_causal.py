import asyncio
import sys
import os

# Ensure local imports work correctly
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from redis_manager import RedisManager
from gemini_orchestrator import GeminiOrchestrator
from dotenv import load_dotenv

load_dotenv()

async def final_verification():
    redis_mgr = RedisManager(db=0)
    redis_mgr.init_vector_index(dim=3072)
    
    doc_id = "test_causal_node_final"
    content = "测试因果节点：输入 A -> 结果 B"
    relations = "CAUSE: User testing -> EFFECT: System success"
    
    print(f"📥 Injecting a clean causal node: {doc_id}...")
    # 模拟 3072 维向量 (全零即可，仅用于验证字段存储)
    mock_vector = [0.0] * 3072
    
    await redis_mgr.store_vector(
        doc_id=doc_id,
        vector=mock_vector,
        content=content,
        entities=["Test"],
        depth=0,
        relations=relations
    )
    
    print("🔍 Fetching specifically the injected node...")
    # 精准拉取，不走模糊搜索，看物理字段
    res = redis_mgr.client.hgetall(f"doc:{doc_id}")
    
    print("\n--- Redis HASH Object Check ---")
    data = {k.decode('utf-8'): v.decode('utf-8') if k.decode('utf-8') != 'vector' else '<binary>' for k, v in res.items()}
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("--------------------------------\n")
    
    if "relations" in data and data["relations"] == relations:
        print("🎉 PHASE 1, STEP 1 VERIFIED: Causal relations are physically stored and retrievable!")
    else:
        print("❌ VERIFICATION FAILED: Relations field missing or data mismatch.")

if __name__ == "__main__":
    asyncio.run(final_verification())
