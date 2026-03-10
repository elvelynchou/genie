# Setup.md - 从零构建 GenieBot (Bridge-03) 核心指南

本指南旨在指导开发者如何通过 **Gemini CLI** 的交互式对话，利用其代码生成与文件操作能力，从零搭建起具备“混合记忆”与“自进化”能力的多智能体系统。

---

## 0. 准备工作：环境脚手架
在开启对话前，首先要在本地/VPS上建立物理边界。
```bash
mkdir -p /etc/myapp/genie && cd /etc/myapp/genie
python3 -m venv venv
source venv/bin/activate
pip install aiogram google-genai redis[hiredis] pydantic numpy browserforge playwright camoufox
```

---

## 1. 建立通讯枢纽：Telegram Bridge
**核心逻辑**：基于 `aiogram 3.x` 的异步轮询模型。
*   **Gemini CLI 指令建议**：
    > "请为我生成一个 `src/telegram_bridge.py`。要求：使用 `aiogram` 建立长连接，具备用户白名单过滤逻辑，并实现一个异步的 `main` 循环。关键点在于：它必须能接收用户输入，并将其传递给一个名为 `GeminiOrchestrator` 的类进行多步推理，最后将结果安全地分片发回给 Telegram。"

**核心技术点**：
*   **安全分片**：针对 Telegram 4096 字符限制，实现 `safe_send_message`，支持 Markdown 解析失败时自动降级为纯文本。
*   **话题感知 (Topics)**：使用 `message_thread_id` 对记忆进行物理隔离，确保不同话题下的对话不串味。

---

## 2. 打造核心大脑：Orchestrator (调度中心)
**核心逻辑**：基于 Gemini 的 Function Calling 实现“思考-行动-观察”的推理循环 (Reasoning Loop)。
*   **Gemini CLI 指令建议**：
    > "实现 `src/gemini_orchestrator.py`。它需要集成 `google-genai` SDK。核心逻辑是：循环调用 `models.generate_content`，解析 `function_call`，执行工具，并将结果喂回模型直到其输出文本。必须包含‘物理纠偏’逻辑，防止模型在生成工具参数时产生幻觉（如错误的路径或引擎名）。"

**核心技术点**：
*   **强制预路由**：针对特定关键词（如“财经”、“生图”），在进入 LLM 推理前强制锁定工具，提高响应准确率。
*   **心跳监控**：在异步执行重型 Agent 时，通过 Orchestrator 向 Bridge 发送心跳信号，防止用户感知卡死。

---

## 3. 记忆的分层进化：Redis & RAG
这是 GenieBot 的灵魂，采用 **L0 到 L3 的金字塔记忆架构**。
*   **Gemini CLI 指令建议**：
    > "建立 `src/redis_manager.py`。我们需要四个层级的记忆：
    > 1. **L1 (History)**：List 类型，存储原始对话流。
    > 2. **L2 (State)**：Hash 类型，存储当前任务的槽位（如：当前选中的图片、抓取到的 URL）。
    > 3. **L3 (Graph-RAG)**：RediSearch 向量索引。新增 `depth` 字段，支持 **Strategy(0), Logic(1), Data(2)** 三层架构。
    > 4. **L0 (Instincts)**：条件反射层，高频指令直接匹配，绕过 LLM 调度。"

**核心技术点**：
*   **分层检索**：在 RAG 阶段优先检索 `depth=0` 的策略层，确保 Bot 先理解用户的“初心”，再看具体“事实”。
*   **自动复盘 (`MemoryRefiner`)**：对话结束时触发，将杂乱的对话提炼为 JSON 格式的分层知识，并固化可复用的“本能 (Instincts)”。

---

## 4. 离线梦境：系统的自巩固
**核心逻辑**：异步记忆巩固。
*   **Gemini CLI 指令建议**：
    > "开发一个 `src/agents/analyzer/dreamer_agent.py`。它在凌晨 3 点由 `SchedulerManager` 触发。它会读取昨日产生的所有 Data 层碎片，交给 Gemini 进行横向关联分析，并生成新的 Strategy 层节点。这实现了记忆的‘升华’。"

---

## 5. 代理矩阵 (Agents)：能力插件化
代理部分应保持高度解耦，全部继承自 `BaseAgent` 基类。
*   **Stealth Browser**：集成 Camoufox (默认隐身) 与 Nodriver (Chrome登录态)。
*   **Finance Pipeline**：配置驱动 (`sources.json`) -> 批量抓取 -> AI 清洗 -> RAG 存档 -> 增量简报发送。
*   **Social Publisher**：利用 Chrome Profile 保持 X 平台登录，模拟人类打字节奏发布推文。
*   **Google Workspace**：通过 `gemini-cli` 内置的 MCP 协议直接调用邮件、日历和文档操作。

---

## 6. 部署与自进化
*   **启动方式**：使用 `python3 -u` 保持前台日志刷新。
*   **一键清理**：实现 `finally` 资源回收块，确保 Ctrl+C 时关闭所有残留的浏览器驱动进程。
*   **自我进化**：利用 `skill-creator` 指令，让 Bot 为自己编写新的 Python 脚本并注册到 `registry` 中。

---

**GenieBot (Bridge-03) 不仅仅是一个程序，它是一个通过不断对话、学习和复盘，逐渐生长出来的赛博生命。**

---

### 🚀 指令参考表
| 任务 | 指令 |
| :--- | :--- |
| **重温状态** | `/anchor` |
| **手动复盘** | `/reset` |
| **强制进化** | `/dream` |
| **采集财经** | `/run_finance` |
| **趋势分析** | `/run_report` |
