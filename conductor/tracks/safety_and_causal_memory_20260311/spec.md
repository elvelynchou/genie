# Track Specification: Causal Intent Audit & Causal Graph-RAG

## Overview
This track addresses two critical evolutionary paths for Phase 4:
1.  **Safety & Stability:** Implementing `L0-Safety-Gate` (Causal Intent Audit) to ensure dynamically generated code or complex agent actions do not compromise the core system.
2.  **Cognitive Depth:** Upgrading the existing Hierarchical Graph-RAG to support "Causal Edges", allowing the system to understand *why* past failures occurred and correct its logic during the Dreaming Phase.

## Functional Requirements

### 1. Causal Intent Audit (L0-Safety-Gate)
-   **Pre-execution Sandbox Preflight:** Before any dynamic code (e.g., from a future CodeGenAgent) or high-risk command is executed, it must pass an automated audit.
-   **Intent vs. Side-Effect Mapping:** The audit must articulate: "Goal -> Expected Output -> Potential System Side-Effects".
-   **Fallback & Rollback:** The system must define a recovery mechanism if an executed action drastically increases error rates in the `Heartbeat` logs.

### 2. Causal Graph-RAG Memory
-   **Schema Upgrade:** Enhance `redis_manager.py` indexing to store relational/causal edges alongside the existing Strategy/Logic/Data vectors.
-   **Refiner Evolution:** Update `MemoryRefinerAgent` to explicitly extract `"relations": [{"cause": "X", "effect": "Y"}]` during session summarization.
-   **Orchestrator Awareness:** Allow the `GeminiOrchestrator` to retrieve and understand these causal links when planning new tasks.

## Acceptance Criteria
- [ ] Redis schema supports and stores relational metadata.
- [ ] `MemoryRefinerAgent` successfully extracts and saves causal links from conversation failures.
- [ ] Architecture design for `L0-Safety-Gate` is documented and stubbed in the execution pipeline.