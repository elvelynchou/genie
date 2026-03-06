import asyncio
import os
import logging
import sys
import json
import shlex
import hashlib
import re
from datetime import datetime

# Ensure local imports work correctly
sys.path.append(os.path.dirname(__file__))

from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from dotenv import load_dotenv

from redis_manager import RedisManager
from gemini_orchestrator import GeminiOrchestrator
from agents.registry import registry
from agents.common.link_extractor import LinkContentAgent
from agents.common.file_sender import FileSenderAgent
from agents.analyzer.trend_analyzer import TrendAnalyzerAgent
from agents.analyzer.memory_refiner import MemoryRefinerAgent
from agents.investment.finance_monitor import FinanceMonitorAgent
from agents.investment.finance_cleaner import FinanceCleanerAgent
from agents.socialpub.xpub_agent import XPubAgent
from agents.analyzer.dreamer_agent import DreamerAgent
from agents.common.gemini_cli_agent import GeminiCLIAgent
from agents.common.browser_agent import BrowserAgent
from agents.imgtools.image_ocr import ImageOCRAgent
from agents.imgtools.prompt_inverse import PromptInverseAgent
from agents.imgtools.template_creator import TemplateCreatorAgent
from agents.imgtools.vertex_agent import VertexGenAgent
from agents.imgtools.modelscope_agent import ModelScopeGenAgent
from agents.analyzer.log_anchor import LogAnchorAgent
from scheduler_manager import SchedulerManager

# Load environment variables
load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ALLOWED_USERS = [u.strip() for u in os.getenv("ALLOWED_USERS", "").split(",") if u.strip()]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
redis_mgr = RedisManager(db=0)
redis_mgr.init_vector_index(dim=768) 

# Enhanced Orchestrator System Instruction
system_instruction = """
You are GenieBot, an autonomous Multi-Agent system. 
OPERATIONAL DIRECTIVES:
1. GOAL PERSISTENCE: If a user gives a multi-step instruction, fulfill EVERY sub-task.
2. METADATA REPORTING: Always report 'file_path' locations.
3. IMAGE WORKFLOW: Use 'prompt_inverse' then 'image_template_creator' for templating.
4. FINANCE PIPELINE: When monitoring finance, the system uses Browser -> Cleaner -> RAG -> Report. 
5. SOCIAL PUBLISHING: To post on X (Twitter), use 'xpub'.
6. BROWSER STRATEGY: When using 'stealth_browser' to read a page, you MUST include at least two actions: 1) {"action": "goto", "url": "..."} and 2) {"action": "extract_semantic"}. Without 'extract_semantic', you will receive no data back.
7. TOOL USAGE: Call 'gemini_cli_executor' with 'yolo=True' for X/video, Nanobanana, and Skill tasks.
8. KNOWLEDGE UTILIZATION: You have access to a Graph-RAG system. Prioritize information labeled [Relevant Past Experiences & Knowledge] to answer queries. ONLY use 'stealth_browser' to search the web if the information in memory is insufficient, or if the user explicitly asks for "latest web search".
"""
orchestrator = GeminiOrchestrator(api_key=GEMINI_KEY, system_instruction=system_instruction)

# Register Agents (Unique registration)
registry.register_agent(LinkContentAgent())
registry.register_agent(FileSenderAgent(bot_instance=bot))
registry.register_agent(TrendAnalyzerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(MemoryRefinerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(LogAnchorAgent(orchestrator=orchestrator))
registry.register_agent(FinanceMonitorAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(FinanceCleanerAgent(orchestrator=orchestrator))
registry.register_agent(XPubAgent(orchestrator=orchestrator))
registry.register_agent(DreamerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(GeminiCLIAgent())
registry.register_agent(BrowserAgent())
registry.register_agent(ImageOCRAgent(orchestrator=orchestrator))
registry.register_agent(PromptInverseAgent(orchestrator=orchestrator))
registry.register_agent(TemplateCreatorAgent())
registry.register_agent(VertexGenAgent())
registry.register_agent(ModelScopeGenAgent())

# Initialize Scheduler
scheduler_mgr = SchedulerManager(bot, redis_mgr, orchestrator, ADMIN_CHAT_ID)

async def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS: return True
    return str(user_id) in ALLOWED_USERS

def escape_markdown(text: str) -> str:
    if not text: return ""
    escape_chars = r'_*`['
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

async def safe_send_message(message_or_id, text: str):
    parse_mode = "Markdown"
    target_id = message_or_id.chat.id if hasattr(message_or_id, 'chat') else message_or_id
    CHUNK_SIZE = 4000
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    for chunk in chunks:
        try:
            await bot.send_message(target_id, chunk, parse_mode=parse_mode)
        except TelegramBadRequest:
            try:
                # 最后的兜底：如果 Markdown 解析失败，发送纯文本
                await bot.send_message(target_id, chunk, parse_mode=None)
            except Exception as e:
                logger.error(f"Failed to send message chunk: {e}")

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 4 Active.\nAdvanced Memory Consolidation: ONLINE")

@dp.message(Command("run_report"))
async def trigger_report(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发每日科技趋势报告流...")
    asyncio.create_task(scheduler_mgr.daily_github_report())

@dp.message(Command("run_finance"))
async def trigger_finance(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发半小时财经监控流...")
    asyncio.create_task(scheduler_mgr.half_hourly_finance_report())

@dp.message(Command("dream"))
async def cmd_dream(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    status = await message.answer("🌙 正在开启“离线梦境”模式，深度巩固记忆...")
    agent = registry.get_agent("dreamer")
    result = await agent.execute(str(message.chat.id))
    await status.delete()
    if result.status == "SUCCESS":
        await message.answer(f"✅ 梦境进化完毕！\n\n{result.message}")
    else:
        await message.answer(f"❌ 梦境中断: {result.errors}")

@dp.message(Command("anchor"))
async def cmd_anchor(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id); history = await redis_mgr.get_history(chat_id)
    focus = message.text.replace("/anchor", "").strip()
    status = await message.answer("⚓ 正在固化项目状态快照...")
    agent = registry.get_agent("log_anchor")
    result = await agent.execute(chat_id, conversation_history=history, focus_topic=focus if focus else None)
    await status.delete()
    if result.status == "SUCCESS":
        await message.answer(f"✅ 状态已固化：`{result.data['log_path']}`", parse_mode="Markdown")
        await safe_send_message(message, result.data["content"])
    else: await message.answer(f"❌ 固化失败: {result.errors}")

@dp.message(Command("reset"))
async def reset_session(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    history = await redis_mgr.get_history(chat_id)
    if history:
        asyncio.create_task(registry.get_agent("memory_refiner").execute(chat_id, history=history, session_status="RESET_BY_USER"))
    await redis_mgr.clear_history(chat_id); redis_mgr.client.delete(f"summary:{chat_id}")
    await message.answer("🔄 会话已复盘并重置。")

@dp.message(Command("x_login"))
async def cmd_x_login(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    args = message.text.replace("/x_login", "").strip()
    profile = args if args else "geclibot_profile"
    await message.answer(f"🌐 正在开启 Chrome (Nodriver) 窗口进行 Profile [{profile}] 登录...")
    agent = registry.get_agent("stealth_browser")
    asyncio.create_task(agent.execute(
        str(message.chat.id), 
        engine="nodriver", 
        headless=False, 
        profile=profile, 
        keep_open=True,
        actions=[{"action": "goto", "params": {"url": "https://x.com/login"}}]
    ))

@dp.message(Command("x_post"))
async def cmd_x_post(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    raw_text = message.text.replace("/x_post", "").strip()
    if not raw_text:
        await message.answer("Usage: `/x_post [打开窗口] 内容`", parse_mode="Markdown")
        return
    
    use_headless = False if any(kw in raw_text.lower() for kw in ["打开窗口", "gui", "window"]) else True
    use_engine = "nodriver"
    content = raw_text.replace("打开窗口", "").replace("gui", "").replace("window", "").strip()

    status = await message.answer(f"🐦 正在通过 Chrome (Nodriver) 发布推文 (Headless: {use_headless})...")
    agent = registry.get_agent("xpub")
    result = await agent.execute(str(message.chat.id), content=content, profile="geclibot_profile", headless=use_headless, engine=use_engine)
    await status.delete()
    if result.status == "SUCCESS":
        snapshot = result.data.get("debug_snapshot")
        if snapshot:
            await registry.get_agent("file_sender").execute(str(message.chat.id), file_path=snapshot, delete_after_send=False)
        await message.answer(f"✅ 推文发布指令执行完毕！\n\n内容预览：\n{content}")
    else:
        await message.answer(f"❌ 发布失败: {result.errors}")

def load_template_prompt(prompt_or_template: str) -> str:
    template_path = f"/etc/myapp/genie/src/agents/imgtools/genimgtemplate/{prompt_or_template}.json"
    if os.path.exists(template_path):
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                tpl = json.load(f); instr = tpl.get("core_instructions", ""); details = tpl.get("visual_details", {})
                return f"{instr}\nVisual Details: {json.dumps(details)}"
        except Exception as e: logger.error(f"Failed to load template {template_path}: {e}")
    return prompt_or_template

async def finalize_nanobanana_output(chat_id: str, result_data: dict, message: types.Message):
    all_paths = result_data.get("all_paths", [result_data.get("file_path")]); valid_paths = [p for p in all_paths if p and os.path.exists(p)]
    if valid_paths:
        for idx, file_path in enumerate(valid_paths):
            if "nanobanana-output" in file_path:
                img_output_dir = "/etc/myapp/genie/img_output"; os.makedirs(img_output_dir, exist_ok=True)
                new_filename = f"nanobanana_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}_{idx}.png"
                new_path = os.path.join(img_output_dir, new_filename); os.rename(file_path, new_path); file_path = new_path
            await registry.get_agent("file_sender").execute(chat_id, file_path=file_path, delete_after_send=False)
    else: await safe_send_message(message, f"❌ 生图成功但未找到路径:\n{result_data.get('output', '')}")

@dp.message(Command("generate"))
async def cmd_generate(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    prompt = message.text.replace("/generate", "").strip()
    if not prompt: await message.answer("Usage: `/generate \"prompt\"`", parse_mode="Markdown"); return
    chat_id = str(message.chat.id); status = await message.answer("🎨 正在启动 Nanobanana...")
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(chat_id, action="execute", prompt=f"MUST USE 'nanobanana__generate_image'. Set preview=false --count=1. PROMPT: {load_template_prompt(prompt)}", yolo=True)
    await status.delete()
    if result.status == "SUCCESS": await finalize_nanobanana_output(chat_id, result.data, message)
    else: await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    try: args = shlex.split(message.text.replace("/edit", "").strip())
    except: await message.answer("❌ 参数解析失败。"); return
    if len(args) < 2: await message.answer("Usage: `/edit filename \"prompt\"`", parse_mode="Markdown"); return
    chat_id = str(message.chat.id); status = await message.answer(f"🎨 正在重绘 {args[0]}...")
    ref_path = os.path.join("/etc/myapp/genie/src/agents/imgtools/characters", args[0]) if "/" not in args[0] else args[0]
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(chat_id, action="execute", prompt=f"MUST USE 'nanobanana__edit_image'. Set preview=false --count=1. Input file: {ref_path}. PROMPT: {load_template_prompt(args[1])}", yolo=True)
    await status.delete()
    if result.status == "SUCCESS": await finalize_nanobanana_output(chat_id, result.data, message)
    else: await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(Command("vertex"))
async def cmd_vertex(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    try: args = shlex.split(message.text.replace("/vertex", "").strip())
    except: await message.answer("❌ 参数解析失败。"); return
    if not args: return
    chat_id = str(message.chat.id); status = await message.answer("🎨 正在启动 Vertex AI...")
    agent = registry.get_agent("vertex_generator")
    result = await agent.execute(chat_id, prompt_or_template=args[0]) if len(args) == 1 else await agent.execute(chat_id, reference_image=args[0], prompt_or_template=args[1])
    await status.delete()
    if result.status == "SUCCESS": await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], delete_after_send=False)
    else: await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(Command("modelscope"))
async def cmd_modelscope(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    try: args = shlex.split(message.text.replace("/modelscope", "").strip())
    except: await message.answer("❌ 参数解析失败。"); return
    if len(args) < 2: return
    chat_id = str(message.chat.id); status = await message.answer("🎨 正在启动 ModelScope...")
    agent = registry.get_agent("modelscope_generator")
    result = await agent.execute(chat_id, reference_image=args[0], prompt_or_template=args[1])
    await status.delete()
    if result.status == "SUCCESS": await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], delete_after_send=False)
    else: await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    try:
        photo = message.photo[-1]; file_info = await bot.get_file(photo.file_id)
        upload_dir = "/etc/myapp/genie/uploads"; os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"up_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.jpg")
        await bot.download_file(file_info.file_path, file_path); await message.reply(f"📸 图片已落地：`{file_path}`", parse_mode="Markdown")
        await redis_mgr.set_state(chat_id, {"last_image_path": file_path})
    except Exception as e: logger.error(f"Photo error: {e}")

@dp.message(F.text)
async def handle_message(message: types.Message, forced_input: str = None):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id); user_input = forced_input if forced_input else message.text
    all_tools = registry.agents; filtered_tools_list = list(all_tools.values())
    force_tool_for_first_round = None; is_video_task = False; is_image_task = False; is_report_task = False; is_browse_task = False

    if "x.com" in user_input.lower() or "twitter.com" in user_input.lower():
        if any(kw in user_input.lower() for kw in ["下载", "download", "保存", "save", "视频", "video", "媒体"]):
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use video-downloader skill to download from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"; is_video_task = True
        else:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use x-tweet-fetcher skill to fetch from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"
    elif "nanobanana" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use the nanobanana extension. If there is a reference image, use nanobanana__edit_image with preview=false --count=1. If text only, use nanobanana__generate_image with preview=false --count=1. Expand template names.'"
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
        force_tool_for_first_round = "gemini_cli_executor"; is_image_task = True
    elif "vertex" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'vertex_generator' immediately to process this image generation request."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["vertex_generator", "file_sender"]]
        force_tool_for_first_round = "vertex_generator"; is_image_task = True
    elif "modelscope" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'modelscope_generator' immediately to process this image generation request."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["modelscope_generator", "file_sender"]]
        force_tool_for_first_round = "modelscope_generator"; is_image_task = True
    elif any(kw in user_input.lower() for kw in ["监控", "获取", "最新", "快报", "monitor", "gather"]) and any(f_kw in user_input.lower() for f_kw in ["财经", "finance"]):
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'finance_monitor' immediately to gather and analyze financial news."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["finance_monitor", "file_sender", "finance_cleaner"]]
        force_tool_for_first_round = "finance_monitor"; is_report_task = True
    elif "http" in user_input.lower() or any(kw in user_input.lower() for kw in ["抓取", "浏览器", "browser", "打开窗口"]):
        url_match = re.search(r'https?://[^\s]+', user_input)
        target_url = url_match.group(0) if url_match else "about:blank"
        headless_val = "False" if any(kw in user_input.lower() for kw in ["打开窗口", "gui", "显示浏览器", "window"]) else "True"
        keep_open_val = "True" if any(kw in user_input.lower() for kw in ["保持开启", "不关闭", "keep open"]) else "False"
        profile_match = re.search(r'使用([\w_]+)profile', user_input.replace(" ", ""))
        target_profile = profile_match.group(1) if profile_match else "default"
        if any(kw in user_input.lower() for kw in ["chrome", "谷歌", "chromium", "x.com", "推特", "twitter", "xpub"]):
            engine_val = "nodriver"
        else:
            engine_val = "camoufox"
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'stealth_browser' with engine='{engine_val}', headless={headless_val}, profile='{target_profile}', and keep_open={keep_open_val}. Actions: 1. goto {target_url}, 2. extract_semantic."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["stealth_browser", "file_sender"]]
        force_tool_for_first_round = "stealth_browser"; is_browse_task = True
    else: current_input = user_input

    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list]
    max_iterations = 5; status_msg = None

    for i in range(max_iterations):
        history = await redis_mgr.get_history(chat_id); summary = await redis_mgr.get_summary(chat_id); state = await redis_mgr.get_state(chat_id)
        
        # 核心进化：Unified Hierarchical Retrieval Engine (Graph + Vector)
        rag_context = ""
        if i == 0:
            try:
                loop = asyncio.get_event_loop()
                entities = await loop.run_in_executor(None, lambda: orchestrator.extract_entities(user_input))
                vector = await loop.run_in_executor(None, lambda: orchestrator.get_embedding(user_input))
                if vector:
                    combined_rag = await redis_mgr.search_hierarchical(vector, entities=entities)
                    if combined_rag:
                        rag_context = "\n".join([f"- {res}" for res in combined_rag])
                        logger.info(f"Hierarchical RAG loaded: {len(combined_rag)} snippets found.")
            except Exception as e: logger.error(f"Hierarchical RAG retrieval failed: {e}")

        loop_input = f"ROOT GOAL: {user_input}\nCURRENT STEP INPUT: {current_input}"
        if rag_context: loop_input += f"\n[Relevant Past Experiences & Knowledge]:\n{rag_context}"
        if state.get("last_image_path"): loop_input += f"\n[Available Image Context]: {state['last_image_path']}"
        
        if i == 0: status_msg = await message.answer("🔍 正在处理任务...")
        else: await status_msg.edit_text(f"⏳ 正在执行第 {i} 轮自动化...")

        try:
            loop = asyncio.get_event_loop()
            force_tool = force_tool_for_first_round if i == 0 else None
            response = await loop.run_in_executor(None, lambda: orchestrator.chat(loop_input, history, summary=summary, tools=available_tools, force_tool_name=force_tool))
            processed = orchestrator.process_response(response)

            if processed["type"] == "error":
                logger.error(f"Orchestrator error: {processed['content']}")
                await message.answer(f"❌ 调度异常: {processed['content']}"); break

            if processed["type"] == "text":
                reply_text = processed["content"]
                if status_msg: await bot.delete_message(chat_id, status_msg.message_id)
                await safe_send_message(message, reply_text)
                await redis_mgr.push_history(chat_id, "user", user_input if i == 0 else f"[System: Step {i} complete]")
                await redis_mgr.push_history(chat_id, "model", reply_text)
                if i > 0: asyncio.create_task(registry.get_agent("memory_refiner").execute(chat_id, history=history, session_status="SUCCESS"))
                break 

            elif processed["type"] == "function_call":
                agent_name = processed["name"]; agent_args = processed["args"]
                
                # 修复逻辑：物理级参数纠偏
                if agent_name == "stealth_browser" or agent_name == "xpub":
                    if any(kw in user_input.lower() for kw in ["chrome", "谷歌", "chromium", "nodriver", "推特", "x.com"]):
                        agent_args["engine"] = "nodriver"
                    else:
                        if agent_name != "xpub": agent_args["engine"] = "camoufox"
                        else: agent_args["engine"] = "nodriver"

                    if any(kw in user_input.lower() for kw in ["打开窗口", "gui", "显示浏览器", "window"]):
                        agent_args["headless"] = False
                    
                    if any(kw in user_input.lower() for kw in ["保持开启", "不关闭", "keep open"]):
                        agent_args["keep_open"] = True
                        agent_args["headless"] = False
                    
                    if "profile" not in agent_args or agent_args["profile"] == "default":
                        if "geclibot_profile" in user_input: agent_args["profile"] = "geclibot_profile"
                    
                    if agent_name == "stealth_browser" and "actions" in agent_args:
                        agent_args["actions"] = [a for a in agent_args["actions"] if a and (a.get("action") or a.get("url"))]
                        if not agent_args["actions"]:
                            url_search = re.search(r'https?://[^\s]+', user_input)
                            url = agent_args.get("url") or (url_search.group(0) if url_search else None)
                            if url: agent_args["actions"] = [{"action": "goto", "params": {"url": url}}, {"action": "wait", "params": {"seconds": 10}}, {"action": "extract_semantic"}]

                logger.info(f"Final Agent Args for {agent_name}: {agent_args}")
                await status_msg.edit_text(f"🚀 正在调用: {agent_name}...")
                if agent_name == "gemini_cli_executor": agent_args["yolo"] = True
                agent = registry.get_agent(agent_name)
                if not agent: current_input = f"Error: Agent {agent_name} not found."; continue
                logger.info(f"Executing {agent_name} for {chat_id}")
                
                # 安全保护：移除可能存在的 chat_id 冲突
                agent_args.pop("chat_id", None)
                
                async def heartbeat():
                    count = 0
                    while True:
                        await asyncio.sleep(20); count += 1
                        try: await status_msg.edit_text(f"⏳ 任务已执行 {count*20}s...")
                        except: pass
                hb = asyncio.create_task(heartbeat())
                try: result = await agent.execute(chat_id, **agent_args)
                finally: hb.cancel()
                
                if result.status == "SUCCESS":
                    if "file_path" in result.data:
                        if "nanobanana-output" in result.data["file_path"]:
                            await finalize_nanobanana_output(chat_id, result.data, message)
                            if is_image_task or is_video_task or is_report_task or is_browse_task:
                                if is_report_task and "report" in result.data: await safe_send_message(message, f"📊 **财经简报摘要**：\n\n{result.data['report']}")
                                await message.answer("✅ 任务执行完毕。"); break
                        else:
                            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], delete_after_send=False)
                            if is_report_task and "report" in result.data: await safe_send_message(message, f"📊 **财经简报摘要**：\n\n{result.data['report']}")
                            if is_image_task or is_video_task or is_report_task or is_browse_task:
                                await message.answer("✅ 任务执行完毕。"); break
                    
                    if is_browse_task:
                        extracted = result.data.get("page_content", "")
                        if extracted: current_input = f"Tool {agent_name} SUCCESS. HERE IS THE WEB CONTENT:\n\n{extracted[:5000]}\n\nNOW SUMMARIZE THIS TO THE USER IMMEDIATELY. DO NOT CALL ANY MORE TOOLS."
                        else: current_input = f"Tool {agent_name} SUCCESS but content empty. Inform the user."
                        available_tools = [] 
                    else: current_input = f"Tool {agent_name} SUCCESS. Result: {json.dumps(result.data)}"
                    await redis_mgr.set_state(chat_id, result.data)
                else: current_input = f"Tool {agent_name} FAILED: {result.errors}"
                continue
        except Exception as e: logger.error(f"Loop error: {e}", exc_info=True); await message.answer("❌ Orchestration Error."); break

async def cleanup_hanging_processes():
    try:
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmd = " ".join(proc.info['cmdline'] or []); name = proc.info['name'].lower()
                if 'gemini' in cmd and '-p' in cmd: proc.kill()
                if any(b_name in name for b_name in ['firefox', 'chrome', 'chromium', 'chromedriver']):
                    if any(exclude in cmd.lower() for exclude in ['chrome-remote-desktop', 'chromoting']): continue
                    if (datetime.now().timestamp() - proc.info['create_time']) > 1800: proc.kill()
            except: continue
    except: pass

async def main():
    await cleanup_hanging_processes(); logger.info("Starting GenieBot..."); scheduler_mgr.start(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
