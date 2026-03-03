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

## [SESSION_COMPRESSION_SNAPSHOT: PHASE_3_5_MULTIMODAL_COMPLETE]
**1. 已实现逻辑 (Done):**
- **Unified Image Bus**: `telegram_bridge.py` 自动拦截 Telegram 图片并持久化至 `uploads/`。
- **Perception Agents**: `ImageOCRAgent` (文本提取) 与 `PromptInverseAgent` (逆向解析生图 Prompt + 强结构化 JSON 存档)。
- **Template Engine**: `TemplateCreatorAgent` 实现带 "Identity Lock" 的结构化参数合并，支持复用。
- **Generation Backends**: 
  - `VertexGenAgent`: 基于 Google GenAI (Imagen 3) 异步 API 的原生接入，具备指数退避抗 429 机制。
  - `Nanobanana MCP`: 深度封装进 `gemini_cli_executor`，通过物理级意图隔离防止路由跑偏，支持多图清洗。
- **UX & Control**: `/generate` 与 `/edit` 强引导快捷命令；产出图片自动集中在 `img_output/` 不删档。

**2. 关键路径 (Key Paths):**
- 视觉资产: `uploads/` (原图), `src/agents/imgtools/characters/` (人物), `img_output/` (产出)。
- 模板仓库: `src/agents/imgtools/genimgtemplate/`。

**3. 下一阶段目标 (Next):**
- 实现 Agent 自我进化沙盒：`code_gen` -> `sandbox` -> `deploy`。
- ModelScope API 等扩展模型接入评估。

---
*此文档由 AI 自动维护，作为系统运行的最高指令依据。*
