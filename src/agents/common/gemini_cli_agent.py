import asyncio
import os
import subprocess
import logging
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class GeminiCLIInput(BaseModel):
    prompt: Optional[str] = Field(None, description="The prompt or instruction to pass to the Gemini CLI.")
    action: str = Field("execute", description="The action to perform: 'execute', 'list', or 'debug'.")
    skill: Optional[str] = Field(None, description="Optional name of a pre-defined skill to use.")
    yolo: bool = Field(False, description="Whether to run in --yolo mode.")

class GeminiCLIAgent(BaseAgent):
    name = "gemini_cli_executor"
    description = "A powerful system-level agent using Gemini CLI. Use action='list' to see extensions/MCPs. Use action='execute' with yolo=True for actions."
    input_schema = GeminiCLIInput

    # Shared environment for all calls
    BASE_ENV = {
        "HOME": "/home/elvelyn",
        "USER": "elvelyn",
        "PATH": "/home/elvelyn/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin",
        "TERM": "xterm-256color",
        "SHELL": "/bin/bash"
    }

    async def run(self, params: GeminiCLIInput, chat_id: str) -> AgentResult:
        if params.action == "list":
            return await self._get_capabilities()
        
        if params.action == "debug":
            return await self._debug_env()

        if not params.prompt:
            return AgentResult(status="FAILED", message="Prompt required.")

        return await self._execute_command(params)

    async def _run_raw_cmd(self, cmd_str: str) -> str:
        """Runs a command through bash -c with a clean environment."""
        full_env = os.environ.copy()
        full_env.update(self.BASE_ENV)
        
        # Use bash -c to ensure aliases and path are respected
        proc = await asyncio.create_subprocess_shell(
            f"bash -c '{cmd_str}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env
        )
        stdout, stderr = await proc.communicate()
        
        # Merge stdout and stderr for listing commands as they sometimes output to stderr
        combined = stdout.decode() + stderr.decode()
        
        # Clean ANSI codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', combined).strip()

    async def _execute_command(self, params: GeminiCLIInput) -> AgentResult:
        cmd = f"gemini -p \"{params.prompt}\""
        if params.skill: cmd += f" --skill {params.skill}"
        if params.yolo: cmd += " --yolo"
        
        output = await self._run_raw_cmd(cmd)
        return AgentResult(status="SUCCESS", data={"output": output}, message="Execution complete.")

    async def _get_capabilities(self) -> AgentResult:
        # Use more descriptive commands
        skills_raw = await self._run_raw_cmd("gemini skills list")
        mcps_raw = await self._run_raw_cmd("gemini mcp list")
        exts_raw = await self._run_raw_cmd("gemini extensions list")

        report = f"📋 **Gemini CLI 系统能力清单**\n\n"
        report += f"✅ **[Extensions]**:\n{exts_raw or 'None'}\n\n"
        report += f"🛠 **[Agent Skills]**:\n{skills_raw or 'None'}\n\n"
        report += f"🔌 **[MCP Servers]**:\n{mcps_raw or 'None'}"

        return AgentResult(
            status="SUCCESS",
            data={"skills": skills_raw, "mcps": mcps_raw, "extensions": exts_raw},
            message=report
        )

    async def _debug_env(self) -> AgentResult:
        debug_info = await self._run_raw_cmd("env && which gemini && gemini -v")
        return AgentResult(status="SUCCESS", message=f"Debug Info:\n{debug_info}")
