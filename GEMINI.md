# GEMINI.md - 工程协作协议

## 项目背景
**项目名称**: GenieBot (Bridge-03)
**核心目标**: 实现一个具备“混合记忆”和“自进化能力”的 Telegram 多智能体系统。

## 工程规则 (Engineering Rules)

### 1. 任务拆分与执行 (Task Protocol)
*   **原子化改动**: 每次改动应聚焦于一个子任务。
*   **验证优先**: 任何代码改动后，必须运行相应的 `check` 或 `test` 指令。
*   **文档同步**: 修改核心逻辑后，必须同步更新 `genieprd.md` 中的进度表。

### 2. 长上下文压缩协议 (Context Compression)
为了防止上下文过长导致 AI 遗忘核心设计：
*   **阶段性快照 (State Snapshot)**: 在完成 `genieprd.md` 中的一个里程碑（Phase）后，AI 会生成一个“技术快照”，包含：
    *   `Current_Architecture`: 当前已实现的组件。
    *   `Key_Variables`: 核心变量和接口定义。
    *   `Pending_Tasks`: 剩余高优先级任务。
*   **归档指令**: 用户可以发送 `/archive`，AI 将总结之前的所有对话细节并输出为一个短字符串/简报，用户随后可以启动新会话并粘贴此简报。

### 3. 代码风格
*   **Python**: 强制类型提示 (Type Hints)。
*   **异步**: 核心逻辑必须异步化 (`async/await`)。
*   **错误处理**: 严禁静默失败，必须有日志记录。

## 项目结构 (Project Structure)
- `src/`: 核心代码。
    - `agents/`: 智能体目录。
        - `base.py`: Agent 基类定义。
        - `common/`: 常用通用工具（链接抓取、视频下载、文件发送等）。
    - `redis_manager.py`: 混合记忆管理。
    - `gemini_orchestrator.py`: Gemini 调度中心。
    - `telegram_bridge.py`: Telegram 接入点。
- `references/`: 参考资料目录（GitHub 源码、第三方 API 范例、代码片段）。
- `tests/`: 测试脚本。
- `.env`: 环境变量。

## 当前状态 (Current State)
- **已完成**: 
    - Phase 1 & 2 核心架构：Telegram 接入、混合记忆 (L1/L2/L3) 及 RAG 闭环。
    - Phase 3 核心功能：多 Agent 协同循环、超级隐身浏览器、Skill 插件化架构。
    - Phase 3.5 多模态集成：图片感知 (`image_ocr`, `prompt_inverse`)，模板引擎 (`genimgtemplate`)，与生图后端 (`nanobanana`, `vertex_generator`)。
- **待执行**: Phase 4 - 自我进化闭环 (Code Gen & Deploy)。

## [SESSION_COMPRESSION_SNAPSHOT: PHASE_4_EVOLUTION_STABLE_V2]
**1. 核心架构稳定性 (Done):**
- **Goal-Persistent Loop**: 重构了 `telegram_bridge.py` 的推理循环。引入了 `completed_subtasks` 追踪机制与增强版 Prompt，强制 Orchestrator 必须验证所有子任务完成后才输出最终回复，解决了长链任务中断的难题。
- **Graceful Shutdown v2**: 实现了基于 `asyncio.Event` 与 `os._exit(0)` 的强力停机机制。解决了 `Ctrl+C` 信号冲突导致的进程残留，确保资源秒级回收。
- **Anti-Explosion Heartbeat**: 在 `SchedulerManager` 中开启了任务合并 (`coalesce`) 与错失补偿限制。同时升级了 `HeartbeatAgent` 的决策逻辑，严禁触发 `running` 状态的任务，杜绝了离线后开机任务狂发的现象。
- **Topic-Aware Data Alignment**: 统一了财经监控在话题模式下的 Redis Key 命名规范（`last_finance_digest:{chat_id}:{topic_id}`），修复了报告始终显示为“初次报告”的 Bug。

**2. 多代理协同增强 (Done):**
- **Cross-Agent State Handoff**: 细化了状态键（`last_image_path`, `last_report_path`），确保在生成文档的同时，图片路径不会被覆盖，从而支撑“抓取 -> 文档 -> 生图 -> 发推”的高级联动。
- **X-Upload Reliability**: 升级了 X 发布工作流，增加了“点击聚焦”与“渲染等待”步骤，配合 CDP 物理注入，大幅提升了带图发推的成功率。

**3. 关键路径 (Key Paths):**
- 逻辑: `src/telegram_bridge.py` (主循环), `src/agents/analyzer/heartbeat_agent.py` (决策层)。
- 存储: `src/agents/task_status.json` (任务追踪), Redis (L1-L3 记忆)。

**4. 下一阶段目标 (Next):**
- 完成 `CodeGenAgent` 的物理沙盒热部署闭环。
- 探索多 Bot 矩阵下的跨实体协同。

---
*此文档由 AI 自动维护，作为系统运行的最高指令依据。*
