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
        
        # 核心改进：开启任务合并，防止离线后疯狂补跑
        self.scheduler.add_job(
            self.pulse, 
            'interval', 
            minutes=10, 
            misfire_grace_time=60, 
            coalesce=True
        )
        self.scheduler.start()
        logger.info("Scheduler started. Pulse interval: 10m.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down (immediate).")

    async def pulse(self, is_manual: bool = False):
        """唤醒心跳 Agent 进行环境感知与决策"""
        if not self.admin_chat_id:
            logger.error("ADMIN_CHAT_ID not set.")
            return

        logger.info(f"System Pulse Triggered (Manual: {is_manual})")
        heartbeat = registry.get_agent("heartbeat")
        if heartbeat:
            await heartbeat.execute(self.admin_chat_id, is_manual=is_manual)
        else:
            logger.error("HeartbeatAgent not found in registry.")
