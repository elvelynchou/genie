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
from agents.analyzer.daily_report_agent import DailyReportAgent
from agents.analyzer.heartbeat_agent import HeartbeatAgent
from agents.analyzer.safety_agent import SafetyAgent
from agents.analyzer.sys_check_agent import SysCheckAgent
from agents.common.gemini_cli_agent import GeminiCLIAgent
from agents.common.browser_agent import BrowserAgent
from agents.imgtools.image_ocr import ImageOCRAgent
from agents.imgtools.prompt_inverse import PromptInverseAgent
from agents.imgtools.template_creator import TemplateCreatorAgent
from agents.imgtools.newspaper_agent import NewspaperAgent
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
redis_mgr.init_vector_index(dim=3072) 

# Enhanced Orchestrator System Instruction
system_instruction = """
You are GenieBot, an autonomous Multi-Agent system. 
OPERATIONAL DIRECTIVES:
1. GOAL PERSISTENCE: If a user gives a multi-step instruction, fulfill EVERY sub-task.
2. FINANCE PIPELINE: When monitoring finance, the system uses Browser -> Cleaner -> RAG -> Report. 
3. SOCIAL PUBLISHING: To post on X (Twitter), use 'xpub'.
4. BROWSER STRATEGY: When using 'stealth_browser' to read a page, you MUST include at least two actions: 1) {"action": "goto", "url": "..."} and 2) {"action": "extract_semantic"}.
5. TOOL USAGE: Call 'gemini_cli_executor' with 'yolo=True' for specialized Skill tasks (X fetching, video downloading, nanobanana).
6. KNOWLEDGE UTILIZATION: You have access to a Graph-RAG system. Prioritize [Relevant Past Knowledge].
"""
orchestrator = GeminiOrchestrator(api_key=GEMINI_KEY, system_instruction=system_instruction)

# Register Agents
registry.register_agent(LinkContentAgent())
registry.register_agent(FileSenderAgent(bot_instance=bot))
registry.register_agent(TrendAnalyzerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(MemoryRefinerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(LogAnchorAgent(orchestrator=orchestrator))
registry.register_agent(FinanceMonitorAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(FinanceCleanerAgent(orchestrator=orchestrator))
registry.register_agent(XPubAgent(orchestrator=orchestrator))
registry.register_agent(DreamerAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(DailyReportAgent(orchestrator=orchestrator))
registry.register_agent(HeartbeatAgent(orchestrator=orchestrator, bot=bot))
registry.register_agent(SafetyAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(SysCheckAgent(orchestrator=orchestrator))
registry.register_agent(GeminiCLIAgent())
registry.register_agent(BrowserAgent())
registry.register_agent(ImageOCRAgent(orchestrator=orchestrator))
registry.register_agent(PromptInverseAgent(orchestrator=orchestrator))
registry.register_agent(TemplateCreatorAgent())
registry.register_agent(NewspaperAgent(orchestrator=orchestrator, redis_mgr=redis_mgr))
registry.register_agent(VertexGenAgent())
registry.register_agent(ModelScopeGenAgent())

# Initialize Scheduler
scheduler_mgr = SchedulerManager(bot, redis_mgr, orchestrator, ADMIN_CHAT_ID)

async def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS: return True
    return str(user_id) in ALLOWED_USERS

async def safe_send_message(message_or_id, text: str):
    target_id = message_or_id.chat.id if hasattr(message_or_id, 'chat') else message_or_id
    thread_id = message_or_id.message_thread_id if hasattr(message_or_id, 'message_thread_id') else None
    
    CHUNK_SIZE = 3500
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    logger.info(f"Sending message to {target_id} (Thread: {thread_id}) in {len(chunks)} chunks...")
    for i, chunk in enumerate(chunks):
        try:
            await bot.send_message(target_id, chunk, parse_mode="Markdown", message_thread_id=thread_id)
            logger.info(f"Chunk {i+1}/{len(chunks)} sent.")
        except Exception:
            try: await bot.send_message(target_id, chunk, parse_mode=None, message_thread_id=thread_id)
            except: pass
        await asyncio.sleep(0.5)

# --- Command Handlers ---

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 4 Active.\nTopic-Aware & Safety Gate: ONLINE")

@dp.message(Command("run_report"))
async def trigger_report(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发：科技趋势扫描...")
    await registry.get_agent("heartbeat").execute(str(message.chat.id), force_task="daily_report", message_thread_id=message.message_thread_id)

@dp.message(Command("run_finance"))
async def trigger_finance(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发：财经监控...")
    await registry.get_agent("heartbeat").execute(str(message.chat.id), force_task="finance_monitor", is_manual=True, message_thread_id=message.message_thread_id)

@dp.message(Command("dream"))
async def cmd_dream(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🌙 手动触发：离线梦境...")
    await registry.get_agent("heartbeat").execute(str(message.chat.id), force_task="dreamer", message_thread_id=message.message_thread_id)

@dp.message(Command("reset"))
async def reset_session(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id); tid = message.message_thread_id; mem_key = f"{chat_id}:{tid or 'main'}"
    history = await redis_mgr.get_history(mem_key)
    if history: asyncio.create_task(registry.get_agent("memory_refiner").execute(mem_key, history=history, session_status="RESET"))
    await redis_mgr.clear_history(mem_key); await message.answer(f"🔄 话题会话已重置。")

# --- Main Message Handler ---

@dp.message(F.text)
async def handle_message(message: types.Message, forced_input: str = None):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id); tid = message.message_thread_id; mem_key = f"{chat_id}:{tid or 'main'}"
    user_input = forced_input if forced_input else message.text
    
    # 1. L0 Instinct Bypass
    instinct = await redis_mgr.get_instinct(user_input)
    if instinct:
        if instinct["name"] in ["finance_monitor", "daily_report", "dreamer"]:
            await registry.get_agent("heartbeat").execute(chat_id, force_task=instinct["name"], is_manual=True, message_thread_id=tid)
            return

    # 2. Reasoning Loop - Explicit Routing for Skills
    all_tools = registry.agents
    filtered_tools_list = list(all_tools.values())
    force_tool_for_first_round = None; is_browse_task = False
    current_input = user_input

    # 核心进化：强力预路由并收缩工具箱
    logger.info(f"Routing check for input: {user_input}")
    
    # --- X 发布强力预路由 ---
    if any(kw in user_input.lower() for kw in ["发推", "推文", "tweet", "post on x"]):
        logger.info("Routing to xpub...")
        # 尝试从状态中寻找刚才生成的图片
        state = await redis_mgr.get_state(mem_key)
        last_img = state.get("file_path")
        if last_img:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'xpub' with content='(Write a short insightful tweet based on the news)' and image_path='{last_img}' and profile='geclibot_profile'."
        else:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'xpub' using geclibot_profile. If an image was recently generated, use it."
        
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["xpub", "file_sender"]]
        force_tool_for_first_round = "xpub"

    elif "x.com" in user_input.lower() or "twitter.com" in user_input.lower():
        if any(kw in user_input.lower() for kw in ["下载", "视频", "video", "媒体"]):
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use video-downloader skill to download from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"
        else:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use x-tweet-fetcher skill to fetch from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"
    elif "nanobanana" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use nanobanana extension. If reference image exists, use nanobanana__edit_image with preview=false --count=1. If text only, use nanobanana__generate_image with preview=false --count=1.'."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
        force_tool_for_first_round = "gemini_cli_executor"
    elif "报纸" in user_input or "newspaper" in user_input.lower():
        logger.info("Routing to newspaper_renderer...")
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'newspaper_renderer' immediately using the latest financial data in your context."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["newspaper_renderer", "file_sender"]]
        force_tool_for_first_round = "newspaper_renderer"
    elif any(kw in user_input.lower() for kw in ["财经", "finance"]):
        logger.info("Routing to finance_monitor...")
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["finance_monitor", "finance_cleaner", "file_sender"]]
        force_tool_for_first_round = "finance_monitor"
    elif "http" in user_input.lower() or "抓取" in user_input:
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["stealth_browser", "file_sender"]]
        force_tool_for_first_round = "stealth_browser"; is_browse_task = True

    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list if agent.name != "heartbeat"]
    max_iterations = 5; status_msg = None

    for i in range(max_iterations):
        history = await redis_mgr.get_history(mem_key); summary = await redis_mgr.get_summary(mem_key); state = await redis_mgr.get_state(mem_key)
        loop_input = f"ROOT GOAL: {user_input}\nCURRENT STEP: {current_input}"
        
        if i == 0: status_msg = await message.answer("🔍 正在启动任务...")
        else: await status_msg.edit_text(f"⏳ 正在执行第 {i} 轮自动化...")

        try:
            loop = asyncio.get_event_loop()
            force_tool = force_tool_for_first_round if i == 0 else None
            logger.info(f"Round {i+1} | Force Tool: {force_tool}")
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
                agent_args.pop("chat_id", None)
                
                # --- L0-Safety-Gate: 高危动作拦截 ---
                if agent_name in ["gemini_cli_executor", "xpub"]:
                    logger.info(f"🛡️ Auditing high-risk tool: {agent_name}")
                    safety_gate = registry.get_agent("safety_gate")
                    audit_res = await safety_gate.execute(
                        chat_id, 
                        intent=f"Reasoning Loop Round {i+1}: 执行 {agent_name}",
                        proposed_action=json.dumps(agent_args, ensure_ascii=False),
                        expected_outcome="继续推进 ROOT GOAL",
                        potential_side_effects="系统配置变更或社交平台发布"
                    )
                    if audit_res.status == "SUCCESS":
                        score = audit_res.data.get("score")
                        if score == "RED":
                            await message.answer(f"🚫 **安全拦截 (RED)**：{audit_res.data.get('reason')}")
                            break
                        elif score == "YELLOW":
                            await message.answer(f"⚠️ **风险预警 (YELLOW)**：{audit_res.data.get('reason')}")

                # --- 物理参数强制修正层 ---
                if agent_name == "xpub":
                    agent_args["engine"] = "nodriver"
                    agent_args["profile"] = "geclibot_profile"
                    agent_args["headless"] = False # 强制前台 GUI 模式
                    # 自动补全图片路径（如果 AI 漏掉了）
                    if "image_path" not in agent_args or not agent_args["image_path"]:
                        state = await redis_mgr.get_state(mem_key)
                        if state.get("file_path"):
                            agent_args["image_path"] = state.get("file_path")
                            logger.info(f"Auto-injected image_path: {agent_args['image_path']}")

                if agent_name == "stealth_browser":
                    if any(kw in user_input.lower() for kw in ["x.com", "twitter", "推特", "chrome"]):
                        agent_args["engine"] = "nodriver"; agent_args["profile"] = "geclibot_profile"
                    if "actions" not in agent_args or not agent_args["actions"]:
                        url_search = re.search(r'https?://[^\s]+', user_input)
                        url = url_search.group(0) if url_search else "about:blank"
                        agent_args["actions"] = [{"action": "goto", "params": {"url": url}}, {"action": "wait", "params": {"seconds": 10}}, {"action": "extract_semantic"}]

                agent = registry.get_agent(agent_name)
                if not agent: continue
                
                try: 
                    result = await agent.execute(chat_id, **agent_args)
                    if result.status == "SUCCESS":
                        if agent_name == "finance_monitor":
                            if "report" in result.data: await safe_send_message(message, f"📊 **财经简报摘要**：\n\n{result.data['report']}")
                            await message.answer("✅ 财经监控任务执行完毕。"); break
                        
                        if agent_name == "newspaper_renderer":
                            if "file_path" in result.data:
                                await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], message_thread_id=tid)
                            await message.answer("🗞️ **复古报纸生成完毕**！"); break

                        if agent_name == "xpub":
                            await message.answer("🐦 **推文已成功发布**！"); break

                        if "file_path" in result.data:
                            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], message_thread_id=tid)
                        
                        if is_browse_task and result.data.get("page_content"):
                            current_input = f"SUCCESS. CONTENT:\n{result.data['page_content'][:5000]}\nSummarize and analyze now."
                            available_tools = []
                        else:
                            current_input = f"Tool {agent_name} SUCCESS. Result: {json.dumps(result.data)}"
                        await redis_mgr.set_state(mem_key, result.data)
                    else:
                        current_input = f"Tool {agent_name} FAILED: {result.errors}"
                except Exception as e: current_input = f"Error: {e}"
                continue
        except Exception as e: 
            logger.error(f"Loop error: {e}", exc_info=True)
            await message.answer("❌ 调度异常。")
            break

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
    loop = asyncio.get_running_loop()
    
    # 强制清理函数
    async def shutdown(signal=None):
        if signal: logger.warning(f"Received exit signal {signal.name}...")
        logger.info("Closing GenieBot and cleaning up resources...")
        
        # 停止调度器
        scheduler_mgr.shutdown()
        
        # 强制杀死残留进程
        await cleanup_hanging_processes()
        
        # 取消所有运行中的任务
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
        loop.stop()

    # 注册信号处理 (针对 Linux)
    import signal
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    try:
        await cleanup_hanging_processes(); logger.info("Starting GenieBot Bridge-03...")
        scheduler_mgr.start(); await dp.start_polling(bot)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        await shutdown()
        logger.info("GenieBot stopped cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        sys.exit(1)
