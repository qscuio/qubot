from typing import List, Dict, Any
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("OpenAI")

class OpenAIProvider(BaseProvider):
    def __init__(self):
        super().__init__("openai", "OPENAI_API_KEY")
        self.default_model = "gpt-4o"
        self.fallback_models = {
            "gpt-5.2": "gpt-5.2",
            "gpt-5.2-codex": "gpt-5.2-codex",
            "gpt-5.1": "gpt-5.1",
            "gpt-5": "gpt-5",
            "gpt-4.5": "gpt-4.5",
            "gpt-4.1": "gpt-4.1",
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            "o4-mini": "o4-mini",
            "o3-mini": "o3-mini",
        }
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.models_url = "https://api.openai.com/v1/models"

    async def fetch_models(self) -> List[Dict[str, str]]:
        api_key = self.get_api_key()
        if not api_key:
            return self.get_fallback_models()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30.0
                )
                if response.status_code != 200:
                    return self.get_fallback_models()

                data = response.json()
                models = []
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    # Filter to only chat-capable models (gpt-*)
                    if model_id.startswith("gpt-") and not any(x in model_id for x in ["instruct", "vision", "audio", "realtime"]):
                        models.append({"id": model_id, "name": model_id})
                return sorted(models, key=lambda x: x["id"], reverse=True)[:20]  # Limit to top 20
        except Exception as e:
            logger.warn(f"Failed to fetch models: {e}")
            return self.get_fallback_models()


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
