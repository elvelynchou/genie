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

## [SESSION_COMPRESSION_SNAPSHOT: PHASE_4_EVOLUTION_MATURED]
**1. 核心架构进化 (Done):**
- **L0 Instincts Layer**: 引入了“本能指令集”。高频成功的动作序列（如财经监控、登录）被固化为 L0 缓存，跳过 LLM 推理实现毫秒级响应。
- **Topic-Aware Routing**: 全面支持 Telegram 话题模式。记忆按 `chat_id:topic_id` 分片隔离，确保跨领域任务（财经 vs 开发）上下文互不干扰。
- **Semantic Object Control**: `stealth_browser` 进化为基于 **Accessibility Tree (A11yTree)** 的语义控制。通过 JS 代理提取结构化对象而非原始 HTML，Token 消耗降低 50%，稳定性大幅提升。
- **Hierarchical Graph-RAG**: 升级为 Strategy(0), Logic(1), Data(2) 三层索引。`MemoryRefiner` 自动归档宏观意图，实现策略优先的关联检索。
- **Nightly Dreaming Phase**: 实现了异步记忆巩固机制。系统在凌晨自动复盘事实碎片并升华为长期策略节点。

**2. 交互与通讯 (Done):**
- **Robust Delivery**: 实现了带分片、自动转义和纯文本回退的消息安全发送机制，彻底解决了长篇财经简报导致的通讯卡死。
- **Fault Isolation**: 浏览器执行层引入了动作级超时 (60s) 与全自动异常隔离，确保单个源的故障不影响全局流水线。

**3. 关键路径 (Key Paths):**
- 文档: `Setup.md` (系统构建指南), `GEMINI.md` (工程协议)。
- 配置: `src/agents/investment/sources.json` (财经源), `src/agents/imgtools/genimgtemplate/` (图片模板)。
- 本能: `RediSearch: instinct:*` (L0 指令集)。

**4. 下一阶段目标 (Next):**
- 完善基于 `skill-creator` 的代码生成与沙盒部署闭环。
- 探索多 Bot 矩阵下的跨实体协同。

---
*此文档由 AI 自动维护，作为系统运行的最高指令依据。*
