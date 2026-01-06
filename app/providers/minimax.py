from typing import List, Dict, Any
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("MiniMax")

class MiniMaxProvider(BaseProvider):
    """MiniMax AI Provider"""
    def __init__(self):
        super().__init__("minimax", "MINIMAX_API_KEY")
        self.default_model = "MiniMax-Text-01"
        self.fallback_models = {
            "minimax-m2.1": "MiniMax-M2.1",
            "minimax-m2": "MiniMax-M2",
            "minimax-m1": "MiniMax-M1",
            "minimax-text-01": "MiniMax-Text-01",
            "abab-7": "abab7-chat-preview",
            "abab-6.5": "abab6.5-chat",
            "abab-6.5s": "abab6.5s-chat",
        }
        self.base_url = "https://api.minimax.chat/v1/text/chatcompletion_v2"

    async def fetch_models(self) -> List[Dict[str, str]]:
        # MiniMax doesn't have a public models list API, use fallback
        return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is not set")

        if history is None:
            history = []

        messages = []
        if context_prefix:
            messages.append({"role": "system", "content": context_prefix})
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json={"model": model or self.default_model, "messages": messages},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=90.0
                )
                response.raise_for_status()
                data = response.json()
                return {"thinking": "", "content": data["choices"][0]["message"]["content"]}
            except Exception as e:
                logger.error(f"MiniMax API call failed: {e}")
                raise
