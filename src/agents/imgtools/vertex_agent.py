import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from google import genai
from google.genai import types

class VertexGenInput(BaseModel):
    prompt_or_template: str = Field(..., description="The prompt string or the name of a template JSON.")
    reference_image: Optional[str] = Field(None, description="Local path to the reference image.")

class VertexGenAgent(BaseAgent):
    name = "vertex_generator"
    description = "Handles image generation using Google Vertex AI (gemini-3.1-flash-image-preview). Supports templates and reference images."
    input_schema = VertexGenInput
    
    PROJECT_ROOT = "/etc/myapp/genie"
    TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "src/agents/imgtools/genimgtemplate")
    CHAR_DIR = os.path.join(PROJECT_ROOT, "src/agents/imgtools/characters")
    DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "img_output")

    def __init__(self):
        super().__init__()
        # We read the key dynamically in run() or during init
        self.api_key = os.environ.get("GOOGLE_VERTEX_API_KEY")
        if self.api_key:
            self.client = genai.Client(vertexai=True, api_key=self.api_key)
        else:
            self.client = None

    async def run(self, params: VertexGenInput, chat_id: str) -> AgentResult:
        # Check API key again in case it was loaded late
        api_key = os.environ.get("GOOGLE_VERTEX_API_KEY")
        if not self.client and api_key:
            self.client = genai.Client(vertexai=True, api_key=api_key)
            
        if not self.client:
            return AgentResult(status="FAILED", message="GOOGLE_VERTEX_API_KEY not set in .env")

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

        # 2. Build Contents Array
        contents_parts = []
        
        if params.reference_image:
            ref_path = params.reference_image
            if "/" not in ref_path:
                ref_path = os.path.join(self.CHAR_DIR, ref_path)
            
            if os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    img_bytes = f.read()
                contents_parts.append(
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                )
                logs.append({"step": "reference_image_loaded", "path": ref_path})
            else:
                return AgentResult(status="FAILED", message=f"Reference image not found: {ref_path}")

        contents_parts.append(types.Part.from_text(text=final_prompt))

        contents = [types.Content(role="user", parts=contents_parts)]

        # 3. Configure generation based on your example
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=32768,
            response_modalities=["TEXT", "IMAGE"],
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            image_config=types.ImageConfig(
                aspect_ratio="1:1",
                output_mime_type="image/png",
            ),
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH",
            )
        )

        try:
            self.logger.info(f"Calling Vertex AI for {chat_id}...")
            from google.genai.errors import ClientError

            response = None
            max_retries = 3
            base_delay = 10 # 初始等待 10 秒
            
            for attempt in range(max_retries):
                try:
                    # 使用 async client 进行非阻塞调用
                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model="gemini-3.1-flash-image-preview",
                            contents=contents,
                            config=generate_content_config,
                        ),
                        timeout=120.0
                    )
                    break # 如果成功，跳出重试循环
                except ClientError as e:
                    if e.code == 429 and attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt) # 指数退避: 10s, 20s, 40s
                        self.logger.warning(f"Vertex AI rate limited (429). Retrying in {sleep_time}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(sleep_time)
                    else:
                        # 非 429 错误，或重试次数耗尽，向上抛出
                        raise e
                except asyncio.TimeoutError:
                    return AgentResult(status="FAILED", errors="Vertex AI image generation timed out after 120 seconds.", logs=logs)

            if not response:
                return AgentResult(status="FAILED", errors="Failed to generate image after retries.", logs=logs)

            # Extract image from response parts
            image_bytes = None
            text_response = ""
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_bytes = part.inline_data.data
                    elif part.text:
                        text_response += part.text + "\n"

            if image_bytes:
                os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
                date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"vertex_{date_str}_{chat_id}.png"
                file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
                
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                
                logs.append({"step": "image_saved", "path": file_path})
                return AgentResult(
                    status="SUCCESS",
                    data={"file_path": file_path, "text_response": text_response.strip()},
                    message="Vertex AI generation complete.",
                    logs=logs,
                    next_steps=["file_sender"]
                )
            else:
                return AgentResult(status="FAILED", errors="No image data returned.", message=text_response.strip(), logs=logs)

        except Exception as e:
            self.logger.error(f"Vertex AI failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
