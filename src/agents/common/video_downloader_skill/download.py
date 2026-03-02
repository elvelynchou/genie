import os
import sys
import json
import yt_dlp

def download(url):
    download_dir = "/etc/myapp/genie/downloads"
    os.makedirs(download_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': os.path.join(download_dir, "%(id)s.%(ext)s"),
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
            if not os.path.exists(path):
                base, _ = os.path.splitext(path)
                if os.path.exists(base + ".mp4"):
                    path = base + ".mp4"
            
            return {"status": "SUCCESS", "file_path": path}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        sys.exit(1)
    
    result = download(sys.argv[1])
    print(json.dumps(result))
