---
name: x-tweet-fetcher
description: "Fetch content and stats from X (Twitter) and save to Markdown. Use this when the user wants to analyze or archive a tweet."
tools:
  - name: fetch_x_tweet
    description: "Fetch content, stats, and generate a Markdown file in downloads/. Returns the local file path."
    path: ./fetch.py
    parameters:
      type: object
      properties:
        url:
          type: string
          description: "The full X tweet URL."
      required: [url]
---

# X Social Intelligence Skill (Enhanced)

Fetch tweet data and archive it as Markdown.

## Usage
1. Provide the URL.
2. The tool returns text and a `file_path`.
3. Inform the user of the analysis and file location.
