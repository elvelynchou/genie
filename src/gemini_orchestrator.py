from google import genai
from google.genai import types
import os
import logging
from typing import List, Dict, Any, Optional

class GeminiOrchestrator:
    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        # The new SDK default version is v1, which might not have text-embedding-004 in all regions
        # We can try to specify the api_version if needed
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

    def chat(self, user_input: str, history: List[Dict[str, str]], summary: Optional[str] = None, context: Optional[str] = None, tools: Optional[List[Any]] = None) -> Any:
        """Synchronous chat method for execution in thread pool."""
        system_instruction = "You are GenieBot, an advanced AI assistant."
        if summary:
            system_instruction += f"\n[Previous Conversation Summary]: {summary}"
        if context:
            system_instruction += f"\n[Relevant Background Context]: {context}"
        
        contents = []
        for m in history:
            contents.append({"role": m["role"], "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_input}]})
        
        try:
            # Wrap function declarations into a single Tool object
            tool_config = None
            if tools:
                tool_config = [types.Tool(function_declarations=tools)]

            # Using the synchronous generate_content
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tool_config
                )
            )
            return response
        except Exception as e:
            self.logger.error(f"Gemini API error: {e}")
            raise

    def get_embedding(self, text: str) -> List[float]:
        """Convert text to vector."""
        try:
            # Verified model name from client.models.list()
            response = self.client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            self.logger.error(f"Embedding error with gemini-embedding-001: {e}")
            return []

    def summarize_history(self, history: List[Dict[str, str]], current_summary: Optional[str] = None) -> str:
        """Synchronous summarization."""
        prompt = "Summarize the following conversation history into a concise paragraph. "
        if current_summary:
            prompt += f"Incorporate this existing summary: {current_summary}\n\n"
        
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        full_prompt = f"{prompt}\nConversation:\n{history_text}\n\nSummary:"
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"Summarization error: {e}")
            return current_summary or ""

    def process_response(self, response: Any):
        if not hasattr(response, 'candidates') or not response.candidates:
            return {"type": "error", "content": "No candidates in response"}
        
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.text:
                return {"type": "text", "content": part.text}
            if part.function_call:
                return {
                    "type": "function_call",
                    "name": part.function_call.name,
                    "args": part.function_call.args
                }
        return {"type": "error", "content": "Unknown response format"}
