import os
import json
import logging
import asyncio
import base64
import httpx
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class ModelScopeInput(BaseModel):
    prompt_or_template: str = Field(..., description="The prompt string or the name of a template JSON.")
    reference_image: str = Field(..., description="Local path to the reference image (Required for Image-to-Image).")

class ModelScopeGenAgent(BaseAgent):
    name = "modelscope_generator"
    description = "Handles image-to-image generation using ModelScope API (Qwen-Image-Edit). Requires a reference image."
    input_schema = ModelScopeInput
    
    PROJECT_ROOT = "/etc/myapp/genie"
    TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "src/agents/imgtools/genimgtemplate")
    CHAR_DIR = os.path.join(PROJECT_ROOT, "src/agents/imgtools/characters")
    DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "img_output")

    def __init__(self):
        super().__init__()

    async def run(self, params: ModelScopeInput, chat_id: str) -> AgentResult:
        api_key = os.environ.get("MODELSCOPE_API_KEY")
        if not api_key:
            return AgentResult(status="FAILED", message="MODELSCOPE_API_KEY not set in .env")

        logs = [{"step": "initialization", "prompt": params.prompt_or_template}]
        
        # 1. Resolve Prompt
        final_prompt = params.prompt_or_template
        template_path = os.path.join(self.TEMPLATE_DIR, f"{params.prompt_or_template}.json")
        
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                tpl = json.load(f)
                details = tpl.get("visual_details", {})
                instr = tpl.get("core_instructions", "")
                final_prompt = f"{instr}\nVisual Details: {json.dumps(details)}"
                logs.append({"step": "template_loaded", "name": params.prompt_or_template})

        # 2. Resolve Reference Image
        ref_path = params.reference_image
        if "/" not in ref_path:
            ref_path = os.path.join(self.CHAR_DIR, ref_path)
        
        if not os.path.exists(ref_path):
            return AgentResult(status="FAILED", message=f"Reference image not found: {ref_path}")

        logs.append({"step": "reference_image_loaded", "path": ref_path})

        # Encode image to base64
        with open(ref_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Determine mime type (rough guess based on extension)
        ext = os.path.splitext(ref_path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        base64_url = f"data:{mime_type};base64,{encoded_string}"

        # 3. Call ModelScope API
        base_url = 'https://api-inference.modelscope.cn/'
        common_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": 'Qwen/Qwen-Image-Edit-2511', 
            "prompt": final_prompt,
            "image_url": [base64_url]
        }

        try:
            self.logger.info(f"Submitting task to ModelScope for {chat_id}...")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{base_url}v1/images/generations",
                    headers={**common_headers, "X-ModelScope-Async-Mode": "true"},
                    json=payload
                )
                
                if response.status_code != 200:
                    return AgentResult(status="FAILED", errors=f"HTTP {response.status_code}: {response.text}", logs=logs)
                
                task_id = response.json().get("task_id")
                if not task_id:
                    return AgentResult(status="FAILED", errors="No task_id received from ModelScope.", logs=logs)
                
                logs.append({"step": "task_submitted", "task_id": task_id})
                self.logger.info(f"ModelScope Task ID: {task_id}. Polling for results...")

                # 4. Poll for results
                max_polls = 60 # 5 mins max
                for _ in range(max_polls):
                    await asyncio.sleep(5)
                    poll_resp = await client.get(
                        f"{base_url}v1/tasks/{task_id}",
                        headers={**common_headers, "X-ModelScope-Task-Type": "image_generation"},
                    )
                    
                    if poll_resp.status_code != 200:
                        continue
                        
                    data = poll_resp.json()
                    status = data.get("task_status")
                    
                    self.logger.info(f"ModelScope Task {task_id} status: {status}")

                    if status == "SUCCEED":
                        img_urls = data.get("output_images", [])
                        if not img_urls:
                            return AgentResult(status="FAILED", errors="Task succeeded but no output images found.", logs=logs)
                            
                        # Download the generated image
                        img_url = img_urls[0]
                        img_response = await client.get(img_url, timeout=30.0)
                        
                        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
                        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        file_name = f"modelscope_{date_str}_{chat_id}.jpg"
                        file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
                        
                        with open(file_path, "wb") as f:
                            f.write(img_response.content)
                            
                        logs.append({"step": "image_saved", "path": file_path})
                        
                        return AgentResult(
                            status="SUCCESS",
                            data={"file_path": file_path},
                            message="ModelScope generation complete.",
                            logs=logs,
                            next_steps=["file_sender"]
                        )
                    elif status == "FAILED":
                        return AgentResult(status="FAILED", errors=f"ModelScope task failed: {data}", logs=logs)
                
                return AgentResult(status="FAILED", errors="Polling timed out after 5 minutes.", logs=logs)

        except Exception as e:
            self.logger.error(f"ModelScope API failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
