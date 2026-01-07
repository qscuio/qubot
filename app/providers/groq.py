from typing import List, Dict, Any, Optional
import httpx
import json
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("Groq")

class GroqProvider(BaseProvider):
    def __init__(self):
        super().__init__("groq", "GROQ_API_KEY")
        self.default_model = "llama-3.3-70b-versatile"
        self.fallback_models = {
            "llama-4-maverick": "llama-4-maverick-17b-128e-instruct",
            "llama-4-scout": "llama-4-scout-17b-16e-instruct",
            "llama-3.3-70b": "llama-3.3-70b-versatile",
            "llama-3.1-8b": "llama-3.1-8b-instant",
            "qwen3-32b": "qwen3-32b",
            "qwen2.5-32b": "qwen-2.5-32b",
            "deepseek-r1-32b": "deepseek-r1-distill-qwen-32b",
            "mixtral-8x7b": "mixtral-8x7b-32768",
        }
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.models_url = "https://api.groq.com/openai/v1/models"
    
    @property
    def supports_tools(self) -> bool:
        return True

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
                # Priority order for sorting
                priority_prefixes = ["llama-3.3", "llama-3.2", "llama-3.1", "deepseek", "qwen", "mixtral", "gemma"]
                
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    # Skip non-chat models
                    if any(x in model_id for x in ["whisper", "distil", "guard", "tool-use"]):
                        continue
                    if model_id:
                        # Calculate priority score
                        priority = 99
                        for i, prefix in enumerate(priority_prefixes):
                            if prefix in model_id.lower():
                                priority = i
                                break
                        models.append({"id": model_id, "name": model_id, "_priority": priority})
                
                # Sort by priority then by name (descending for version numbers)
                models.sort(key=lambda x: (x["_priority"], x["id"]))
                # Remove priority field before returning
                return [{"id": m["id"], "name": m["name"]} for m in models]
        except Exception as e:
            logger.warn(f"Failed to fetch models: {e}")
            return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set")

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
                    timeout=90.0
                )
                response.raise_for_status()
                data = response.json()
                return {"thinking": "", "content": data["choices"][0]["message"]["content"]}
            except Exception as e:
                logger.error(f"Groq API call failed: {e}")
                raise
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call Groq with tool/function calling support (OpenAI-compatible)."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set")
        
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
                logger.error(f"Groq API call with tools failed: {e}")
                raise

