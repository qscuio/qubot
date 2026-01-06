from typing import List, Dict, Any, Optional
import httpx
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("Claude")

class ClaudeProvider(BaseProvider):
    def __init__(self):
        super().__init__("claude", "CLAUDE_API_KEY")
        self.default_model = "claude-sonnet-4-20250514"
        self.fallback_models = {
            "claude-opus-4.5": "claude-opus-4-5-20251124",
            "claude-sonnet-4.5": "claude-sonnet-4-5-20250929",
            "claude-haiku-4.5": "claude-haiku-4-5-20251015",
            "claude-opus-4": "claude-opus-4-20250522",
            "claude-sonnet-4": "claude-sonnet-4-20250514",
        }
        self.base_url = "https://api.anthropic.com/v1/messages"

    async def fetch_models(self) -> List[Dict[str, str]]:
        # Claude doesn't have a public models API
        return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("CLAUDE_API_KEY is not set")

        if history is None:
            history = []

        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        full_prompt = f"{context_prefix}{prompt}" if context_prefix else prompt
        messages.append({"role": "user", "content": full_prompt})

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json={"model": model or self.default_model, "max_tokens": 4096, "messages": messages},
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=90.0
                )
                response.raise_for_status()
                data = response.json()

                thinking, content = "", ""
                for block in data.get("content", []):
                    if block.get("type") == "thinking":
                        thinking += block.get("thinking", "")
                    elif block.get("type") == "text":
                        content += block.get("text", "")

                return {"thinking": thinking, "content": content}
            except Exception as e:
                logger.error(f"Claude API call failed: {e}")
                raise
