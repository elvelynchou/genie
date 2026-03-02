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
    - 基础 Agent 框架 (`BaseAgent`) 及 目录结构初始化。
    - 通用工具 Agent 实现：`video_downloader`, `file_sender`, `link_content_extractor`, `browser_agent`.
    - Phase 3 核心功能：`code_gen_agent`, `sandbox_executor`, `code_deploy_agent` (自我进化闭环).
- **待执行**: Phase 4 - 监控与优化 (生产化) 及 专用业务 Agent (Investment, WebSearch).

## [SESSION_COMPRESSION_SNAPSHOT: PHASE_3_COMPLETE]
**1. 已实现逻辑 (Done):**
- **Memory Layers**: L1 (History List), L2 (Auto-Summary), L3 (Vector RAG).
- **Core Agents**: `video_downloader`, `link_extractor`, `browser_agent`, `github_analyzer`.
- **Self-Evolution**: `code_gen_agent`, `sandbox_executor`, `code_deploy_agent` (完整闭环).
- **Inference**: 使用 `gemini-3-flash-preview` 调度，`gemini-embedding-001` 进行向量化。

**2. 关键路径 (Key Paths):**
- 向量索引: `genie_vdb` (DB 0, 768 dim, HNSW).
- 核心逻辑: `redis_manager.py` (多层记忆管理), `gemini_orchestrator.py` (Embedding 与 Chat), `telegram_bridge.py` (多 Agent 循环调度).

**3. 下一阶段目标 (Next):**
- 实现基于 Function Calling 的专用业务 Agent (Investment, WebSearch)。
- 接入监控告警与系统健康检测。
- 优化长任务异步反馈机制。

---
*此文档由 AI 自动维护，作为系统运行的最高指令依据。*
