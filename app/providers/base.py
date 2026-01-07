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
    
    @property
    def supports_tools(self) -> bool:
        """Whether this provider supports tool/function calling."""
        return False
    
    @property
    def supports_thinking(self) -> bool:
        """Whether this provider supports extended thinking."""
        return False

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

    async def call_with_trace(
        self, 
        prompt: str, 
        model: str, 
        history: List[Dict[str, str]] = None, 
        context_prefix: str = ""
    ) -> Dict[str, Any]:
        """Call with automatic tracing. Wraps the actual call method."""
        from app.services.ai.tracer import ai_tracer
        
        # Start trace
        ai_tracer.start_trace(
            provider=self.name,
            model=model or getattr(self, 'default_model', 'unknown'),
            prompt=prompt,
            system_prompt=context_prefix,
            history=history
        )
        
        try:
            result = await self.call(prompt, model, history, context_prefix)
            ai_tracer.end_trace(
                response=result.get("content", ""),
                thinking=result.get("thinking", ""),
                success=True
            )
            return result
        except Exception as e:
            ai_tracer.end_trace(
                success=False,
                error=str(e)
            )
            raise

    @abstractmethod
    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        """
        Call the AI provider.
        Returns: {"thinking": str, "content": str}
        """
        pass
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call the AI provider with tool/function calling support.
        
        Args:
            messages: List of conversation messages
            model: Model to use
            system_prompt: System prompt
            tools: List of tool schemas in OpenAI function format
            
        Returns:
            {
                "thinking": str,
                "content": str,
                "tool_calls": [{"id": str, "name": str, "arguments": dict}]
            }
        """
        # Default implementation: fall back to regular call without tools
        prompt = messages[-1]["content"] if messages else ""
        history = messages[:-1] if len(messages) > 1 else []
        result = await self.call(
            prompt=prompt,
            model=model,
            history=history,
            context_prefix=system_prompt
        )
        result["tool_calls"] = []
        return result

