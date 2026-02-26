from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("--- Available Models ---")
for model in client.models.list():
    # Use dir() to see available attributes if unsure, but let's try the common ones
    # The new SDK might use different names
    try:
        print(f"Name: {model.name}, Methods: {model.supported_methods}")
    except AttributeError:
        print(f"Name: {model.name}")
