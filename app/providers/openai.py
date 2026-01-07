from typing import List, Dict, Any
import httpx
import json
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("OpenAI")

class OpenAIProvider(BaseProvider):
    def __init__(self):
        super().__init__("openai", "OPENAI_API_KEY")
        self.default_model = "gpt-4o"
        self.fallback_models = {
            "gpt-5.2": "gpt-5.2",
            "gpt-5.2-codex": "gpt-5.2-codex",
            "gpt-5.1": "gpt-5.1",
            "gpt-5": "gpt-5",
            "gpt-4.5": "gpt-4.5",
            "gpt-4.1": "gpt-4.1",
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            "o4-mini": "o4-mini",
            "o3-mini": "o3-mini",
        }
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.models_url = "https://api.openai.com/v1/models"
    
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
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    # Filter to only chat-capable models (gpt-*)
                    if model_id.startswith("gpt-") and not any(x in model_id for x in ["instruct", "vision", "audio", "realtime"]):
                        models.append({"id": model_id, "name": model_id})
                return sorted(models, key=lambda x: x["id"], reverse=True)[:20]  # Limit to top 20
        except Exception as e:
            logger.warn(f"Failed to fetch models: {e}")
            return self.get_fallback_models()


    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("OpenAI API Key not configured")

        if history is None:
            history = []

        messages = []
        if context_prefix:
            messages.append({"role": "system", "content": context_prefix})
        
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model or "gpt-3.5-turbo",
            "messages": messages,
            "temperature": 0.7
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, json=payload, headers=headers, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                content = data['choices'][0]['message']['content']
                return {
                    "thinking": "",
                    "content": content
                }
            except Exception as e:
                logger.error(f"OpenAI API call failed: {e}")
                raise e
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call OpenAI with tool/function calling support."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("OpenAI API Key not configured")
        
        # Build messages with system prompt
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
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
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
                logger.error(f"OpenAI API call with tools failed: {e}")
                raise

