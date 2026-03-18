# Implementation Plan: multi-agent multi-step task completion and state stability

The goal is to fix the issue where multi-step tasks (e.g., the 5-step finance->doc->image->tweet->calendar task) stop prematurely or repeat steps, and to ensure that generated assets (like images) are correctly passed to subsequent steps even if intermediate files (like docs) are created.

## Objective
- Ensure 100% completion of complex task chains.
- Prevent state key collisions (e.g., Doc path overwriting Image path).
- Improve "Graceful Shutdown" and "Ctrl+C" behavior (already partially addressed, but will double-check).
- Fix "Initial Report" hallucination by standardizing Redis keys.

## Key Changes

### 1. Redis State Management (src/redis_manager.py)
- No changes needed to the manager itself, but we will use more specific keys in the agents.

### 2. Multi-Agent Feedback Loop (src/telegram_bridge.py)
- **State Differentiation**: Instead of just storing `file_path`, we will store `last_image_path`, `last_doc_path`, and `last_report_path`.
- **Loop Prompt Refactoring**: 
    - Maintain a `completed_tasks` list within the loop.
    - Explicitly list "REMAINING SUB-GOALS" in the prompt.
    - Tell the Orchestrator: "DO NOT provide a final text response until ALL goals are marked as [DONE]".
- **Tool Logic Refinement**:
    - Update `xpub` physical patching to look for `last_image_path` specifically.
    - Ensure `gemini_cli_executor` feedback includes the generated Doc URL if available.

### 3. Agent Enhancements
- **NewspaperAgent (src/agents/imgtools/newspaper_agent.py)**:
    - Ensure it sets `last_image_path` in its result data.
- **FinanceMonitorAgent (src/agents/investment/finance_monitor.py)**:
    - Ensure it sets `last_report_path` and `last_finance_digest`.
    - (Already fixed the key mismatch issue in previous attempt, will verify).

### 4. Workflow Stabilization
- **X Workflow (src/agents/socialpub/x_workflow.json)**:
    - Re-verify the `upload` selector.
    - Add a step to "click the text area" before typing to ensure focus.

## Implementation Steps

### Phase 1: Bridge Loop Reinforcement
1.  Modify `handle_message` in `telegram_bridge.py` to track `accomplished_goals`.
2.  Update the loop prompt to be extremely persistent.
3.  Implement specific state keys (`last_image_path`, etc.) to prevent collisions.

### Phase 2: Agent Data Flow Alignment
1.  Update `NewspaperAgent`, `FinanceMonitorAgent`, and `GeminiCLIAgent` to use specific result keys.
2.  Update `xpub` patching logic to use `last_image_path`.

### Phase 3: Verification
1.  Run the 5-step task.
2.  Verify:
    - [ ] Finance report sent.
    - [ ] Google Doc created (link provided).
    - [ ] Newspaper image sent.
    - [ ] Image uploaded to X (visible in GUI).
    - [ ] Calendar event created.
    - [ ] Bot summarizes everything in a final message.

## Rollback Plan
- Revert `telegram_bridge.py` to the previous version if the loop becomes unstable.
