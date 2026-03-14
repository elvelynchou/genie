# GenieBot 产品需求文档 (PRD) - v2.0 (Deep Dive)

## 1. 系统愿景
构建一个基于 Telegram 的“自进化”多智能体平台，利用 Gemini 的长上下文能力和 Redis Stack 的向量检索，实现复杂任务的自主拆解与执行。

## 2. 深度模块设计

### 2.1 消息接入层 (Telegram Bridge)
*   **异步模型**：基于 `aiogram 3.x`。
*   **中间件 (Middleware)**：
    *   **Identity Filter**: 校验 UserID，非白名单用户直接阻断。
    *   **Rate Limiter**: 防止 API 滥用。
*   **交互规范**：
    *   长任务需先回复 `⏳ 正在处理...` 并通过 `edit_message` 更新进度。
    *   支持 `Inline Keyboard` 进行二次确认（如：代码部署授权）。

### 2.2 核心大脑 (Gemini Orchestrator)
*   **上下文控制策略 (Window Management)**：
    *   当上下文接近限制时，执行 `Archive & Summarize` 任务。
    *   保留最新的 5 条原始消息，其余消息转为“背景事实”压缩存储。
*   **多步推理 (Chain-of-Execution)**：
    *   Gemini 返回 `call: search` -> 执行 -> 得到结果 -> 再次输入 Gemini -> 返回 `call: plot`。
    *   系统需维护一个 `Task_Chain_ID` 追踪整个任务流。

### 2.3 记忆架构 (Redis Stack)
*   **Key 设计**：
    *   `history:{chat_id}` (List): 原始消息。
    *   `state:{chat_id}` (Hash): 存储当前任务的槽位信息（例如：`asset="BTC", timeframe="1h"`）。
    *   `vector_index` (RediSearch): 存储 RAG 文档。
*   **RAG 触发逻辑**：仅在意图识别为“知识咨询”或“深度分析”时，调用 `VectorSearch` 补充 Prompt。

### 2.4 智能 Agent 沙盒 (Self-Evolution)
*   **隔离环境**：所有动态生成的 Agent 代码必须运行在独立的虚拟环境或容器中。
*   **安全性检查**：
    *   禁止 `os.system`, `subprocess` (除受限白名单外)。
    *   禁止访问 `.env` 和系统配置文件。
*   **动态加载**：使用 `importlib` 动态加载通过审核的 Agent 类。

## 3. 开发任务拆分 (Task Breakdown)

### Phase 1: 基础设施与闭环 (基础建设) - ✅ 已完成 (2026-02-26)
- [x] 搭建 `telegram_bridge`：实现身份校验与基础对话。
- [x] 搭建 `redis_manager`：实现 L1 历史记录存储。
- [x] 实现 `orchestrator`：集成 google-genai (v1) 并验证对话闭环。

### Phase 2: 记忆进阶与 RAG (智能增强) - ✅ 已完成 (2026-02-26)
- [x] 实现上下文自动压缩与摘要逻辑。
- [x] 配置 Redis Search 索引，实现 L3 长期记忆检索。
- [x] 调通 gemini-embedding-001 向量模型。

### Phase 3: 高级智能与专用 Agent - ✅ 已完成 (2026-03-03)
- [x] 实现基于 Function Calling 的多 Agent 协同循环逻辑 (Reasoning Loop)。
- [x] 开发 `video-downloader`：基于 Gemini CLI Skill 模式的视频下载。
- [x] 开发 `x-tweet-fetcher`：基于 Gemini CLI Skill 模式的推文抓取与 MD 存档。
- [x] 开发 `link_content_extractor`：基于 Playwright 的网页转 Markdown 工具。
- [x] 开发 `stealth_browser`：集成 Camoufox & nodriver 的双引擎隐身浏览器。
- [x] 实现分阶段任务反馈与心跳监控机制。

### Phase 3.5: 多模态视觉引擎集成 - ✅ 已完成 (2026-03-03)
- [x] **视觉感知层**: 开发 `image_ocr` (图文提取) 和 `prompt_inverse` (逆向解析生图 Prompt)。
- [x] **模板引擎**: 开发 `image_template_creator` 实现参考图身份锁定 (Identity Lock) 模板。
- [x] **生图后端**: 接入 `Nanobanana` (基于 MCP/CLI) 与 `Vertex AI` (Imagen 3 API)，实现文生图/图生图闭环。
- [x] 优化 Telegram 交互逻辑：实现图片自动落地存储 (`uploads/`) 和生图自动回传 (`img_output/`)，并增加 `/generate` 和 `/edit` 快捷指令。

### Phase 4: 自进化与自动化运维 - ✅ 已完成 (2026-03-13)
- [x] 环境准备：安装 RestrictedPython 沙箱环境。
- [x] 开发 `code_gen_agent`：根据自然语言生成 BaseAgent 子类。
- [x] 实现动态 Agent 热加载与部署审核流程 (SandboxAgent & DeploymentAgent)。
- [x] 接入监控告警与系统健康检测 (SysCheckAgent)。
