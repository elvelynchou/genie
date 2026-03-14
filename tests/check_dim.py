import os
import asyncio
from google import genai
from dotenv import load_dotenv

load_dotenv()

async def check_dim():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents="Hello World"
    )
    vec = response.embeddings[0].values
    print(f"Dimension: {len(vec)}")

if __name__ == "__main__":
    asyncio.run(check_dim())
