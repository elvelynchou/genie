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
        
        # 核心简化：每 10 分钟唤醒一次“赛博脉搏”
        # 由 HeartbeatAgent 根据 HEARTBEAT.md 自行决定执行什么
        self.scheduler.add_job(self.pulse, 'interval', minutes=10)
        self.scheduler.start()
        logger.info("Scheduler started. Pulse interval: 10m.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shut down.")

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
