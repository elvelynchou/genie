from fastmcp import FastMCP
import os
import yt_dlp
import json

mcp = FastMCP("VideoDownloader")
DOWNLOAD_DIR = "/etc/myapp/genie/downloads"

@mcp.tool()
def download_video(url: str) -> str:
    """
    Downloads videos from platforms like X (Twitter), YouTube, Threads, and Reddit.
    :param url: The URL of the video to download.
    :return: JSON string with status and file_path.
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Simple ID-based naming
    output_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            
            # Correction for post-processing merge
            if not os.path.exists(path):
                base, _ = os.path.splitext(path)
                if os.path.exists(base + ".mp4"):
                    path = base + ".mp4"
            
            if os.path.exists(path):
                return json.dumps({"status": "SUCCESS", "file_path": path})
            else:
                return json.dumps({"status": "ERROR", "message": "File not found after download."})
                
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e)})

if __name__ == "__main__":
    mcp.run()
