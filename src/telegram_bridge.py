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

# Configure logging with file support
log_file = "/etc/myapp/genie/logs/bot.log"
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
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
    target_id = message_or_id.chat.id if hasattr(message_or_id, 'chat') else message_or_id
    # 支持话题路由
    thread_id = message_or_id.message_thread_id if hasattr(message_or_id, 'message_thread_id') else None
    
    CHUNK_SIZE = 3500
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    logger.info(f"Sending message to {target_id} (Thread: {thread_id}) in {len(chunks)} chunks...")
    for i, chunk in enumerate(chunks):
        try:
            await bot.send_message(target_id, chunk, parse_mode="Markdown", message_thread_id=thread_id)
            logger.info(f"Chunk {i+1}/{len(chunks)} sent.")
        except Exception as e:
            logger.warning(f"Markdown chunk {i+1} failed, falling back: {e}")
            try:
                await bot.send_message(target_id, chunk, parse_mode=None, message_thread_id=thread_id)
                logger.info(f"Chunk {i+1}/{len(chunks)} sent as plain text.")
            except Exception as e2:
                logger.error(f"Failed to send chunk: {e2}")
        await asyncio.sleep(0.5)

# --- 快捷指令处理器 ---

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 4 Active.\nAdvanced Memory Consolidation: ONLINE")

@dp.message(Command("run_report"))
async def trigger_report(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发每日科技趋势报告流...", message_thread_id=message.message_thread_id)
    asyncio.create_task(scheduler_mgr.daily_github_report())

@dp.message(Command("dream"))
async def cmd_dream(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    status = await message.answer("🌙 正在开启“离线梦境”模式，深度巩固记忆...", message_thread_id=message.message_thread_id)
    agent = registry.get_agent("dreamer")
    # 注意：梦境是全局的，不需要 thread_id 隔离
    result = await agent.execute(str(message.chat.id))
    await status.delete()
    if result.status == "SUCCESS":
        await message.answer(f"✅ 梦境进化完毕！\n\n{result.message}", message_thread_id=message.message_thread_id)
    else:
        await message.answer(f"❌ 梦境中断: {result.errors}", message_thread_id=message.message_thread_id)

@dp.message(Command("reset"))
async def reset_session(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    topic_id = str(message.message_thread_id) if message.message_thread_id else "main"
    mem_key = f"{chat_id}:{topic_id}"
    
    history = await redis_mgr.get_history(mem_key)
    if history:
        asyncio.create_task(registry.get_agent("memory_refiner").execute(mem_key, history=history, session_status="RESET_BY_USER"))
    await redis_mgr.clear_history(mem_key); redis_mgr.client.delete(f"summary:{mem_key}")
    await message.answer(f"🔄 话题 [{topic_id}] 会话已复盘并重置。", message_thread_id=message.message_thread_id)

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    topic_id = str(message.message_thread_id) if message.message_thread_id else "main"
    mem_key = f"{chat_id}:{topic_id}"
    
    try:
        photo = message.photo[-1]; file_info = await bot.get_file(photo.file_id)
        upload_dir = "/etc/myapp/genie/uploads"; os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"up_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{chat_id}.jpg")
        await bot.download_file(file_info.file_path, file_path)
        await message.reply(f"📸 图片已落地：`{file_path}`", parse_mode="Markdown")
        await redis_mgr.set_state(mem_key, {"last_image_path": file_path})
    except Exception as e: logger.error(f"Photo error: {e}")

@dp.message(F.text)
async def handle_message(message: types.Message, forced_input: str = None):
    if not await is_allowed(message.from_user.id): return
    
    # 核心进化：支持话题隔离 (Thread/Topic ID)
    chat_id = str(message.chat.id)
    topic_id = str(message.message_thread_id) if message.message_thread_id else "main"
    mem_key = f"{chat_id}:{topic_id}"
    user_input = forced_input if forced_input else message.text
    
    # 1. L0 Instinct Bypass
    instinct = await redis_mgr.get_instinct(user_input)
    if instinct:
        logger.info(f"L0 Instinct HIT: {instinct['name']} for topic {topic_id}")
        status_msg = await message.answer(f"⚡ **L0 本能激活**：正在执行 {instinct['name']}...", message_thread_id=message.message_thread_id)
        agent = registry.get_agent(instinct["name"])
        if agent:
            agent_args = instinct["args"]
            # 专门针对 finance_monitor 的手动标记，确保结果发回正确话题
            if instinct["name"] == "finance_monitor":
                await scheduler_mgr.half_hourly_finance_report(is_manual=True, topic_id=message.message_thread_id)
                await status_msg.delete(); return
            
            try:
                result = await agent.execute(chat_id, **agent_args)
                await status_msg.delete()
                if result.status == "SUCCESS":
                    if "file_path" in result.data:
                        await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], message_thread_id=message.message_thread_id)
                        await message.answer(f"✅ {instinct['name']} 本能执行完毕。", message_thread_id=message.message_thread_id)
                    else:
                        await message.answer(f"✅ 本能执行成功: {result.message}", message_thread_id=message.message_thread_id)
                    return 
            except Exception as e:
                logger.error(f"L0 Instinct failed: {e}")
                await status_msg.edit_text("⚠️ 本能执行受阻，切换到 LLM 逻辑思考...")

    # 2. 全逻辑推理循环
    all_tools = registry.agents; filtered_tools_list = list(all_tools.values())
    force_tool_for_first_round = None; is_video_task = False; is_image_task = False; is_report_task = False; is_browse_task = False

    if any(kw in user_input.lower() for kw in ["监控", "获取", "最新", "快报", "monitor", "gather"]) and any(f_kw in user_input.lower() for f_kw in ["财经", "finance"]):
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'finance_monitor' immediately."
        force_tool_for_first_round = "finance_monitor"; is_report_task = True
    elif "http" in user_input.lower() or any(kw in user_input.lower() for kw in ["抓取", "浏览器", "browser"]):
        url_match = re.search(r'https?://[^\s]+', user_input)
        target_url = url_match.group(0) if url_match else "about:blank"
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'stealth_browser' with actions: goto {target_url}, extract_semantic."
        force_tool_for_first_round = "stealth_browser"; is_browse_task = True
    else: current_input = user_input

    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list]
    max_iterations = 5; status_msg = None

    for i in range(max_iterations):
        history = await redis_mgr.get_history(mem_key)
        summary = await redis_mgr.get_summary(mem_key)
        state = await redis_mgr.get_state(mem_key)
        
        # Unified Retrieval Engine
        rag_context = ""
        if i == 0:
            try:
                loop = asyncio.get_event_loop()
                vector = await loop.run_in_executor(None, lambda: orchestrator.get_embedding(user_input))
                if vector:
                    combined_rag = await redis_mgr.search_hierarchical(vector)
                    if combined_rag:
                        rag_context = "\n".join([f"- {res}" for res in combined_rag])
            except: pass

        loop_input = f"ROOT GOAL: {user_input}\nCURRENT STEP INPUT: {current_input}"
        if rag_context: loop_input += f"\n[Relevant Past Knowledge]:\n{rag_context}"
        if state.get("last_image_path"): loop_input += f"\n[Image Context]: {state['last_image_path']}"
        
        if i == 0: status_msg = await message.answer("🔍 正在处理...", message_thread_id=message.message_thread_id)
        else: await status_msg.edit_text(f"⏳ 正在执行第 {i} 轮自动化...")

        try:
            loop = asyncio.get_event_loop()
            force_tool = force_tool_for_first_round if i == 0 else None
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: orchestrator.chat(loop_input, history, summary=summary, tools=available_tools, force_tool_name=force_tool)),
                timeout=90
            )
            processed = orchestrator.process_response(response)

            if processed["type"] == "text":
                reply_text = processed["content"]
                if status_msg: await bot.delete_message(chat_id, status_msg.message_id)
                await safe_send_message(message, reply_text)
                await redis_mgr.push_history(mem_key, "user", user_input if i == 0 else f"[Step {i} complete]")
                await redis_mgr.push_history(mem_key, "model", reply_text)
                if i > 0: asyncio.create_task(registry.get_agent("memory_refiner").execute(mem_key, history=history, session_status="SUCCESS"))
                break 

            elif processed["type"] == "function_call":
                agent_name = processed["name"]; agent_args = processed["args"]
                # 话题感知物理修正
                if agent_name == "file_sender": agent_args["message_thread_id"] = message.message_thread_id
                
                agent = registry.get_agent(agent_name)
                if not agent: current_input = f"Error: Agent {agent_name} not found."; continue
                agent_args.pop("chat_id", None)
                
                try: 
                    result = await agent.execute(chat_id, **agent_args)
                    if result.status == "SUCCESS":
                        if agent_name == "finance_monitor":
                            if "report" in result.data: await safe_send_message(message, f"📊 **财经简报摘要**：\n\n{result.data['report']}")
                            await message.answer("✅ 财经监控任务执行完毕。", message_thread_id=message.message_thread_id); break
                        
                        if "file_path" in result.data:
                            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], message_thread_id=message.message_thread_id)
                        
                        if is_browse_task and result.data.get("page_content"):
                            current_input = f"Tool {agent_name} SUCCESS. CONTENT:\n{result.data['page_content'][:5000]}\nSummarize now."
                            available_tools = []
                        else:
                            current_input = f"Tool {agent_name} SUCCESS. Result: {json.dumps(result.data)}"
                        await redis_mgr.set_state(mem_key, result.data)
                    else: current_input = f"Tool {agent_name} FAILED: {result.errors}"
                except Exception as e:
                    current_input = f"Error: {e}"
                continue
        except Exception as e: logger.error(f"Loop error: {e}", exc_info=True); await message.answer("❌ Orchestration Error.", message_thread_id=message.message_thread_id); break

async def cleanup_hanging_processes():
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = " ".join(proc.info['cmdline'] or [])
                if 'gemini' in cmd and '-p' in cmd: proc.kill()
                if any(b in proc.info['name'].lower() for b in ['firefox', 'chrome', 'chromium']):
                    if any(ex in cmd.lower() for ex in ['chrome-remote-desktop', 'chromoting']): continue
                    proc.kill()
            except: continue
    except: pass

async def main():
    try:
        await cleanup_hanging_processes()
        logger.info("Starting GenieBot Bridge-03 in foreground mode...")
        scheduler_mgr.start()
        await dp.start_polling(bot)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received.")
    finally:
        scheduler_mgr.shutdown(); logger.info("GenieBot stopped.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
