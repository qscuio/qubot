from typing import List, Dict, Any, Optional
import httpx
import json
from app.providers.base import BaseProvider
from app.core.logger import Logger

logger = Logger("Gemini")

class GeminiProvider(BaseProvider):
    def __init__(self):
        super().__init__("gemini", "GEMINI_API_KEY")
        self.default_model = "gemini-2.5-flash"  # Stable default
        self.fallback_models = {
            # Gemini 3 (Latest - Preview)
            "gemini-3-pro": "gemini-3.0-pro-preview",
            "gemini-3-flash": "gemini-3.0-flash-preview",
            # Gemini 2.5 (Stable)
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-flash-lite": "gemini-2.5-flash-lite-preview-06-17",
            # Gemini 2.0
            "gemini-2.0-flash": "gemini-2.0-flash",
            "gemini-2.0-flash-lite": "gemini-2.0-flash-lite",
            # Gemini 1.5 (Legacy)
            "gemini-1.5-pro": "gemini-1.5-pro",
            "gemini-1.5-flash": "gemini-1.5-flash",
        }
    
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
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                    timeout=30.0
                )
                if response.status_code != 200:
                    return self.get_fallback_models()

                data = response.json()
                models = []
                # Priority: gemini-3 > gemini-2.5 > gemini-2.0 > gemini-1.5
                priority_map = {"3": 0, "2.5": 1, "2.0": 2, "1.5": 3}
                
                for m in data.get("models", []):
                    if not m.get("name") or "generateContent" not in m.get("supportedGenerationMethods", []):
                        continue
                    
                    model_id = m["name"].replace("models/", "")
                    display_name = m.get("displayName", model_id)
                    
                    # Skip embedding, aqa, tunedModels, image, vision-only, and old 1.0 models
                    if any(x in model_id.lower() for x in ["embedding", "aqa", "tuned", "image", "vision", "gemini-1.0"]):
                        continue
                    
                    # Only include gemini models (skip palm, etc)
                    if not model_id.startswith("gemini"):
                        continue
                    
                    # Calculate priority - prefer newer versions
                    priority = 99
                    for ver, p in priority_map.items():
                        if f"gemini-{ver}" in model_id or f"-{ver}-" in model_id:
                            priority = p
                            break
                    
                    # Boost flash and pro models
                    if "pro" in model_id:
                        priority -= 0.1
                    elif "flash" in model_id:
                        priority -= 0.05
                    
                    models.append({"id": model_id, "name": display_name, "_priority": priority})
                
                # Sort by priority, then alphabetically
                models.sort(key=lambda x: (x["_priority"], x["id"]))
                
                # Return top 15 models to avoid overwhelming the user
                return [{"id": m["id"], "name": m["name"]} for m in models[:15]]
        except Exception as e:
            logger.warn(f"Failed to fetch models: {e}")
            return self.get_fallback_models()

    async def call(self, prompt: str, model: str, history: List[Dict[str, str]] = None, context_prefix: str = "") -> Dict[str, Any]:
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        if history is None:
            history = []

        # Validate model - fallback to default for invalid/specialized models
        use_model = model or self.default_model
        invalid_patterns = ["computer-use", "image", "vision", "embedding", "aqa", "tuned"]
        if any(p in use_model.lower() for p in invalid_patterns):
            logger.warn(f"Invalid model {use_model}, falling back to {self.default_model}")
            use_model = self.default_model

        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        
        full_prompt = f"{context_prefix}{prompt}" if context_prefix else prompt
        contents.append({"role": "user", "parts": [{"text": full_prompt}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"contents": contents},
                    headers={"Content-Type": "application/json"},
                    timeout=90.0
                )
                response.raise_for_status()
                data = response.json()

                thinking, content = "", ""
                if data.get("candidates") and data["candidates"][0].get("content", {}).get("parts"):
                    for part in data["candidates"][0]["content"]["parts"]:
                        if part.get("thought"):
                            thinking += part.get("text", "")
                        else:
                            content += part.get("text", "")

                return {"thinking": thinking, "content": content}
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                raise
    
    async def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        tools: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call Gemini with tool/function calling support."""
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        
        # Build Gemini contents format
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "assistant":
                # Check for tool calls
                if msg.get("tool_calls"):
                    parts = []
                    if content:
                        parts.append({"text": content})
                    for tc in msg.get("tool_calls", []):
                        parts.append({
                            "functionCall": {
                                "name": tc.get("name", ""),
                                "args": tc.get("arguments", {})
                            }
                        })
                    contents.append({"role": "model", "parts": parts})
                else:
                    contents.append({"role": "model", "parts": [{"text": content}]})
            elif role == "tool":
                # Tool result
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.get("tool_call_id", ""),
                            "response": {"result": content}
                        }
                    }]
                })
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})
        
        # Convert OpenAI tool format to Gemini format
        gemini_tools = []
        if tools:
            function_declarations = []
            for tool in tools:
                func = tool.get("function", {})
                function_declarations.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
            if function_declarations:
                gemini_tools.append({"functionDeclarations": function_declarations})
        
        request_body = {"contents": contents}
        
        if system_prompt:
            request_body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        
        if gemini_tools:
            request_body["tools"] = gemini_tools
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or self.default_model}:generateContent?key={api_key}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()
                
                thinking = ""
                content = ""
                tool_calls = []
                
                if data.get("candidates") and data["candidates"][0].get("content", {}).get("parts"):
                    for part in data["candidates"][0]["content"]["parts"]:
                        if part.get("thought"):
                            thinking += part.get("text", "")
                        elif part.get("text"):
                            content += part.get("text", "")
                        elif part.get("functionCall"):
                            fc = part["functionCall"]
                            tool_calls.append({
                                "id": fc.get("name", ""),
                                "name": fc.get("name", ""),
                                "arguments": fc.get("args", {})
                            })
                
                return {
                    "thinking": thinking,
                    "content": content,
                    "tool_calls": tool_calls
                }
            except Exception as e:
                logger.error(f"Gemini API call with tools failed: {e}")
                raise

