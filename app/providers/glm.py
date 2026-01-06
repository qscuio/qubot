from typing import List, Dict, Any
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("GLM")

class GLMProvider(BaseProvider):
    """Zhipu AI GLM Provider (ChatGLM)"""
    def __init__(self):
        super().__init__("glm", "GLM_API_KEY")
        self.default_model = "glm-4-flash"
        self.fallback_models = {
            "glm-4.7": "glm-4.7",
            "glm-4.6": "glm-4.6",
            "glm-4.5": "glm-4.5",
            "glm-4-plus": "glm-4-plus",
            "glm-4-flash": "glm-4-flash",
            "glm-4-air": "glm-4-air",
            "glm-4-long": "glm-4-long",
            "glm-4-alltools": "glm-4-alltools",
        }
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    async def fetch_models(self) -> List[Dict[str, str]]:
        # GLM doesn't have a public models list API, use fallback
        return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GLM_API_KEY is not set")

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
                logger.error(f"GLM API call failed: {e}")
                raise
