import asyncio
import os
import logging
import sys
import json
import shlex
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
from agents.common.github_analyzer import GithubAnalyzerAgent
from agents.common.gemini_cli_agent import GeminiCLIAgent
from agents.common.browser_agent import BrowserAgent
from agents.imgtools.image_ocr import ImageOCRAgent
from agents.imgtools.prompt_inverse import PromptInverseAgent
from agents.imgtools.template_creator import TemplateCreatorAgent
from agents.imgtools.vertex_agent import VertexGenAgent
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
3. IMAGE WORKFLOW:
   - To extract details from image: Use 'prompt_inverse'.
   - To save these details as a reusable template: Use 'image_template_creator'.
   - To generate/edit images with Vertex AI: Use 'vertex_generator'.
   - To generate/edit images with Nanobanana: Use 'gemini_cli_executor' with yolo=True, specifying the tool nanobanana__edit_image or nanobanana__generate_image.
   - Always apply the 'Strict identity lock' logic for portraits.
4. TOOL USAGE: Call 'gemini_cli_executor' with 'yolo=True' for X/video and Nanobanana tasks.
"""
orchestrator = GeminiOrchestrator(api_key=GEMINI_KEY, system_instruction=system_instruction)

# Register Agents (Unique registration)
registry.register_agent(LinkContentAgent())
registry.register_agent(FileSenderAgent(bot_instance=bot))
registry.register_agent(GithubAnalyzerAgent(orchestrator=orchestrator))
registry.register_agent(GeminiCLIAgent())
registry.register_agent(BrowserAgent())
registry.register_agent(ImageOCRAgent(orchestrator=orchestrator))
registry.register_agent(PromptInverseAgent(orchestrator=orchestrator))
registry.register_agent(TemplateCreatorAgent())
registry.register_agent(VertexGenAgent())

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
            await bot.send_message(target_id, escape_markdown(chunk), parse_mode=parse_mode)
        except TelegramBadRequest:
            try:
                await bot.send_message(target_id, chunk, parse_mode=parse_mode)
            except TelegramBadRequest:
                await bot.send_message(target_id, chunk, parse_mode=None)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    await message.reply("GenieBot Bridge-03 Phase 3++ Active.\nImage Engine & Task Orchestrator: READY")

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

def load_template_prompt(prompt_or_template: str) -> str:
    template_path = f"/etc/myapp/genie/src/agents/imgtools/genimgtemplate/{prompt_or_template}.json"
    if os.path.exists(template_path):
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                tpl = json.load(f)
                instr = tpl.get("core_instructions", "")
                details = tpl.get("visual_details", {})
                return f"{instr}\nVisual Details: {json.dumps(details)}"
        except Exception as e:
            logger.error(f"Failed to load template {template_path}: {e}")
    return prompt_or_template

async def finalize_nanobanana_output(chat_id: str, result_data: dict, message: types.Message):
    all_paths = result_data.get("all_paths", [result_data.get("file_path")])
    valid_paths = [p for p in all_paths if p and os.path.exists(p)]
    
    if valid_paths:
        for idx, file_path in enumerate(valid_paths):
            if "nanobanana-output" in file_path:
                img_output_dir = "/etc/myapp/genie/img_output"
                os.makedirs(img_output_dir, exist_ok=True)
                date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_filename = f"nanobanana_{date_str}_{chat_id}_{idx}.png"
                new_path = os.path.join(img_output_dir, new_filename)
                os.rename(file_path, new_path)
                file_path = new_path
            
            await registry.get_agent("file_sender").execute(chat_id, file_path=file_path, delete_after_send=False)
    else:
        await safe_send_message(message, f"❌ 生图成功但未找到文件路径:\n{result_data.get('output', '')}")

@dp.message(Command("generate"))
async def cmd_generate(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    prompt = message.text.replace("/generate", "").strip()
    if not prompt:
        await message.answer("Usage: `/generate \"prompt\"`", parse_mode="Markdown")
        return
    
    chat_id = str(message.chat.id)
    status = await message.answer("🎨 正在使用 gemini_cli_executor 启动文生图...")
    
    final_prompt = load_template_prompt(prompt)
    cli_prompt = f"MUST USE TOOL 'nanobanana__generate_image'. CRITICAL: Set preview=false. PROMPT: {final_prompt}"
    
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(chat_id, action="execute", prompt=cli_prompt, yolo=True)
    
    await status.delete()
    if result.status == "SUCCESS":
        await finalize_nanobanana_output(chat_id, result.data, message)
    else:
        await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    try:
        args = shlex.split(message.text.replace("/edit", "").strip())
    except ValueError:
        await message.answer("❌ 参数解析失败，请检查引号。")
        return
    if len(args) < 2:
        await message.answer("Usage: `/edit filename \"prompt\"`", parse_mode="Markdown")
        return
        
    chat_id = str(message.chat.id)
    status = await message.answer(f"🎨 正在使用 {args[0]} 启动图生图重绘...")
    
    ref_path = args[0]
    if "/" not in ref_path:
        ref_path = os.path.join("/etc/myapp/genie/src/agents/imgtools/characters", ref_path)
    
    final_prompt = load_template_prompt(args[1])
    cli_prompt = f"MUST USE TOOL 'nanobanana__edit_image'. CRITICAL: Set preview=false. Input file: {ref_path}. PROMPT: {final_prompt}"
    
    agent = registry.get_agent("gemini_cli_executor")
    result = await agent.execute(chat_id, action="execute", prompt=cli_prompt, yolo=True)
    
    await status.delete()
    if result.status == "SUCCESS":
        await finalize_nanobanana_output(chat_id, result.data, message)
    else:
        await safe_send_message(message, f"❌ 失败: {result.errors}")

@dp.message(Command("vertex"))
async def cmd_vertex(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    try:
        args = shlex.split(message.text.replace("/vertex", "").strip())
    except ValueError:
        await message.answer("❌ 参数解析失败，请检查引号。")
        return
    if len(args) == 0:
        await message.answer("Usage: `/vertex [filename] \"prompt\"`", parse_mode="Markdown")
        return
        
    chat_id = str(message.chat.id)
    status = await message.answer("🎨 正在启动 Vertex AI 生图引擎...")
    
    agent = registry.get_agent("vertex_generator")
    if len(args) == 1:
        result = await agent.execute(chat_id, prompt_or_template=args[0])
    else:
        result = await agent.execute(chat_id, reference_image=args[0], prompt_or_template=args[1])
        
    await status.delete()
    if result.status == "SUCCESS":
        if "file_path" in result.data:
            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], delete_after_send=False)
        if result.data.get("text_response"):
            await safe_send_message(message, f"✅ Vertex 生成附言！\n{result.data['text_response']}")
    else:
        await safe_send_message(message, f"❌ 失败: {result.errors}\n{result.message}")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        upload_dir = "/etc/myapp/genie/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(upload_dir, f"up_{date_str}_{chat_id}.jpg")
        await bot.download_file(file_info.file_path, file_path)
        await message.reply(f"📸 图片已落地：`{file_path}`", parse_mode="Markdown")
        await redis_mgr.set_state(chat_id, {"last_image_path": file_path})
    except Exception as e:
        logger.error(f"Photo error: {e}")

@dp.message(F.text)
async def handle_message(message: types.Message, forced_input: str = None):
    if not await is_allowed(message.from_user.id): return
    chat_id = str(message.chat.id)
    user_input = forced_input if forced_input else message.text

    all_tools = registry.agents
    filtered_tools_list = list(all_tools.values())

    force_tool_for_first_round = None
    is_video_task = False
    is_image_task = False

    if "x.com" in user_input.lower() or "twitter.com" in user_input.lower():
        if any(kw in user_input.lower() for kw in ["下载", "download", "保存", "save", "视频", "video", "媒体"]):
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use video-downloader skill to download from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"
            is_video_task = True
        else:
            current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use x-tweet-fetcher skill to fetch from {user_input}'."
            filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
            force_tool_for_first_round = "gemini_cli_executor"
    elif "nanobanana" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'gemini_cli_executor' with yolo=True. Prompt: 'Use the nanobanana extension. If there is a reference image, use nanobanana__edit_image with preview=false. If text only, use nanobanana__generate_image with preview=false and outputCount=1. Expand template names.'"
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["gemini_cli_executor", "file_sender"]]
        force_tool_for_first_round = "gemini_cli_executor"
        is_image_task = True
    elif "vertex" in user_input.lower():
        current_input = f"USER REQUEST: {user_input}\nCOMMAND: Call 'vertex_generator' immediately to process this image generation request."
        filtered_tools_list = [agent for name, agent in all_tools.items() if name in ["vertex_generator", "file_sender"]]
        force_tool_for_first_round = "vertex_generator"
        is_image_task = True
    else:
        current_input = user_input

    available_tools = [agent.get_tool_declaration() for agent in filtered_tools_list]
    max_iterations = 5
    status_msg = None

    for i in range(max_iterations):
        history = await redis_mgr.get_history(chat_id)
        summary = await redis_mgr.get_summary(chat_id)
        state = await redis_mgr.get_state(chat_id)

        loop_input = f"ROOT GOAL: {user_input}\nCURRENT STEP INPUT: {current_input}"
        if state.get("last_image_path"):
            loop_input += f"\n[Available Image Context]: {state['last_image_path']}"

        if i == 0:
            status_msg = await message.answer("🔍 正在处理任务...")
        else:
            await status_msg.edit_text(f"⏳ 正在执行第 {i} 轮自动化...")

        try:
            loop = asyncio.get_event_loop()
            force_tool = force_tool_for_first_round if i == 0 else None
            
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
                    agent_args["yolo"] = True
                
                agent = registry.get_agent(agent_name)
                if not agent:
                    current_input = f"Error: Agent {agent_name} not found."
                    continue

                logger.info(f"Executing {agent_name} for {chat_id}")

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
                        # 核心改进：统一处理所有 Agent 返回的图片/文件
                        if "nanobanana-output" in result.data["file_path"]:
                            await finalize_nanobanana_output(chat_id, result.data, message)
                            if is_image_task or is_video_task:
                                logger.info("Nanobanana output finalized. Terminating loop.")
                                await message.answer("✅ 任务执行完毕。")
                                break
                        else:
                            await message.answer(f"📦 阶段成果已落地：`{result.data['file_path']}`", parse_mode="Markdown")
                            # 自动发送其他路径的文件
                            await registry.get_agent("file_sender").execute(chat_id, file_path=result.data["file_path"], delete_after_send=False)
                            if is_image_task or is_video_task:
                                logger.info("File sent. Terminating loop.")
                                await message.answer("✅ 任务执行完毕。")
                                break
                    
                    current_input = f"Tool {agent_name} SUCCESS. Result: {json.dumps(result.data)}"
                    await redis_mgr.set_state(chat_id, result.data)
                    
                    # 防止无限生图循环：如果已经成功发出了文件，且是生图/下载任务，则强制结束循环
                    if agent_name == "file_sender" and (is_video_task or is_image_task):
                        logger.info("File sent successfully. Terminating loop to prevent duplicates.")
                        await message.answer("✅ 任务执行完毕。")
                        break
                else:
                    current_input = f"Tool {agent_name} FAILED: {result.errors}"
                continue

        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            await message.answer("❌ Orchestration Error.")
            break

async def cleanup_hanging_processes():
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            cmd = " ".join(proc.info['cmdline'] or [])
            if 'gemini' in cmd and '-p' in cmd:
                proc.kill()
    except: pass

async def main():
    await cleanup_hanging_processes()
    logger.info("Starting GenieBot...")
    scheduler_mgr.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
