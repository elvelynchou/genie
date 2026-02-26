import os
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from agents.base import BaseAgent, AgentResult
import yt_dlp

class VideoDownloaderInput(BaseModel):
    url: str = Field(..., description="The URL of the video to download (supports X, Threads, Reddit, YouTube, etc.)")
    quality: str = Field("best", description="Preferred quality: best, worst, or a specific height like 720")

class VideoDownloaderAgent(BaseAgent):
    name = "video_downloader"
    description = "Downloads videos from social media platforms (X, YouTube, Reddit, Threads, etc.) and returns the local file path."
    input_schema = VideoDownloaderInput
    
    DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

    async def run(self, params: VideoDownloaderInput, chat_id: str) -> AgentResult:
        self.logger.info(f"Starting download for {params.url} requested by {chat_id}")
        
        # Ensure download dir exists
        os.makedirs(self.DOWNLOAD_DIR, exist_ok=True)
        
        # Use a simpler output template to avoid issues with complex titles
        output_template = os.path.join(self.DOWNLOAD_DIR, f"{chat_id}_%(id)s.%(ext)s")
        
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4', # Force mp4 for better compatibility
        }

        logs = [{"step": "initialization", "url": params.url}]

        try:
            loop = asyncio.get_event_loop()
            
            # Use a wrapper to get the final filename reliably
            def download_and_get_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(params.url, download=True)
                    # Use prepare_filename to get the expected path
                    actual_path = ydl.prepare_filename(info)
                    # If it was merged/post-processed, the extension might have changed to mp4
                    if not os.path.exists(actual_path):
                        base, _ = os.path.splitext(actual_path)
                        if os.path.exists(base + ".mp4"):
                            actual_path = base + ".mp4"
                    return info, actual_path

            info, file_path = await loop.run_in_executor(None, download_and_get_info)
            
            if not file_path or not os.path.exists(file_path):
                raise FileNotFoundError(f"Could not locate downloaded file at {file_path}")

            file_name = info.get('title', 'video')
            self.logger.info(f"Download successful: {file_path}")
            logs.append({"step": "download_complete", "file": file_path})
            
            return AgentResult(
                status="SUCCESS",
                data={
                    "file_path": file_path,
                    "title": file_name,
                    "id": info.get('id')
                },
                message=f"Successfully downloaded '{file_name}'.",
                logs=logs
            )

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return AgentResult(
                status="FAILED",
                errors=str(e),
                message=f"Failed to download video: {e}",
                logs=logs
            )

    def _download(self, url: str, opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)
