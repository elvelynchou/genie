import os
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
from google.genai import types

class ImageOCRInput(BaseModel):
    image_path: str = Field(..., description="The local path to the image file to be analyzed.")
    language: str = Field("auto", description="Preferred language for OCR.")

class ImageOCRAgent(BaseAgent):
    name = "image_ocr"
    description = "Extracts text from an image using Gemini's multimodal capabilities. Good for documents, signs, or screenshots."
    input_schema = ImageOCRInput

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator

    async def run(self, params: ImageOCRInput, chat_id: str) -> AgentResult:
        if not self.orchestrator:
            return AgentResult(status="FAILED", message="Orchestrator not provided.")

        if not os.path.exists(params.image_path):
            return AgentResult(status="FAILED", message=f"Image file not found: {params.image_path}")

        logs = [{"step": "initialization", "path": params.image_path}]

        try:
            # 1. Read Image Data
            with open(params.image_path, "rb") as f:
                image_data = f.read()
            
            # 2. Prepare Multimodal Request
            # Note: We use the orchestrator's client directly for multimodal calls
            client = self.orchestrator.client
            model_name = self.orchestrator.model_name
            
            prompt = "Please extract all text from this image. Format the output clearly. If it's a document, maintain the structure."
            if params.language != "auto":
                prompt += f" Focus on {params.language} text."

            loop = asyncio.get_event_loop()
            
            def call_gemini():
                return client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(text=prompt),
                                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_data))
                            ]
                        )
                    ]
                )

            response = await loop.run_in_executor(None, call_gemini)
            result_text = response.text.strip()
            
            logs.append({"step": "ocr_complete", "text_length": len(result_text)})

            return AgentResult(
                status="SUCCESS",
                data={"extracted_text": result_text, "image_path": params.image_path},
                message="Text extraction successful.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"OCR failed: {e}", exc_info=True)
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
