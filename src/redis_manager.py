import redis
import json
import logging
import numpy as np
from datetime import datetime
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

    # --- L0: Instincts (Fast-path triggers) ---
    async def set_instinct(self, trigger: str, agent_name: str, args: Dict[str, Any]):
        """Store a high-frequency successful action pattern."""
        key = f"instinct:{trigger.lower().strip()}"
        data = {
            "agent_name": agent_name,
            "args": json.dumps(args),
            "created_at": datetime.now().isoformat()
        }
        self.client.hset(key, mapping=data)
        self.client.expire(key, 604800) # 1 week TTL for instincts

    async def get_instinct(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Check if user input matches a known 'Instinct' (L0 bypass)."""
        # Simple exact match or specialized finance/xpub patterns
        triggers = [user_input.lower().strip()]
        if "/run_finance" in triggers[0]: triggers.append("run_finance")
        if "/x_post" in triggers[0]: triggers.append("x_post")
        
        for t in triggers:
            key = f"instinct:{t}"
            if self.client.exists(key):
                res = self.client.hgetall(key)
                return {
                    "name": res[b"agent_name"].decode('utf-8'),
                    "args": json.loads(res[b"args"].decode('utf-8'))
                }
        return None

    # --- L3: Vector / RAG (Now on DB 0) ---
    def init_vector_index(self, dim: int = 768):
        """Initialize Vector Index with Entity Tagging and Hierarchical Depth support."""
        try:
            self.client.execute_command(
                "FT.CREATE", self.index_name, "ON", "HASH", "PREFIX", "1", "doc:",
                "SCHEMA", 
                "content", "TEXT", 
                "entities", "TAG", "SEPARATOR", ",",
                "depth", "NUMERIC", "SORTABLE",
                "vector", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE"
            )
            self.logger.info(f"Vector index {self.index_name} (with Tags & Depth) created on DB 0.")
            self.rag_enabled = True
        except redis.exceptions.ResponseError as e:
            if "Index already exists" in str(e):
                self.logger.info("Vector index already exists.")
                self.rag_enabled = True
            else:
                self.logger.error(f"Failed to create index: {e}")
                self.rag_enabled = False

    async def store_vector(self, doc_id: str, vector: List[float], content: str, entities: List[str] = None, depth: int = 2):
        """
        Store vector with entities and hierarchical depth.
        depth: 0=Strategy, 1=Logic, 2=Data (default)
        """
        if not self.rag_enabled: return
        key = f"doc:{doc_id}"
        vector_bin = np.array(vector, dtype=np.float32).tobytes()
        mapping = {
            "vector": vector_bin,
            "content": content,
            "depth": depth
        }
        if entities:
            mapping["entities"] = ",".join(entities)
            
        self.client.hset(key, mapping=mapping)

    async def search_hierarchical(self, query_vector: List[float], entities: List[str] = None, k_strategy: int = 2, k_data: int = 3) -> List[str]:
        """
        Multi-layer search: Prioritizes high-level strategy nodes then combines with detailed data.
        """
        if not self.rag_enabled: return []
        vector_bin = np.array(query_vector, dtype=np.float32).tobytes()
        
        results = []
        try:
            # 1. Search Strategy Layer (depth=0)
            strategy_query = f"(@depth:[0 0])=>[KNN {k_strategy} @vector $vec AS score]"
            res_strat = self.client.execute_command(
                "FT.SEARCH", self.index_name, strategy_query, 
                "PARAMS", "2", "vec", vector_bin, 
                "SORTBY", "score", "ASC", "DIALECT", "2"
            )
            
            # 2. Search Logic/Data Layer (depth > 0) with Entity filtering if provided
            filter_part = ""
            if entities:
                safe_entities = [e.replace(" ", "\\ ") for e in entities]
                filter_part = f"@entities:{{{'|'.join(safe_entities)}}}"
            
            data_query = f"({filter_part} @depth:[1 2])=>[KNN {k_data} @vector $vec AS score]" if filter_part else f"(@depth:[1 2])=>[KNN {k_data} @vector $vec AS score]"
            
            res_data = self.client.execute_command(
                "FT.SEARCH", self.index_name, data_query, 
                "PARAMS", "2", "vec", vector_bin, 
                "SORTBY", "score", "ASC", "DIALECT", "2"
            )

            # Helper to parse FT.SEARCH responses
            def parse_res(res):
                out = []
                if res and res[0] > 0:
                    for i in range(2, len(res), 2):
                        fields = res[i]
                        for j in range(0, len(fields), 2):
                            if fields[j].decode('utf-8') == "content":
                                out.append(fields[j+1].decode('utf-8'))
                return out

            results = parse_res(res_strat) + parse_res(res_data)
            return list(dict.fromkeys(results)) # Deduplicate while preserving order
        except Exception as e:
            self.logger.error(f"Hierarchical search failed: {e}")
            return []

    async def search_by_entities(self, entities: List[str], k: int = 5) -> List[str]:
        """Exact match search based on entity tags (The 'Hop' in Graph-RAG)."""
        if not self.rag_enabled or not entities: return []
        
        # Dialect 2 requires specific escaping or simple tag groups
        # Correct syntax for multiple tags: @entities:{tag1|tag2}
        safe_entities = [e.replace(" ", "\\ ") for e in entities]
        tag_query = "|".join(safe_entities)
        query = f"@entities:{{{tag_query}}}"
        
        try:
            # Use DIALECT 2 for consistent behavior across vector and tag search
            res = self.client.execute_command("FT.SEARCH", self.index_name, query, "LIMIT", "0", str(k), "DIALECT", "2")
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

    async def get_all_by_depth(self, depth: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch all documents at a specific depth layer."""
        if not self.rag_enabled: return []
        query = f"@depth:[{depth} {depth}]"
        try:
            res = self.client.execute_command("FT.SEARCH", self.index_name, query, "LIMIT", "0", str(limit), "DIALECT", "2")
            results = []
            if res and res[0] > 0:
                for i in range(2, len(res), 2):
                    doc_id = res[i-1] # Actually the index before the fields
                    fields = res[i]
                    data = {"id": doc_id.decode('utf-8') if isinstance(doc_id, bytes) else str(doc_id)}
                    for j in range(0, len(fields), 2):
                        key = fields[j].decode('utf-8')
                        val = fields[j+1]
                        if key != "vector": # Skip large binary vector
                            data[key] = val.decode('utf-8') if isinstance(val, bytes) else val
                    results.append(data)
            return results
        except Exception as e:
            self.logger.error(f"Fetch by depth failed: {e}")
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
