# Tech Stack: GenieBot (Bridge-03)

## Core Language
- **Python:** Primary language. Implementation requires strict type hints and asynchronous patterns (`async/await`).

## Bot & Orchestration
- **aiogram 3.x:** Asynchronous framework for Telegram Bot interaction.
- **google-genai:** SDK for Gemini Pro integration, supporting function calling and multi-step reasoning.

## Memory & Retrieval
- **Redis Stack:** Used for L1 (History), L2 (Short-term context), and L3 (Long-term RAG).
- **RediSearch:** Enabled on DB 0 for vector similarity search and entity-based graph retrieval.
- **gemini-embedding-001:** Model used for generating semantic embeddings.

## Web Automation & Stealth
- **Camoufox:** Primary high-stealth browser engine based on Firefox.
- **Nodriver:** Secondary engine for Chromium-based automation.
- **BrowserForge:** Fingerprint and header generation for bypassing bot detection.
- **Playwright:** Underlying automation library.

## Infrastructure & Execution
- **RestrictedPython:** Sandbox environment for executing dynamically generated agent code.
- **apscheduler:** Management of periodic tasks (finance monitoring, nightly consolidation).
- **psutil:** System resource monitoring and process management.

## Utilities
- **yt-dlp:** Media downloading.
- **trafilatura:** Structural web content extraction.
- **httpx:** Asynchronous HTTP requests.
- **numpy:** Efficient vector and numerical processing.
