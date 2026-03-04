import asyncio
import logging
import os
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
        # 北京时间每天 10:00
        self.scheduler.add_job(self.daily_github_report, 'cron', hour=10, minute=0)
        self.scheduler.start()
        logger.info("Scheduler started. Daily GitHub report set for 10:00 AM (Beijing Time).")

    async def daily_github_report(self, send_raw_files: bool = False):
        """执行每日 GitHub 趋势分析流"""
        if not self.admin_chat_id:
            logger.error("ADMIN_CHAT_ID not set.")
            return

        logger.info("Starting daily GitHub report task...")
        await self.bot.send_message(self.admin_chat_id, "🌅 正在获取 GitHub 今日动态...")

        tasks = [
            {"name": "Global", "url": "https://github.com/trending"},
            {"name": "Skills", "url": "https://github.com/search?q=skills&type=repositories&s=stars&o=desc"},
            {"name": "AI Agent", "url": "https://github.com/search?q=ai+agent&type=repositories&s=stars&o=desc"}
        ]

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
                await self.bot.send_message(self.admin_chat_id, f"{title}\n\n{report_text}")
                
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
