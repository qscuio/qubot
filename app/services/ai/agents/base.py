"""
Agent base class for AI agents with tool execution support.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from app.services.ai.tools.base import Tool, ToolResult
from app.services.ai.tools.registry import tool_registry
from app.core.logger import Logger


@dataclass
class AgentMessage:
    """A message in the agent conversation."""
    role: str  # "user", "assistant", "tool"
    content: str
    tool_name: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Response from an agent execution."""
    content: str
    thinking: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """Base class for AI agents."""
    
    def __init__(self):
        self.logger = Logger(f"Agent:{self.name}")
        self._tools: List[Tool] = []
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the agent."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the agent's capabilities."""
        pass
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt that defines the agent's behavior."""
        pass
    
    @property
    def tools(self) -> List[Tool]:
        """List of tools available to this agent."""
        return self._tools
    
    def add_tool(self, tool: Tool) -> None:
        """Add a tool to the agent."""
        self._tools.append(tool)
    
    def add_tools_by_name(self, tool_names: List[str]) -> None:
        """Add tools by their registered names."""
        for name in tool_names:
            tool = tool_registry.get(name)
            if tool:
                self._tools.append(tool)
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get JSON schemas for all agent tools."""
        return [t.get_schema() for t in self._tools]
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None
    
    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with given arguments."""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool '{tool_name}' not found"
            )
        
        # Validate parameters
        error = tool.validate_params(**kwargs)
        if error:
            return ToolResult(success=False, output=None, error=error)
        
        try:
            result = await tool.execute(**kwargs)
            self.logger.debug(f"Tool {tool_name} executed: success={result.success}")
            return result
        except Exception as e:
            self.logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))
    
    @abstractmethod
    async def run(
        self,
        message: str,
        history: List[Dict[str, str]] = None,
        max_tool_calls: int = 10
    ) -> AgentResponse:
        """
        Run the agent with a message and conversation history.
        
        Args:
            message: The user's message
            history: Previous conversation messages
            max_tool_calls: Maximum number of tool calls allowed
            
        Returns:
            AgentResponse with content, tool calls, and results
        """
        pass
    
    def build_messages(
        self,
        message: str,
        history: List[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """Build message list for API call."""
        messages = []
        
        if history:
            for msg in history:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        messages.append({"role": "user", "content": message})
        return messages
    
    def format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for inclusion in messages."""
        if result.success:
            import json
            if isinstance(result.output, (dict, list)):
                return json.dumps(result.output, indent=2, default=str)
            return str(result.output)
        else:
            return f"Error: {result.error}"
