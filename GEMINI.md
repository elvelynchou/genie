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

## [SESSION_COMPRESSION_SNAPSHOT: PHASE_4_EVOLUTION_FINAL_STABILITY]
**1. 核心架构进化 (Done):**
- **Causal Graph-RAG**: 升级了记忆索引，支持 `relations` 字段。`MemoryRefiner` 现在能提取因果链条（原因 -> 结果 -> 教训），实现了逻辑级的经验闭环。
- **L0-Safety-Gate**: 建立了基于因果审计的安全门机制。`SafetyAgent` 会在每一轮高危操作执行前进行意图审计与风险评分，防止系统在自进化过程中崩溃。
- **Advanced Skill Routing**: 在 Bridge 层实现了针对特定任务（生图、发推、X抓取）的强力路由与工具箱收缩，杜绝了 AI 调用的逻辑漂移。
- **CDP Native Upload**: `stealth_browser` 进化为支持 Chrome 原生 CDP 协议的物理级文件上传，彻底解决了社交平台隐藏输入框无法操作的难题。

**2. 交互与体验 (Done):**
- **Newspaper v3.0**: 实现了横版高密度财经报纸自动生成引擎。支持物理文件直连、四维度精准排版与插图极小化。
- **Graceful Shutdown**: 完善了 Linux 信号拦截与任务强制取消机制，解决了 Ctrl+C 无法中断主进程的顽疾。
- **Topic Sharding**: 记忆分片完全成熟，支持不同话题下的独立上下文隔离。

**3. 关键路径 (Key Paths):**
- 文档: `HEARTBEAT.md` (脉搏协议), `SAFETY_GATE.md` (审计架构), `Setup.md` (构建指南)。
- 配置: `src/agents/task_status.json` (任务备忘录), `src/agents/socialpub/x_workflow.json` (发推工作流)。
- Agent: `src/agents/analyzer/safety_agent.py`, `src/agents/imgtools/newspaper_agent.py`。

**4. 下一阶段目标 (Next):**
- 完成 `CodeGenAgent` 与 `SandboxManager` 的热部署闭环。
- 探索基于系统资源监控的自愈式故障恢复（Autonomic Recovery）。

---
*此文档由 AI 自动维护，作为系统运行的最高指令依据。*
