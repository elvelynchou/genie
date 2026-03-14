import os
import psutil
import asyncio
import logging
import socket
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from redis_manager import RedisManager

class SysCheckInput(BaseModel):
    verbose: bool = Field(False, description="Whether to include detailed metrics.")

class SysCheckAgent(BaseAgent):
    name = "sys_check"
    description = "System Health Check Agent. Monitors CPU, Memory, Redis, and API connectivity."
    input_schema = SysCheckInput

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: SysCheckInput, chat_id: str) -> AgentResult:
        self.logger.info("Running system health check...")
        
        health_data = {}
        
        # 1. CPU & Memory
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        health_data["system"] = {
            "cpu_usage": f"{cpu_usage}%",
            "memory_usage": f"{memory.percent}%",
            "memory_available": f"{memory.available / (1024**3):.2f} GB"
        }

        # 2. Redis Connectivity
        redis_status = "DOWN"
        try:
            # We'll try to connect to the default redis
            r_mgr = RedisManager(db=0)
            # Simple ping test (implicitly done by most operations, but we can check connection)
            # Actually, let's just check if the port is open as a basic test
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                if s.connect_ex(('localhost', 6379)) == 0:
                    redis_status = "UP"
        except:
            pass
        health_data["redis"] = redis_status

        # 3. Gemini API Check
        gemini_status = "UNKNOWN"
        if self.orchestrator:
            try:
                start_time = time.time()
                # Use a very small prompt
                await asyncio.get_event_loop().run_in_executor(None, lambda: self.orchestrator.chat("ping", []))
                latency = time.time() - start_time
                gemini_status = f"UP ({latency:.2f}s)"
            except Exception as e:
                gemini_status = f"DOWN: {str(e)}"
        health_data["gemini_api"] = gemini_status

        # 4. Storage
        usage = psutil.disk_usage('/')
        health_data["storage"] = {
            "percent": f"{usage.percent}%",
            "free": f"{usage.free / (1024**3):.2f} GB"
        }

        # Determine overall status
        status = "SUCCESS"
        if redis_status == "DOWN" or "DOWN" in gemini_status:
            status = "FAILED"
            message = "⚠️ **System Health Alert**: Critical components are DOWN!"
        else:
            message = "✅ **System Health Report**: All systems operational."

        if params.verbose:
            report = f"{message}\n\n"
            report += f"💻 **CPU**: {health_data['system']['cpu_usage']}\n"
            report += f"🧠 **Memory**: {health_data['system']['memory_usage']} ({health_data['system']['memory_available']} available)\n"
            report += f"🗄️ **Redis**: {health_data['redis']}\n"
            report += f"✨ **Gemini**: {health_data['gemini_api']}\n"
            report += f"💾 **Storage**: {health_data['storage']['percent']} ({health_data['storage']['free']} free)"
        else:
            report = message

        return AgentResult(
            status=status,
            data=health_data,
            message=report
        )
