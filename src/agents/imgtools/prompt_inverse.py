import os
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from google.genai import types

class PromptInverseInput(BaseModel):
    image_path: str = Field(..., description="The local path to the image to analyze.")
    target_engine: str = Field("nanobanana", description="The target image generator (nanobanana, vertex, modelscope).")

class PromptInverseAgent(BaseAgent):
    name = "prompt_inverse"
    description = "Analyzes an image and generates a structured JSON prompt to recreate it. Includes details on subject, clothing, environment, style, etc."
    input_schema = PromptInverseInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads/prompts"

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: PromptInverseInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator not provided.")

        if not os.path.exists(params.image_path):
            return AgentResult(status="FAILED", message=f"Image file not found: {params.image_path}")

        logs = [{"step": "initialization", "path": params.image_path}]

        try:
            with open(params.image_path, "rb") as f:
                image_data = f.read()
            
            prompt_instruction = """
            Extract all visual details from this image and convert them into a clean, well-structured JSON prompt. 
            Include the following sections:
            - subject
            - clothing
            - hair
            - face
            - accessories
            - posing
            - environment
            - lighting
            - camera
            - style
            
            Return ONLY the JSON object. Do not include any markdown wrapper or explanation.
            """

            loop = asyncio.get_event_loop()
            def call_gemini():
                return self.orchestrator.client.models.generate_content(
                    model=self.orchestrator.model_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(text=prompt_instruction),
                                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_data))
                            ]
                        )
                    ]
                )

            response = await loop.run_in_executor(None, call_gemini)
            raw_json = response.text.strip()
            
            # Clean up potential markdown wrappers
            if raw_json.startswith("```json"):
                raw_json = raw_json.split("```json")[1].split("```")[0].strip()
            elif raw_json.startswith("```"):
                raw_json = raw_json.split("```")[1].split("```")[0].strip()

            # 2. Save to JSON file
            os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"prompt_{date_str}_{chat_id}.json"
            file_path = os.path.join(self.DOWNLOAD_DIR, file_name)
            
            try:
                # Validate JSON format
                parsed_json = json.loads(raw_json)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)
            except Exception as je:
                self.logger.warning(f"Failed to parse JSON, saving as raw text: {je}")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(raw_json)
            
            logs.append({"step": "analysis_complete", "file": file_path})

            return AgentResult(
                status="SUCCESS",
                data={
                    "structured_prompt": raw_json, 
                    "file_path": file_path,
                    "original_image": params.image_path
                },
                message=f"Structured JSON prompt generated and saved to {file_path}.",
                logs=logs,
                next_steps=["file_sender"]
            )

        except Exception as e:
            self.logger.error(f"Prompt inversion failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
