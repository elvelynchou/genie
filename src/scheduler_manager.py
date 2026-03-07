import asyncio
import logging
import os
import json
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agents.registry import registry

logger = logging.getLogger("genie.scheduler")

class SchedulerManager:
    def __init__(self, bot, redis_mgr, orchestrator, admin_chat_id: str):
        # Set timezone to Asia/Shanghai
        self.tz = pytz.timezone('Asia/Shanghai')
        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self.bot = bot
        self.redis_mgr = redis_mgr
        self.orchestrator = orchestrator
        self.admin_chat_id = admin_chat_id

    def start(self):
        if self.scheduler.running:
            logger.info("Scheduler is already running.")
            return
        # 北京时间每天 10:00 科技报告
        self.scheduler.add_job(self.daily_github_report, 'cron', hour=10, minute=0)
        # 每隔 30 分钟执行一次财经监控
        self.scheduler.add_job(self.half_hourly_finance_report, 'interval', minutes=30)
        # 北京时间每天凌晨 03:00 执行离线梦境 (记忆巩固)
        self.scheduler.add_job(self.nightly_dreaming_phase, 'cron', hour=3, minute=0)
        self.scheduler.start()
        logger.info("Scheduler started. Daily Jobs: GitHub (10:00), Dreaming (03:00). Interval: Finance (30m).")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shut down.")

    async def nightly_dreaming_phase(self):
        """凌晨执行离线梦境：巩固记忆碎片"""
        if not self.admin_chat_id: return
        logger.info("Starting nightly Dreaming Phase...")
        dreamer = registry.get_agent("dreamer")
        result = await dreamer.execute(self.admin_chat_id)
        if result.status == "SUCCESS":
            logger.info("Nightly dreaming complete.")
            # 只有在有新发现时才打扰用户（可选，也可设为完全静默）
            if "No new patterns" not in result.message:
                await self.bot.send_message(self.admin_chat_id, "🌙 **离线梦境报告**：昨夜我已完成记忆巩固，提炼了新的宏观策略与逻辑。")
        else:
            logger.error(f"Nightly dreaming failed: {result.errors}")

    async def _safe_send(self, text: str):
        """Safe message sending with chunking and robust error handling."""
        if not text: return
        
        CHUNK_SIZE = 3500
        chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        logger.info(f"Sending message in {len(chunks)} chunks...")
        
        for i, chunk in enumerate(chunks):
            try:
                await self.bot.send_message(self.admin_chat_id, chunk, parse_mode="Markdown")
                logger.info(f"Chunk {i+1}/{len(chunks)} sent successfully.")
            except Exception as e:
                logger.warning(f"Chunk {i+1} Markdown failed, retrying as plain text: {e}")
                try:
                    await self.bot.send_message(self.admin_chat_id, chunk, parse_mode=None)
                    logger.info(f"Chunk {i+1}/{len(chunks)} sent as plain text.")
                except Exception as e2:
                    logger.error(f"Chunk {i+1} failed completely: {e2}")
            await asyncio.sleep(0.5)

    async def half_hourly_finance_report(self, is_manual: bool = False):
        """执行半小时一次的财经自动监控"""
        if not self.admin_chat_id:
            logger.error("ADMIN_CHAT_ID not set.")
            return

        # 时间排除逻辑：仅针对非手动触发的任务执行静默
        if not is_manual:
            now = datetime.now(self.tz)
            current_time = now.time()
            start_silent = datetime.strptime("23:30", "%H:%M").time()
            end_silent = datetime.strptime("07:30", "%H:%M").time()

            if current_time >= start_silent or current_time <= end_silent:
                logger.info(f"Finance monitor suppressed during silent hours ({now.strftime('%H:%M')})")
                return

        logger.info(f"Starting finance monitoring (Manual: {is_manual})...")
        await self.bot.send_message(self.admin_chat_id, "🔍 正在启动自动财经监控...\n[阶段 1/2: 正在抓取多路源数据]")
        
        monitor = registry.get_agent("finance_monitor")
        
        try:
            # 运行重型任务
            result = await monitor.execute(self.admin_chat_id)
            
            if result.status == "SUCCESS":
                if "No new content" in result.message or "No significant new changes" in result.message:
                    logger.info("Finance monitor: No significant new changes.")
                    
                    # 即使无新大事，也列出产生的文件和当前现状
                    file_list = result.data.get("files", "未知")
                    status_quo = result.data.get("status_quo", "无摘要")
                    
                    msg = f"ℹ️ **财经监控完成**：对比上次抓取，暂无重大新增事件。\n\n"
                    msg += f"📂 **本次更新文件**：\n{file_list}\n\n"
                    msg += f"🔍 **当前市场现状回顾**：\n{status_quo[:2000]}"
                    
                    await self._safe_send(msg)
                else:
                    report_text = result.data.get("report", "")
                    file_list = result.data.get("files", "")
                    header = f"📊 **财经自动快报** (北京时间 {datetime.now(self.tz).strftime('%H:%M')}):\n\n"
                    footer = f"\n\n📂 **分源文件列表**：\n{file_list}"
                    await self._safe_send(header + report_text + footer)
            else:
                logger.error(f"Scheduled finance monitor failed: {result.errors}")
                await self.bot.send_message(self.admin_chat_id, f"❌ 财经监控执行失败: {result.errors[:500]}")
        except Exception as e:
            logger.error(f"Finance report task crashed: {e}", exc_info=True)

    async def daily_github_report(self, send_raw_files: bool = False):
        """执行每日科技趋势分析流"""
        if not self.admin_chat_id:
            logger.error("ADMIN_CHAT_ID not set.")
            return

        logger.info("Starting daily tech trend report task...")
        
        # 核心进化：从 JSON 加载科技源
        config_path = "/etc/myapp/genie/src/agents/analyzer/trend_sources.json"
        tasks = []
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    tasks = config.get("tech_sources", [])
            except Exception as e:
                logger.error(f"Failed to load tech sources from {config_path}: {e}")
        
        if not tasks:
            # 兜底默认源
            tasks = [
                {"name": "Global", "url": "https://github.com/trending"},
                {"name": "AI Agent", "url": "https://github.com/search?q=ai+agent&type=repositories&s=stars&o=desc"}
            ]

        await self.bot.send_message(self.admin_chat_id, f"🌅 正在从 {len(tasks)} 个源获取今日科技动态...")

        extractor = registry.get_agent("link_content_extractor")
        analyzer = registry.get_agent("trend_analyzer")
        file_sender = registry.get_agent("file_sender")
        
        combined_text = ""
        raw_file_paths = []

        # 1. 抓取 (Extract)
        for task in tasks:
            res = await extractor.execute(self.admin_chat_id, url=task["url"], save_to_file=True)
            if res.status == "SUCCESS":
                combined_text += f"\n--- Source: {task['name']} ---\n{res.data.get('content', '')[:3000]}"
                raw_file_paths.append(res.data.get("file_path"))

        # 2. 分析 (Analyze) - 这里默认做 General 和 Evolution 两份分析
        # 你可以根据需要调整是否要做 Social 分析
        targets = ["general", "evolution"]
        
        for target in targets:
            analysis_res = await analyzer.execute(self.admin_chat_id, raw_contents=combined_text, target=target)
            if analysis_res.status == "SUCCESS":
                report_text = analysis_res.data.get("analysis", "")
                report_file = analysis_res.data.get("file_path")
                
                # 发送文字总结
                title = "📑 **每日趋势总结**" if target == "general" else "🚀 **项目进化建议**"
                await self._safe_send(f"{title}\n\n{report_text}")
                
                # 记录分析结果文件到 Redis state，但不立即发送，除非需要备份
                # await file_sender.execute(self.admin_chat_id, file_path=report_file, delete_after_send=False)

        # 3. 只有当明确要求时，才发送 3 个 MD 原文文件
        if send_raw_files:
            for path in raw_file_paths:
                await file_sender.execute(self.admin_chat_id, file_path=path, delete_after_send=True)
        else:
            # 如果不发送，可以选择清理掉（或者留着，由系统定期清理）
            pass

        logger.info("Daily report flow complete.")
