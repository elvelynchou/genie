import sys
import json
import httpx
import re
import os
from datetime import datetime

def parse_tweet_url(url: str):
    pattern = r"(?:x|twitter)\.com/([^/]+)/status/(\d+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid X/Twitter URL format")
    return match.group(1), match.group(2)

def fetch_tweet(url):
    download_dir = "/etc/myapp/genie/downloads"
    os.makedirs(download_dir, exist_ok=True)
    
    try:
        username, tweet_id = parse_tweet_url(url)
        api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(api_url, headers={"User-Agent": "GenieBot/1.0"})
            if response.status_code != 200:
                return {"status": "ERROR", "message": f"HTTP {response.status_code}"}
            
            data = response.json()
            tweet = data.get("tweet", {})
            content = tweet.get("text", "")
            author = tweet.get("author", {}).get("name", "Unknown")
            
            # 核心改进：生成 Markdown 文件
            date_str = datetime.now().strftime("%Y%m%d")
            file_name = f"xfetcher_{date_str}_{tweet_id}.md"
            file_path = os.path.join(download_dir, file_name)
            
            md_content = f"# Tweet from {author}\n\n"
            md_content += f"**URL**: {url}\n"
            md_content += f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            md_content += f"## Content\n{content}\n\n"
            md_content += f"## Stats\n- Likes: {tweet.get('likes', 0)}\n- Retweets: {tweet.get('retweets', 0)}\n"
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            
            return {
                "status": "SUCCESS",
                "text": content,
                "author": author,
                "file_path": file_path,
                "message": f"Tweet fetched and saved to {file_path}"
            }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL"}))
        sys.exit(1)
    print(json.dumps(fetch_tweet(sys.argv[1])))
