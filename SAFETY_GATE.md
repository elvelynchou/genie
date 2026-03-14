# L0-Safety-Gate: Causal Intent Audit Architecture

## 1. 愿景
在 Phase 4 的自我进化中，系统具备动态生成代码和执行高危操作的能力。L0-Safety-Gate 作为一个拦截层，通过“因果预判”来防止系统性风险。

## 2. 核心 Schema (Intent -> Expected -> Side Effects)
每个高危动作在执行前，Orchestrator 必须构造一个“意图包”交给 SafetyGate 审计：

| 字段 | 描述 | 示例 |
| :--- | :--- | :--- |
| **Intent** | 核心意图 | "更新 X 发布 Agent 的选择器逻辑" |
| **Proposed Action** | 具体动作/代码 | `agent_code_v2.py` 或 `os.system(...)` |
| **Expected Outcome** | 预期结果 | "发布成功率提升，不再超时" |
| **Potential Side Effects** | 潜在副作用 | "可能导致内存占用升高，或由于选择器错误导致全量失败" |

## 3. 审计流程 (Audit Pipeline)

1.  **感知与唤起**：Orchestrator 识别到即将执行的操作属于 `HIGH_RISK` 类别（代码部署、物理删除、社交全量发布）。
2.  **因果追溯**：SafetyGate 查询 **Causal Graph-RAG**，寻找历史中类似意图导致的失败案例。
3.  **风险评分**：
    -   **Green**: 历史无负面记录，且代码静态扫描通过。直接执行。
    -   **Yellow**: 存在类似失败案例，但意图合理。需要 **User Manual Approval**（Telegram 确认）。
    -   **Red**: 违反物理禁令（如访问 .env）或历史有致命崩溃记录。强制拦截并回退。
4.  **监控与本能回滚**：
    -   执行后进入 5 分钟“观察期”。
    -   `Heartbeat` 持续监控报错率。
    -   若报错率激增，触发 L0 级的 **Instinctive Rollback**（物理覆盖回旧版本）。

## 4. 落地步骤
-   [ ] 在 `GeminiOrchestrator` 中定义 `HIGH_RISK_TOOLS` 集合。
-   [ ] 实现 `SafetyAgent` 专门用于执行上述 3 步审计逻辑。
-   [ ] 在 `telegram_bridge.py` 中增加对 `SafetyAgent` 的强制拦截点。
