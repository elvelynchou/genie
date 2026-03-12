# Implementation Plan: Causal Intent Audit & Causal Graph-RAG Memory

## Phase 1: Causal Graph-RAG Foundation
- [ ] **Task: Update Redis schema in `redis_manager.py` to support `relations` TEXT field**
- [ ] **Task: Modify `MemoryRefinerAgent` prompt and parsing logic to extract causal edges**
- [ ] **Task: Verify storage and retrieval of causal metadata in vector search**

## Phase 2: Orchestrator Integration
- [ ] **Task: Inject causal metadata into the `GeminiOrchestrator` reasoning prompt**
- [ ] **Task: Update `DreamerAgent` to utilize causal relations for deeper strategy synthesis**

## Phase 3: L0-Safety-Gate Architecture
- [ ] **Task: Design and document the Audit Schema (Intent -> Expected -> Side Effects)**
- [ ] **Task: Implement a pre-flight verification hook in the Orchestrator for high-risk actions**
- [ ] **Task: Define rollback triggers based on Heartbeat log anomalies**