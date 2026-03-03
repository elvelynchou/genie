import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class TemplateCreatorInput(BaseModel):
    template_name: str = Field(..., description="The unique name for the new template (e.g., 'cinematic_me').")
    structured_prompt: Dict[str, Any] = Field(..., description="The JSON object received from prompt_inverse.")
    identity_lock_prompt: str = Field(
        "Use the uploaded picture as a reference (Strict identity lock, the face must match the attached reference photo exactly, preserving facial structure, skin tone, expression, and hairstyle (same haircut and hair texture)",
        description="The strict instruction for maintaining identity."
    )

class TemplateCreatorAgent(BaseAgent):
    name = "image_template_creator"
    description = "Converts a structured prompt into a reusable generation template with identity locking rules."
    input_schema = TemplateCreatorInput
    
    TEMPLATE_DIR = "/etc/myapp/genie/src/agents/imgtools/genimgtemplate"

    async def run(self, params: TemplateCreatorInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Creating new image template: {params.template_name}")
        
        os.makedirs(self.TEMPLATE_DIR, exist_ok=True)
        file_path = os.path.join(self.TEMPLATE_DIR, f"{params.template_name}.json")

        logs = [{"step": "initialization", "name": params.template_name}]

        try:
            # Enforce face and hair consistency directly in the visual details
            visual_details = params.structured_prompt.copy()
            visual_details["face"] = "The face, facial structure, features, skin tone, and expression must match the reference image exactly."
            visual_details["hair"] = "The hair color, length, style, and texture must match the reference image exactly."

            # 1. Merge logic
            # We wrap the visual details and add the core generation instructions
            final_template = {
                "template_metadata": {
                    "name": params.template_name,
                    "created_at": datetime.now().isoformat(),
                    "chat_id": chat_id
                },
                "core_instructions": params.identity_lock_prompt,
                "visual_details": visual_details,
                "usage_hint": f"Pass this template to any image generator agent with an image reference."
            }

            # 2. Save to disk
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(final_template, f, indent=2, ensure_ascii=False)
            
            logs.append({"step": "template_saved", "path": file_path})

            return AgentResult(
                status="SUCCESS",
                data={"template_path": file_path, "template_content": final_template},
                message=f"Template '{params.template_name}' has been created successfully in {file_path}.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Template creation failed: {e}")
            return AgentResult(status="FAILED", errors=str(e), logs=logs)
