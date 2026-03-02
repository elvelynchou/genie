import asyncio
import os
import logging
import sys
import json

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
from agents.common.github_analyzer import GithubAnalyzerAgent
from agents.common.gemini_cli_agent import GeminiCLIAgent
from agents.common.browser_agent import BrowserAgent
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
1. GOAL PERSISTENCE: If a user gives a multi-step instruction (e.g., 'fetch, translate, and analyze'), keep track of ALL steps. DO NOT stop after the first tool call.
2. METADATA REPORTING: If any tool returns a 'file_path', you MUST explicitly mention the file name and directory (/etc/myapp/genie/downloads/) in your final response.
3. LANGUAGE: Always respond in the language used by the user (Chinese in this case). If 'translation' is requested, ensure the final report is in the target language.
4. TOOL USAGE: Call 'gemini_cli_executor' with 'yolo=True' for all X/Twitter and video tasks.
5. FINAL CHECK: Before ending the conversation, verify if you have fulfilled EVERY sub-task requested by the user.
"""
orchestrator = GeminiOrchestrator(api_key=GEMINI_KEY, system_instruction=system_instruction)

# Register Agents
registry.register_agent(LinkContentAgent())
registry.register_agent(FileSenderAgent(bot_instance=bot))
registry.register_agent(GithubAnalyzerAgent(orchestrator=orchestrator))
registry.register_agent(GeminiCLIAgent())
registry.register_agent(BrowserAgent())

# Initialize Scheduler
scheduler_mgr = SchedulerManager(bot, redis_mgr, orchestrator, ADMIN_CHAT_ID)

async def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
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
            await bot.send_message(target_id, escape_markdown(chunk), parse_mode=parse_mode)
        except TelegramBadRequest:
            try:
                await bot.send_message(target_id, chunk, parse_mode=parse_mode)
            except TelegramBadRequest:
                await bot.send_message(target_id, chunk, parse_mode=None)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 3 Active.\nAgent Coordination System: ONLINE")

@dp.message(Command("run_report"))
async def trigger_report(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🚀 手动触发每日报告流...")
    asyncio.create_task(scheduler_mgr.daily_github_report())

@dp.message(Command("capabilities"))
async def list_capabilities(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.answer("🔍 正在查询系统级能力清单...")
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(str(message.chat.id), action="list")
    await safe_send_message(message, result.message)

@dp.message(Command("reset"))
async def reset_session(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    await redis_mgr.clear_history(chat_id)
    redis_mgr.client.delete(f"summary:{chat_id}")
    await message.answer("🔄 会话已重置。")

@dp.message(F.text)
async def handle_message(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    user_input = message.text

    all_tools = registry.agents
    filtered_tools_list = list(all_tools.values())
    is_video_task = False
    if "x.com" in user_input.lower() or "twitter.com" in user_input.lower():
        if any(kw in user_input.lower() for kw in ["下载", "download", "保存", "save", "视频", "video", "媒体"]):
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call the 'gemini_cli_executor' tool immediately. Set action='execute' and yolo=True. Prompt for the tool: 'Use the video-downloader skill to download the video from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name not in ["link_content_extractor", "stealth_browser", "github_analyzer"]]
            is_video_task = True
        else:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call the 'gemini_cli_executor' tool immediately. Set action='execute' and yolo=True. Prompt for the tool: 'Use the x-tweet-fetcher skill to fetch and analyze the content from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name not in ["link_content_extractor", "stealth_browser", "github_analyzer"]]
    else:
        current_input = user_input

    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list]
    max_iterations = 5
    status_msg = None
    
    for i in range(max_iterations):
        history = await redis_mgr.get_history(chat_id)
        summary = await redis_mgr.get_summary(chat_id)
        if i == 0:
            status_msg = await message.answer("🔍 正在思考处理方案...")
        else:
            await status_msg.edit_text(f"⏳ 正在执行第 {i} 轮任务自动化...")

        try:
            loop = asyncio.get_event_loop()
            loop_input = f"ROOT GOAL: {user_input}\nCURRENT STEP INPUT: {current_input}"
            force_tool = "gemini_cli_executor" if (is_video_task and i == 0) else None
            
            response = await loop.run_in_executor(None, lambda: orchestrator.chat(
                loop_input, history, summary=summary, tools=available_tools, force_tool_name=force_tool
            ))
            processed = orchestrator.process_response(response)

            if processed["type"] == "text":
                reply_text = processed["content"]
                if status_msg: await bot.delete_message(chat_id, status_msg.message_id)
                await safe_send_message(message, reply_text)
                await redis_mgr.push_history(chat_id, "user", user_input if i == 0 else f"[System: Step {i} complete]")
                await redis_mgr.push_history(chat_id, "model", reply_text)
                break 

            elif processed["type"] == "function_call":
                agent_name = processed["name"]
                agent_args = processed["args"]
                await status_msg.edit_text(f"🚀 正在调用: {agent_name}...")
                
                if agent_name == "gemini_cli_executor":
                    if any(keyword in str(agent_args.get("prompt", "")).lower() for keyword in ["download", "fetch", "x.com", "video"]):
                        agent_args["yolo"] = True
                
                agent = registry.get_agent(agent_name)
                if not agent:
                    current_input = f"Error: Agent {agent_name} not found."
                    continue

                async def heartbeat():
                    count = 0
                    while True:
                        await asyncio.sleep(20)
                        count += 1
                        try: await status_msg.edit_text(f"⏳ 任务已执行 {count*20}s...")
                        except: pass

                hb = asyncio.create_task(heartbeat())
                try:
                    result = await agent.execute(chat_id, **agent_args)
                finally:
                    hb.cancel()
                
                if result.status == "SUCCESS":
                    if "file_path" in result.data:
                        await message.answer(f"📦 阶段性成果：文件已保存至 `{result.data['file_path']}`", parse_mode="Markdown")
                    current_input = f"Tool {agent_name} SUCCESS. Result: {json.dumps(result.data)}"
                    await redis_mgr.set_state(chat_id, result.data)
                else:
                    current_input = f"Tool {agent_name} FAILED: {result.errors}"
                continue

        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            await message.answer("❌ Orchestration Error.")
            break

async def cleanup_hanging_processes():
    logger.info("Cleaning processes...")
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
            cmd = " ".join(proc.info['cmdline'] or [])
            if 'gemini' in cmd and '-p' in cmd and (proc.info['ppid'] == 1 or (asyncio.get_event_loop().time() - proc.create_time()) > 3600):
                proc.kill()
    except: pass

async def main():
    await cleanup_hanging_processes()
    logger.info("Starting GenieBot...")
    scheduler_mgr.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
