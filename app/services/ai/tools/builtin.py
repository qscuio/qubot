"""
Built-in tools: Web search, URL fetch, calculator, datetime, memory.
"""

import httpx
import re
from datetime import datetime, timezone
from typing import List, Any, Dict
from app.services.ai.tools.base import Tool, ToolParameter, ToolResult
from app.services.ai.tools.registry import register_tool
from app.core.config import settings
from app.core.logger import Logger

logger = Logger("BuiltinTools")


class WebSearchTool(Tool):
    """Search the web using SearXNG."""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Search the web for information. Returns search results with titles, URLs, and snippets."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="The search query",
                required=True
            ),
            ToolParameter(
                name="num_results",
                type="integer",
                description="Number of results to return (max 10)",
                required=False,
                default=5
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        num_results = min(kwargs.get("num_results", 5), 10)
        
        searx_url = getattr(settings, "SEARX_URL", None)
        if not searx_url:
            return ToolResult(
                success=False,
                output=None,
                error="SEARX_URL not configured"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{searx_url}/search",
                    params={"q": query, "format": "json"},
                    timeout=15.0
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:300]
                    })
                
                return ToolResult(
                    success=True,
                    output=results,
                    metadata={"query": query, "count": len(results)}
                )
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class FetchURLTool(Tool):
    """Fetch and parse web page content."""
    
    @property
    def name(self) -> str:
        return "fetch_url"
    
    @property
    def description(self) -> str:
        return "Fetch content from a URL. Returns the text content of the page."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                type="string",
                description="The URL to fetch",
                required=True
            ),
            ToolParameter(
                name="max_length",
                type="integer",
                description="Maximum characters to return",
                required=False,
                default=5000
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        url = kwargs.get("url", "")
        max_length = kwargs.get("max_length", 5000)
        
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, output=None, error="Invalid URL")
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 QuBot/1.0"},
                    timeout=20.0
                )
                response.raise_for_status()
                
                content = response.text
                # Basic HTML to text conversion
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()
                
                return ToolResult(
                    success=True,
                    output=content[:max_length],
                    metadata={"url": url, "length": len(content)}
                )
        except Exception as e:
            logger.error(f"URL fetch failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))


class CalculatorTool(Tool):
    """Evaluate mathematical expressions safely."""
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return "Evaluate a mathematical expression. Supports basic arithmetic, powers, and common math functions."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="expression",
                type="string",
                description="Mathematical expression to evaluate (e.g., '2 * 3 + 4', 'sqrt(16)', 'pow(2, 10)')",
                required=True
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        import math
        expression = kwargs.get("expression", "")
        
        # Allowed names for safe evaluation
        allowed = {
            "abs": abs, "round": round, "min": min, "max": max,
            "pow": pow, "sum": sum, "len": len,
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "log10": math.log10,
            "exp": math.exp, "pi": math.pi, "e": math.e,
            "floor": math.floor, "ceil": math.ceil
        }
        
        try:
            # Remove any potentially dangerous characters
            if any(c in expression for c in ['__', 'import', 'exec', 'eval', 'open']):
                return ToolResult(success=False, output=None, error="Invalid expression")
            
            result = eval(expression, {"__builtins__": {}}, allowed)
            return ToolResult(
                success=True,
                output=result,
                metadata={"expression": expression}
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=f"Calculation error: {e}")


class DateTimeTool(Tool):
    """Get current date and time information."""
    
    @property
    def name(self) -> str:
        return "datetime"
    
    @property
    def description(self) -> str:
        return "Get current date, time, or calculate time differences."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action to perform",
                required=True,
                enum=["now", "date", "time", "timestamp", "weekday"]
            ),
            ToolParameter(
                name="timezone",
                type="string",
                description="Timezone (e.g., 'UTC', 'US/Eastern')",
                required=False,
                default="UTC"
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "now")
        
        try:
            now = datetime.now(timezone.utc)
            
            if action == "now":
                output = now.isoformat()
            elif action == "date":
                output = now.strftime("%Y-%m-%d")
            elif action == "time":
                output = now.strftime("%H:%M:%S")
            elif action == "timestamp":
                output = int(now.timestamp())
            elif action == "weekday":
                output = now.strftime("%A")
            else:
                output = now.isoformat()
            
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


class MemoryTool(Tool):
    """Store and retrieve key-value notes."""
    
    _memory: Dict[str, Any] = {}
    
    @property
    def name(self) -> str:
        return "memory"
    
    @property
    def description(self) -> str:
        return "Store or retrieve persistent notes. Use to remember information across conversations."
    
    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: 'set', 'get', 'delete', or 'list'",
                required=True,
                enum=["set", "get", "delete", "list"]
            ),
            ToolParameter(
                name="key",
                type="string",
                description="Key name (required for set/get/delete)",
                required=False
            ),
            ToolParameter(
                name="value",
                type="string",
                description="Value to store (required for set)",
                required=False
            )
        ]
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "get")
        key = kwargs.get("key", "")
        value = kwargs.get("value", "")
        
        try:
            if action == "set":
                if not key:
                    return ToolResult(success=False, output=None, error="Key required for set")
                MemoryTool._memory[key] = value
                return ToolResult(success=True, output=f"Stored '{key}'")
            
            elif action == "get":
                if not key:
                    return ToolResult(success=False, output=None, error="Key required for get")
                val = MemoryTool._memory.get(key)
                if val is None:
                    return ToolResult(success=False, output=None, error=f"Key '{key}' not found")
                return ToolResult(success=True, output=val)
            
            elif action == "delete":
                if key in MemoryTool._memory:
                    del MemoryTool._memory[key]
                    return ToolResult(success=True, output=f"Deleted '{key}'")
                return ToolResult(success=False, output=None, error=f"Key '{key}' not found")
            
            elif action == "list":
                return ToolResult(success=True, output=list(MemoryTool._memory.keys()))
            
            return ToolResult(success=False, output=None, error="Unknown action")
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# Register all builtin tools
def register_builtin_tools():
    """Register all builtin tools with the registry."""
    register_tool(WebSearchTool())
    register_tool(FetchURLTool())
    register_tool(CalculatorTool())
    register_tool(DateTimeTool())
    register_tool(MemoryTool())
    logger.info("Registered builtin tools")
