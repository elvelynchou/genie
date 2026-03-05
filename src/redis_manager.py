import redis
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional

class RedisManager:
    def __init__(self, host='localhost', port=6379, db=0, password=None):
        self.logger = logging.getLogger(__name__)
        
        # Unified Database (DB 0) for all layers
        self.pool = redis.ConnectionPool(
            host=host, port=port, db=db, password=password, 
            decode_responses=False # Keep binary for Vector/Numpy compatibility
        )
        self.client = redis.Redis(connection_pool=self.pool)
        
        self.index_name = "genie_vdb"
        self.rag_enabled = False

    # --- L1/L2 Methods (Now all on DB 0) ---
    async def push_history(self, chat_id: str, role: str, content: str, ttl: int = 86400):
        key = f"history:{chat_id}"
        message = json.dumps({"role": role, "content": content})
        self.client.rpush(key, message)
        self.client.expire(key, ttl)

    async def get_history(self, chat_id: str, limit: int = 20) -> List[Dict[str, str]]:
        key = f"history:{chat_id}"
        messages = self.client.lrange(key, -limit, -1)
        return [json.loads(m.decode('utf-8')) for m in messages]

    async def trim_history(self, chat_id: str, keep_last: int = 5):
        key = f"history:{chat_id}"
        self.client.ltrim(key, -keep_last, -1)

    async def clear_history(self, chat_id: str):
        """Clear L1 history for a specific chat."""
        key = f"history:{chat_id}"
        self.client.delete(key)

    async def set_summary(self, chat_id: str, summary_text: str):
        key = f"summary:{chat_id}"
        self.client.set(key, summary_text)

    async def get_summary(self, chat_id: str) -> Optional[str]:
        val = self.client.get(f"summary:{chat_id}")
        return val.decode('utf-8') if val else None

    async def set_state(self, chat_id: str, state_data: Dict[str, Any]):
        """Store shared agent state/data bus."""
        key = f"state:{chat_id}"
        # Convert all values to strings for Redis Hash compatibility
        flat_state = {k: str(v) for k, v in state_data.items()}
        if flat_state:
            self.client.hset(key, mapping=flat_state)
            self.client.expire(key, 3600) # State expires in 1 hour

    async def get_state(self, chat_id: str) -> Dict[str, str]:
        """Retrieve shared state."""
        key = f"state:{chat_id}"
        res = self.client.hgetall(key)
        return {k.decode('utf-8'): v.decode('utf-8') for k, v in res.items()}

    # --- L3: Vector / RAG (Now on DB 0) ---
    def init_vector_index(self, dim: int = 768):
        """Initialize Vector Index with Entity Tagging support."""
        try:
            self.client.execute_command(
                "FT.CREATE", self.index_name, "ON", "HASH", "PREFIX", "1", "doc:",
                "SCHEMA", 
                "content", "TEXT", 
                "entities", "TAG", "SEPARATOR", ",",
                "vector", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE"
            )
            self.logger.info(f"Vector index {self.index_name} (with Tags) created on DB 0.")
            self.rag_enabled = True
        except redis.exceptions.ResponseError as e:
            if "Index already exists" in str(e):
                # Optionally check if entities field exists, if not, recreate or alter
                self.logger.info("Vector index already exists.")
                self.rag_enabled = True
            else:
                self.logger.error(f"Failed to create index: {e}")
                self.rag_enabled = False

    async def store_vector(self, doc_id: str, vector: List[float], content: str, entities: List[str] = None):
        if not self.rag_enabled: return
        key = f"doc:{doc_id}"
        vector_bin = np.array(vector, dtype=np.float32).tobytes()
        mapping = {
            "vector": vector_bin,
            "content": content
        }
        if entities:
            mapping["entities"] = ",".join(entities)
            
        self.client.hset(key, mapping=mapping)

    async def search_by_entities(self, entities: List[str], k: int = 5) -> List[str]:
        """Exact match search based on entity tags (The 'Hop' in Graph-RAG)."""
        if not self.rag_enabled or not entities: return []
        tag_query = " | ".join([f"{{{e}}}" for e in entities])
        query = f"@entities:({tag_query})"
        try:
            res = self.client.execute_command("FT.SEARCH", self.index_name, query, "LIMIT", "0", str(k))
            results = []
            if res and res[0] > 0:
                for i in range(2, len(res), 2):
                    fields = res[i]
                    for j in range(0, len(fields), 2):
                        if fields[j].decode('utf-8') == "content":
                            results.append(fields[j+1].decode('utf-8'))
            return results
        except Exception as e:
            self.logger.error(f"Entity search failed: {e}")
            return []

    async def search_vector(self, query_vector: List[float], k: int = 3) -> List[str]:
        if not self.rag_enabled: return []
        vector_bin = np.array(query_vector, dtype=np.float32).tobytes()
        query = f"*=>[KNN {k} @vector $vec AS score]"
        try:
            res = self.client.execute_command(
                "FT.SEARCH", self.index_name, query, 
                "PARAMS", "2", "vec", vector_bin, 
                "SORTBY", "score", "ASC", "DIALECT", "2"
            )
            results = []
            if res and res[0] > 0:
                for i in range(2, len(res), 2):
                    fields = res[i]
                    for j in range(0, len(fields), 2):
                        if fields[j].decode('utf-8') == "content":
                            results.append(fields[j+1].decode('utf-8'))
            return results
        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            return []
