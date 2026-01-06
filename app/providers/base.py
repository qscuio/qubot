from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.core.logger import Logger

class BaseProvider(ABC):
    def __init__(self, name: str, api_key_env_name: str):
        self.name = name
        self.api_key_env_name = api_key_env_name
        self.logger = Logger(f"Provider:{name}")
        self.fallback_models = {}

    def get_api_key(self) -> str:
        # Pydantic settings are case-insensitive
        return str(getattr(settings, self.api_key_env_name, "") or "")

    def is_configured(self) -> bool:
        return bool(self.get_api_key())

    async def fetch_models(self) -> List[Dict[str, str]]:
        """
        Fetch available models. Override in subclass.
        Default: return fallback models.
        """
        return self.get_fallback_models()

    def get_fallback_models(self) -> List[Dict[str, str]]:
        return [
            {"id": full_name, "name": short_name} 
            for short_name, full_name in self.fallback_models.items()
        ]

    @abstractmethod
    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        """
        Call the AI provider.
        Returns: {"thinking": str, "content": str}
        """
        pass
