import os
from google import genai
from google.genai import types
import base64
from dotenv import load_dotenv

load_dotenv()

def generate():
    client = genai.Client(
        vertexai=True,
        api_key=os.environ.get("GOOGLE_VERTEX_API_KEY"),
    )

    image1 = types.Part.from_bytes(
        data=b"dummy_data", # Just to test API validation
        mime_type="image/jpeg",
    )
    text1 = types.Part.from_text(text="Generate an image.")

    model = "gemini-3.1-flash-image-preview"
    contents = [
        types.Content(
            role="user",
            parts=[text1]
        )
    ]

    try:
        generate_content_config = types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="1:1",
                output_mime_type="image/png",
            )
        )
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        print("Success")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate()
