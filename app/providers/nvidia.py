from typing import List, Dict, Any, Optional
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("NVIDIA")

class NvidiaProvider(BaseProvider):
    def __init__(self):
        super().__init__("nvidia", "NVIDIA_API_KEY")
        self.default_model = "deepseek-ai/deepseek-r1"
        self.fallback_models = {
            "deepseek-r1": "deepseek-ai/deepseek-r1",
            "deepseek-v3": "deepseek-ai/deepseek-v3.2",
            "llama-405b": "meta/llama-3.1-405b-instruct",
            "nemotron-ultra": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "qwen3-coder": "qwen/qwen3-coder-480b-a35b-instruct",
            "llama-70b": "meta/llama-3.3-70b-instruct",
        }
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"

    async def fetch_models(self) -> List[Dict[str, str]]:
        # NVIDIA has too many models, use curated fallback list
        return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("NVIDIA_API_KEY is not set")

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
                    json={"model": model or self.default_model, "messages": messages, "max_tokens": 4096},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=120.0  # 2 minutes for slow models like DeepSeek R1
                )
                response.raise_for_status()
                data = response.json()
                return {"thinking": "", "content": data["choices"][0]["message"]["content"]}
            except Exception as e:
                logger.error(f"NVIDIA API call failed: {e}")
                raise
