"""
Tool registry for managing and discovering tools.
"""

from typing import Dict, List, Optional, Any
from app.services.ai.tools.base import Tool
from app.core.logger import Logger

logger = Logger("ToolRegistry")


class ToolRegistry:
    """Registry for managing available tools."""
    
    _instance: Optional['ToolRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, Tool] = {}
            cls._instance._initialized = False
        return cls._instance
    
    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool by name."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_all(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())
    
    def list_names(self) -> List[str]:
        """List all tool names."""
        return list(self._tools.keys())
    
    def get_schemas(self, tool_names: List[str] = None) -> List[Dict[str, Any]]:
        """Get JSON schemas for specified tools (or all if None)."""
        tools = self._tools.values() if tool_names is None else [
            self._tools[n] for n in tool_names if n in self._tools
        ]
        return [t.get_schema() for t in tools]
    
    def get_tool_info(self) -> List[Dict[str, str]]:
        """Get info about all tools for display."""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]


# Global registry instance
tool_registry = ToolRegistry()


def register_tool(tool: Tool) -> Tool:
    """Decorator/function to register a tool."""
    tool_registry.register(tool)
    return tool
