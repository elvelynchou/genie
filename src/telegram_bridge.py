import asyncio
import os
import logging
import sys
import json
import shlex
import hashlib
import re
import signal
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
1. GOAL PERSISTENCE: If a user gives a multi-step instruction, fulfill EVERY sub-task. Do not stop until all goals are met.
2. CONTINUITY: After a tool succeeds, immediately plan and execute the NEXT logical step. Do not waste rounds on 'ls' or 'checking' if the path was just provided.
3. FINANCE PIPELINE: Browser -> Cleaner -> RAG -> Report. 
4. SOCIAL PUBLISHING: To post on X (Twitter), use 'xpub'.
5. WORKSPACE: Use 'gemini_cli_executor' for Google Docs and Calendar tasks.
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
    for chunk in chunks:
        try:
            await bot.send_message(target_id, chunk, parse_mode="Markdown", message_thread_id=thread_id)
        except Exception:
            try: await bot.send_message(target_id, chunk, parse_mode=None, message_thread_id=thread_id)
            except: pass
        await asyncio.sleep(0.5)

# --- Handlers ---

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 4 Active.\nTopic-Aware, Safety-Gate & Graceful Shutdown: ONLINE")

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

    # 2. Reasoning Loop
    all_tools = registry.agents
    filtered_tools_list = list(all_tools.values())
    force_tool_for_first_round = None; current_input = user_input
    completed_subtasks = []

    # Intelligent Routing
    task_keywords = ["抓取", "监控", "财经", "生图", "发推", "日历", "doc", "document"]
    detected_keywords = [kw for kw in task_keywords if kw in user_input.lower()]
    is_complex_workflow = len(detected_keywords) >= 2

    if any(kw in user_input.lower() for kw in ["监控", "获取", "最新", "抓取", "财经", "finance"]):
        if not is_complex_workflow:
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["finance_monitor", "finance_cleaner", "file_sender", "stealth_browser"]]
        force_tool_for_first_round = "finance_monitor" if "财经" in user_input.lower() else "stealth_browser"
    elif any(kw in user_input.lower() for kw in ["报纸", "newspaper", "nanobanana", "生图"]):
        if not is_complex_workflow:
            target_tools = ["newspaper_renderer", "gemini_cli_executor", "vertex_generator", "file_sender"]
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in target_tools]
        force_tool_for_first_round = "newspaper_renderer" if "报纸" in user_input.lower() else "gemini_cli_executor"
    elif any(kw in user_input.lower() for kw in ["发推", "推文", "tweet", "post on x"]):
        state = await redis_mgr.get_state(mem_key)
        if state.get("last_image_path"): current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'xpub' with image_path='{state['last_image_path']}'."
        if not is_complex_workflow: filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["xpub", "file_sender"]]
        force_tool_for_first_round = "xpub"

    if is_complex_workflow: filtered_tools_list = list(all_tools.values())
    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list if agent.name != "heartbeat"]
    
    max_iterations = 10; status_msg = None 

    for i in range(max_iterations):
        history = await redis_mgr.get_history(mem_key); summary = await redis_mgr.get_summary(mem_key); state = await redis_mgr.get_state(mem_key)
        
        # 构造增强版推理 Prompt
        loop_input = f"ROOT GOAL: {user_input}\n"
        if completed_subtasks:
            loop_input += f"PROGRESS: The following sub-tasks are already [DONE]: {', '.join(completed_subtasks)}\n"
        loop_input += f"CURRENT STEP CONTEXT: {current_input}\n"
        loop_input += "DIRECTIVE: If there are remaining tasks in the ROOT GOAL, call the next tool. DO NOT output final text until EVERYTHING is finished."
        
        if i == 0: status_msg = await message.answer("🔍 正在启动任务序列...")
        else: await status_msg.edit_text(f"⏳ 正在执行第 {i+1} 轮自动化...")

        try:
            loop = asyncio.get_event_loop()
            force_tool = force_tool_for_first_round if i == 0 else None
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: orchestrator.chat(loop_input, history, summary=summary, tools=available_tools, force_tool_name=force_tool)),
                timeout=120
            )
            processed = orchestrator.process_response(response)

            if processed["type"] == "text":
                reply_text = processed["content"]
                if status_msg: await bot.delete_message(chat_id, status_msg.message_id)
                await safe_send_message(message, reply_text)
                await redis_mgr.push_history(mem_key, "user", user_input if i == 0 else f"[System: All tasks complete]")
                await redis_mgr.push_history(mem_key, "model", reply_text)
                if i > 0: asyncio.create_task(registry.get_agent("memory_refiner").execute(mem_key, history=history, session_status="SUCCESS"))
                break 

            elif processed["type"] == "function_call":
                agent_name = processed["name"]; agent_args = processed["args"]; agent_args.pop("chat_id", None)
                
                # Safety Gate
                if agent_name in ["gemini_cli_executor", "xpub"]:
                    safety_gate = registry.get_agent("safety_gate")
                    audit_res = await safety_gate.execute(chat_id, intent=f"Step {i+1}: {agent_name}", proposed_action=json.dumps(agent_args, ensure_ascii=False), expected_outcome="Goal progress", potential_side_effects="Impact Check")
                    if audit_res.status == "SUCCESS" and audit_res.data.get("score") == "RED":
                        await message.answer(f"🚫 安全拦截: {audit_res.data.get('reason')}"); break

                # Physical Patching
                if agent_name == "xpub":
                    agent_args.update({"engine": "nodriver", "profile": "geclibot_profile", "headless": False})
                    if not agent_args.get("image_path"):
                        st = await redis_mgr.get_state(mem_key)
                        agent_args["image_path"] = st.get("last_image_path") or st.get("file_path")

                agent = registry.get_agent(agent_name)
                if not agent: continue
                
                try: 
                    result = await agent.execute(chat_id, **agent_args)
                    if result.status == "SUCCESS":
                        completed_subtasks.append(agent_name)
                        # Physical Feedback
                        res_data_brief = {k: v for k, v in result.data.items() if k in ["file_path", "last_image_path", "last_report_path", "output"]}
                        current_input = f"Agent {agent_name} SUCCESS. Result Brief: {json.dumps(res_data_brief, ensure_ascii=False)}. CONTINUE TO NEXT STEP."
                        
                        # 核心回显
                        if "file_path" in result.data:
                            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], message_thread_id=tid)
                        
                        if agent_name == "finance_monitor":
                            await safe_send_message(message, f"📊 **财经分析完成**：\n\n{result.data.get('report', '')[:500]}...")
                        elif agent_name == "xpub":
                            await message.answer("🐦 **推文发布成功**！")
                        elif agent_name == "gemini_cli_executor":
                            if any(k in user_input.lower() for k in ["doc", "document", "calendar", "日历"]):
                                await message.answer(f"✅ **Workspace 同步成功**：\n{result.data.get('output', '')[:500]}...")
                        
                        await redis_mgr.set_state(mem_key, result.data)
                    else:
                        current_input = f"Agent {agent_name} FAILED: {result.errors}. RE-EVALUATE."
                except Exception as e: current_input = f"Error: {e}"
                continue
        except Exception as e: 
            logger.error(f"Loop error: {e}", exc_info=True)
            await message.answer("❌ 调度异常。")
            break

async def cleanup_hanging_processes():
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmd_list = proc.info['cmdline'] or []
                cmd = " ".join(cmd_list).lower()
                name = proc.info['name'].lower()
                is_gemini = ('gemini' in cmd) or ('.gemini' in cmd and 'node' in name)
                is_browser = any(b in name for b in ['firefox', 'chrome', 'chromium', 'chromedriver'])
                is_remote_desktop = any(exclude in cmd for exclude in ['chrome-remote-desktop', 'chromoting'])
                if (is_gemini or (is_browser and not is_remote_desktop)):
                    if (datetime.now().timestamp() - proc.info['create_time']) > 10:
                        logger.info(f"Terminating: {name} (PID: {proc.pid})")
                        proc.terminate()
                        try: proc.wait(timeout=2)
                        except psutil.TimeoutExpired: proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): continue
    except Exception as e: logger.error(f"Cleanup error: {e}")

async def main():
    # 强制清理函数
    async def shutdown():
        logger.info("Graceful shutdown initiated...")
        scheduler_mgr.shutdown()
        await cleanup_hanging_processes()
        # 取消所有背景任务
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    try:
        await cleanup_hanging_processes()
        logger.info("Starting GenieBot Bridge-03...")
        scheduler_mgr.start()
        # 让 aiogram 处理信号，它会在收到 SIGINT 时停止轮询并返回
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Main loop error: {e}", exc_info=True)
    finally:
        await shutdown()
        logger.info("GenieBot stopped cleanly.")
        # 强制退出进程，确保终端即时返回
        os._exit(0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
