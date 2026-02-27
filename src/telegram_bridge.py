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
from agents.common.video_downloader import VideoDownloaderAgent
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
orchestrator = GeminiOrchestrator(api_key=GEMINI_KEY)

# Register Agents
registry.register_agent(LinkContentAgent())
registry.register_agent(VideoDownloaderAgent())
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
    """
    Escapes markdown special characters for Telegram Markdown V1.
    """
    if not text:
        return ""
    # Characters that need escaping in Markdown V1: _, *, `, [
    # We use a more comprehensive regex-based approach or multiple replaces
    escape_chars = r'_*`['
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text

async def safe_send_message(message_or_id, text: str):
    parse_mode = "Markdown"
    target_id = message_or_id.chat.id if hasattr(message_or_id, 'chat') else message_or_id
    
    # Try sending with escaped markdown
    try:
        await bot.send_message(target_id, escape_markdown(text), parse_mode=parse_mode)
    except TelegramBadRequest as e:
        logger.warning(f"Markdown failed: {e}. Falling back to raw text.")
        try:
            # If escaped failed, try sending the original text as is (sometimes works better)
            await bot.send_message(target_id, text, parse_mode=parse_mode)
        except TelegramBadRequest:
            # Absolute fallback: Plain text
            await bot.send_message(target_id, text, parse_mode=None)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    await message.reply("GenieBot Bridge-03 Phase 3 Active.\nAgent Coordination System: ONLINE\nDaily Task Scheduler: READY")

@dp.message(Command("run_report"))
async def trigger_report(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    await message.answer("🚀 手动触发每日报告流...")
    asyncio.create_task(scheduler_mgr.daily_github_report())

@dp.message(Command("capabilities"))
async def list_capabilities(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return
    await message.answer("🔍 正在查询系统级能力清单...")
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(str(message.chat.id), action="list")
    await safe_send_message(message, result.message)

@dp.message(F.text)
async def handle_message(message: types.Message):
    if not await is_allowed(message.from_user.id):
        return

    chat_id = str(message.chat.id)
    user_input = message.text
    
    # 准备 Tools 定义 (给 Gemini)
    available_tools = [agent.get_tool_declaration() for agent in registry.agents.values()]

    # 循环调度逻辑 (支持链式调用)
    current_input = user_input
    max_iterations = 5
    
    for i in range(max_iterations):
        history = await redis_mgr.get_history(chat_id)
        summary = await redis_mgr.get_summary(chat_id)
        # TODO: Add RAG context search here if needed

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: orchestrator.chat(current_input, history, summary=summary, tools=available_tools)
            )
            
            processed = orchestrator.process_response(response)

            if processed["type"] == "text":
                reply_text = processed["content"]
                await safe_send_message(message, reply_text)
                # 记录对话
                await redis_mgr.push_history(chat_id, "user", current_input if i == 0 else f"[System: Tool Result Processed]")
                await redis_mgr.push_history(chat_id, "model", reply_text)
                break # 对话结束

            elif processed["type"] == "function_call":
                agent_name = processed["name"]
                agent_args = processed["args"]
                
                agent = registry.get_agent(agent_name)
                if not agent:
                    current_input = f"Error: Agent {agent_name} not found."
                    continue

                # 执行 Agent
                logger.info(f"Executing {agent_name} for {chat_id}")
                result = await agent.execute(chat_id, **agent_args)
                
                if result.status == "SUCCESS":
                    # 将执行结果反馈给 Gemini，决定下一步
                    current_input = f"Tool {agent_name} executed successfully. Result: {json.dumps(result.data)}. Message: {result.message}"
                    # 记录状态到 Redis 以便后续 Agent 共享
                    await redis_mgr.set_state(chat_id, result.data)
                else:
                    current_input = f"Tool {agent_name} failed. Error: {result.errors}. Message: {result.message}"
                
                # 继续循环，让 Gemini 看到结果并决定是结束还是继续呼叫下一个 Tool
                continue

        except Exception as e:
            logger.error(f"Execution loop error: {e}", exc_info=True)
            await message.answer("❌ Orchestration Error.")
            break

async def main():
    logger.info("Starting GenieBot Bridge-03...")
    # Start Scheduler
    scheduler_mgr.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
