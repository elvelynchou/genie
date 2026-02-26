import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult

class FileSenderInput(BaseModel):
    file_path: str = Field(..., description="The absolute path to the local file to be sent.")
    caption: Optional[str] = Field(None, description="Optional caption for the file/video/image.")
    delete_after_send: bool = Field(True, description="Whether to delete the local file after successful transmission.")
    as_document: bool = Field(False, description="Force sending as a document even if it's a photo or video.")

class FileSenderAgent(BaseAgent):
    name = "file_sender"
    description = "Sends local files to the user via Telegram. Automatically detects file type (photo, video, document)."
    input_schema = FileSenderInput

    def __init__(self, bot_instance=None):
        super().__init__()
        # We need the bot instance to send files. 
        # In a real app, this would be injected or accessed via a global registry.
        self.bot = bot_instance

    async def run(self, params: FileSenderInput, chat_id: str) -> AgentResult:
        if not self.bot:
            return AgentResult(status="FAILED", message="Bot instance not initialized in FileSenderAgent.")

        if not os.path.exists(params.file_path):
            return AgentResult(status="FAILED", message=f"File not found: {params.file_path}")

        logs = [{"step": "file_check", "path": params.file_path, "exists": True}]
        ext = os.path.splitext(params.file_path)[1].lower()
        
        try:
            from aiogram.types import FSInputFile
            file = FSInputFile(params.file_path)
            
            # Logic to choose the correct aiogram method
            if params.as_document:
                await self.bot.send_document(chat_id, file, caption=params.caption)
                logs.append({"step": "send", "method": "send_document"})
            elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
                await self.bot.send_photo(chat_id, file, caption=params.caption)
                logs.append({"step": "send", "method": "send_photo"})
            elif ext in ['.mp4', '.mov', '.mkv', '.avi']:
                await self.bot.send_video(chat_id, file, caption=params.caption)
                logs.append({"step": "send", "method": "send_video"})
            elif ext in ['.mp3', '.m4a', '.ogg']:
                await self.bot.send_audio(chat_id, file, caption=params.caption)
                logs.append({"step": "send", "method": "send_audio"})
            else:
                await self.bot.send_document(chat_id, file, caption=params.caption)
                logs.append({"step": "send", "method": "send_document"})

            # Optional cleanup
            if params.delete_after_send:
                os.remove(params.file_path)
                logs.append({"step": "cleanup", "status": "deleted"})

            return AgentResult(
                status="SUCCESS",
                data={"path": params.file_path, "action": "sent"},
                message=f"File successfully sent to user.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Failed to send file: {e}")
            return AgentResult(
                status="FAILED",
                errors=str(e),
                message=f"Failed to send file via Telegram: {e}",
                logs=logs
            )
