from typing import List, Dict, Any, Optional
import httpx
import json
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("NVIDIA")

class NvidiaProvider(BaseProvider):
    def __init__(self):
        super().__init__("nvidia", "NVIDIA_API_KEY")
        self.default_model = "deepseek-ai/deepseek-r1"
        self.fallback_models = {
            "deepseek-v3.2": "deepseek-ai/deepseek-v3.2",
            "deepseek-r1": "deepseek-ai/deepseek-r1",
            "nemotron-ultra": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
            "nemotron-super": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
            "nemotron-nano": "nvidia/llama-3.1-nemotron-nano-4b-v1.1",
            "llama-3.3-70b": "meta/llama-3.3-70b-instruct",
            "llama-405b": "meta/llama-3.1-405b-instruct",
            "qwen3-coder": "qwen/qwen3-coder-480b-a35b-instruct",
        }
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    
    @property
    def supports_tools(self) -> bool:
        return True

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
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call NVIDIA with tool/function calling support (OpenAI-compatible)."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("NVIDIA_API_KEY is not set")
        
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
            "messages": api_messages,
            "max_tokens": 4096
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
                logger.error(f"NVIDIA API call with tools failed: {e}")
                raise

