from typing import List, Dict, Any
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("OpenAI")

class OpenAIProvider(BaseProvider):
    def __init__(self):
        super().__init__("openai", "OPENAI_API_KEY")
        self.fallback_models = {
            "gpt-4": "gpt-4-turbo-preview",
            "gpt-3.5": "gpt-3.5-turbo",
        }
        self.base_url = "https://api.openai.com/v1/chat/completions"

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("OpenAI API Key not configured")

        if history is None:
            history = []

        messages = []
        if context_prefix:
            messages.append({"role": "system", "content": context_prefix})
        
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model or "gpt-3.5-turbo",
            "messages": messages,
            "temperature": 0.7
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                content = data['choices'][0]['message']['content']
                return {
                    "thinking": "",
                    "content": content
                }
            except Exception as e:
                logger.error(f"OpenAI API call failed: {e}")
                raise e
