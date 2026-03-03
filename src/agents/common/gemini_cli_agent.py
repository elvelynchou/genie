import asyncio
import os
import subprocess
import logging
import re
import shlex
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
    description = "A powerful system-level agent using Gemini CLI. IMPORTANT: If you encounter 'Tool execution denied by policy', set 'yolo=True'."
    input_schema = GeminiCLIInput

    PROJECT_ROOT = "/etc/myapp/genie"
    BASE_ENV = {
        "HOME": "/home/elvelyn",
        "USER": "elvelyn",
        "PATH": f"{PROJECT_ROOT}/venv/bin:/home/elvelyn/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "TERM": "xterm-256color",
        "SHELL": "/bin/bash",
        "PYTHONPATH": f"{PROJECT_ROOT}/src:{PROJECT_ROOT}",
        "VIRTUAL_ENV": f"{PROJECT_ROOT}/venv",
        "REDIS_URL": "redis://localhost:6379/0"
    }

    async def run(self, params: GeminiCLIInput, chat_id: str) -> AgentResult:
        if params.action == "list":
            return await self._get_capabilities()
        if params.action == "debug":
            return await self._debug_env()
        if not params.prompt:
            return AgentResult(status="FAILED", message="Prompt required.")
        return await self._execute_command(params)

    async def _run_raw_cmd(self, cmd_parts: List[str]) -> str:
        """Runs a command with venv activation and proper argument escaping."""
        full_env = os.environ.copy()
        full_env.update(self.BASE_ENV)
        
        # Build the command string safely
        # We use a single bash command but escape the internal gemini command properly
        inner_cmd = " ".join([shlex.quote(p) for p in cmd_parts])
        activation = f"source {self.PROJECT_ROOT}/venv/bin/activate"
        full_bash_cmd = f"{activation} && {inner_cmd}"
        
        proc = await asyncio.create_subprocess_shell(
            full_bash_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=self.PROJECT_ROOT,
            executable="/bin/bash" # Ensure we use bash for 'source'
        )
        
        try:
            # Hard timeout of 5 minutes for any CLI task
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            combined = stdout.decode() + stderr.decode()
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            return ansi_escape.sub('', combined).strip()
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except:
                pass
            return "ERROR: Task timed out after 300s."

    async def _execute_command(self, params: GeminiCLIInput) -> AgentResult:
        cmd_parts = ["gemini", "-p", params.prompt]
        if params.skill:
            cmd_parts.extend(["--skill", params.skill])
        if params.yolo:
            cmd_parts.append("--yolo")
        
        output = await self._run_raw_cmd(cmd_parts)
        
        # Extract file paths if present (downloads, img_output, nanobanana-output)
        path_matches = re.findall(r"(/[a-zA-Z0-9._/-]+/(?:downloads|img_output|nanobanana-output)/[a-zA-Z0-9._/-]+(?:png|jpg|jpeg|mp4))", output)
        file_paths = list(dict.fromkeys(path_matches)) # remove duplicates
        
        result_data = {"output": output}
        if file_paths:
            result_data["file_path"] = file_paths[0]
            result_data["all_paths"] = file_paths

        return AgentResult(status="SUCCESS", data=result_data, message="Execution complete.")

    async def _get_capabilities(self) -> AgentResult:
        await self._run_raw_cmd(["gemini", "-v"])
        skills_raw = await self._run_raw_cmd(["gemini", "skills", "list"])
        mcps_raw = await self._run_raw_cmd(["gemini", "mcp", "list"])
        exts_raw = await self._run_raw_cmd(["gemini", "extensions", "list"])

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
        debug_info = await self._run_raw_cmd(["env"])
        return AgentResult(status="SUCCESS", message=f"Debug Info:\n{debug_info}")
