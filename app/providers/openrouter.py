from typing import List, Dict, Any
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("OpenRouter")

class OpenRouterProvider(BaseProvider):
    """OpenRouter - Unified API gateway for 500+ models"""
    def __init__(self):
        super().__init__("openrouter", "OPENROUTER_API_KEY")
        self.default_model = "anthropic/claude-sonnet-4"
        self.fallback_models = {
            # Anthropic Claude 4
            "claude-opus-4.5": "anthropic/claude-opus-4.5",
            "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
            "claude-sonnet-4": "anthropic/claude-sonnet-4",
            # OpenAI GPT-5
            "gpt-5.2": "openai/gpt-5.2",
            "gpt-5": "openai/gpt-5",
            "gpt-4o": "openai/gpt-4o",
            # Google Gemini
            "gemini-3-pro": "google/gemini-3-pro-preview",
            "gemini-2.5-pro": "google/gemini-2.5-pro-preview",
            "gemini-2.5-flash": "google/gemini-2.5-flash",
            # Meta Llama
            "llama-4-maverick": "meta-llama/llama-4-maverick",
            "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
            # DeepSeek
            "deepseek-r1": "deepseek/deepseek-r1",
            "deepseek-v3": "deepseek/deepseek-v3",
            # Qwen
            "qwen3-235b": "qwen/qwen3-235b-a22b",
            "qwen3-32b": "qwen/qwen3-32b",
            # GLM
            "glm-4.7": "zhipu/glm-4.7",
            "glm-4-flash": "zhipu/glm-4-flash",
            # MiniMax
            "minimax-m2.1": "minimax/minimax-m2.1",
        }
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.models_url = "https://openrouter.ai/api/v1/models"

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
                # Priority prefixes for sorting
                priority_prefixes = ["anthropic/claude", "openai/gpt-5", "openai/gpt-4", "google/gemini-3", "google/gemini-2", "deepseek", "meta-llama/llama-4", "qwen", "zhipu", "minimax"]
                
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if not model_id:
                        continue
                    
                    # Calculate priority
                    priority = 99
                    for i, prefix in enumerate(priority_prefixes):
                        if model_id.startswith(prefix):
                            priority = i
                            break
                    
                    models.append({
                        "id": model_id,
                        "name": m.get("name", model_id),
                        "_priority": priority
                    })
                
                models.sort(key=lambda x: (x["_priority"], x["id"]))
                return [{"id": m["id"], "name": m["name"]} for m in models[:50]]  # Limit to 50
        except Exception as e:
            logger.warn(f"Failed to fetch models: {e}")
            return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

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
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://qubot.app",
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                return {"thinking": "", "content": data["choices"][0]["message"]["content"]}
            except Exception as e:
                logger.error(f"OpenRouter API call failed: {e}")
                raise
