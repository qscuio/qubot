from typing import List, Dict, Any
import httpx
import json
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
    
    @property
    def supports_tools(self) -> bool:
        return True

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
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call GLM with tool/function calling support (OpenAI-compatible)."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GLM_API_KEY is not set")
        
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content
                })
            elif role == "assistant" and msg.get("tool_calls"):
                api_messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.get("id", tc.get("name", "")),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else tc.get("arguments", "{}")
                            }
                        }
                        for tc in msg.get("tool_calls", [])
                    ]
                })
            else:
                api_messages.append({"role": role, "content": content})
        
        payload = {
            "model": model or self.default_model,
            "messages": api_messages
        }
        
        if tools:
            payload["tools"] = tools
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                
                choice = data["choices"][0]["message"]
                content = choice.get("content", "") or ""
                
                tool_calls = []
                if choice.get("tool_calls"):
                    for tc in choice["tool_calls"]:
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                args = {}
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "arguments": args
                        })
                
                return {
                    "thinking": "",
                    "content": content,
                    "tool_calls": tool_calls
                }
            except Exception as e:
                logger.error(f"GLM API call with tools failed: {e}")
                raise

