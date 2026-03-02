---
name: video-downloader
description: "Downloads videos from platforms like X (Twitter), YouTube, Threads, and Reddit."
tools:
  - name: download_video
    description: "Download a video from a URL. Returns the local path to the file."
    path: ./download.py
    parameters:
      type: object
      properties:
        url:
          type: string
          description: "The full URL of the video to download."
      required: [url]
---

# Video Downloader Skill

This skill allows Genie to download media files directly from social platforms.

## Usage
When a user provides a video link, invoke the `download_video` tool.
Once the JSON response is received, notify the user of the `file_path`.
