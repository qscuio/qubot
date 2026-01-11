"""
Abstract base class for CLI-based coding agents.

Provides a common interface for Claude Code, Gemini CLI, and Codex agents.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from app.core.logger import Logger


@dataclass
class AgentRequest:
    """Normalized agent invocation request."""
    
    user_id: int
    chat_id: int
    message: str
    working_path: str
    session_id: str
    reply_callback: Optional[Callable[[str], Any]] = None
    started_at: float = field(default_factory=time.monotonic)


@dataclass
class AgentMessage:
    """Normalized message emitted by an agent."""
    
    text: str
    message_type: str = "assistant"  # assistant, system, result, error
    parse_mode: str = "Markdown"
    metadata: Optional[Dict[str, Any]] = None


class BaseCLIAgent(ABC):
    """Abstract base class for CLI-based coding agents."""
    
    name: str = "base"
    
    def __init__(self, service: Any):
        """
        Initialize agent with reference to parent service.
        
        Args:
            service: The VibeRemoteService instance
        """
        self.service = service
        self.logger = Logger(f"Agent:{self.name}")
        self._active_sessions: Dict[str, Any] = {}
    
    def _calculate_duration_ms(self, started_at: Optional[float]) -> int:
        """Calculate elapsed time in milliseconds."""
        if not started_at:
            return 0
        elapsed = time.monotonic() - started_at
        return max(0, int(elapsed * 1000))
    
    def format_duration(self, duration_ms: int) -> str:
        """Format duration for display."""
        if duration_ms < 1000:
            return f"{duration_ms}ms"
        elif duration_ms < 60000:
            return f"{duration_ms / 1000:.1f}s"
        else:
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) / 1000
            return f"{minutes}m {seconds:.0f}s"
    
    async def emit_message(
        self,
        request: AgentRequest,
        message: AgentMessage
    ) -> None:
        """Emit a message back to the user."""
        if request.reply_callback:
            try:
                await request.reply_callback(message.text)
            except Exception as e:
                self.logger.error(f"Failed to emit message: {e}")
    
    async def emit_result(
        self,
        request: AgentRequest,
        result_text: Optional[str],
        subtype: str = "success",
        duration_ms: Optional[int] = None
    ) -> None:
        """Emit a result message with duration."""
        if duration_ms is None:
            duration_ms = self._calculate_duration_ms(request.started_at)
        
        duration_str = self.format_duration(duration_ms)
        
        if subtype == "success":
            emoji = "✅"
        elif subtype == "error":
            emoji = "❌"
        elif subtype == "interrupted":
            emoji = "⏹"
        else:
            emoji = "📝"
        
        if result_text:
            text = f"{emoji} *Completed* ({duration_str})\n\n{result_text}"
        else:
            text = f"{emoji} *Completed* ({duration_str})"
        
        await self.emit_message(request, AgentMessage(
            text=text,
            message_type="result"
        ))
    
    @abstractmethod
    async def handle_message(self, request: AgentRequest) -> None:
        """
        Process a user message.
        
        Args:
            request: The agent request containing message and context
        """
        pass
    
    @abstractmethod
    async def handle_stop(self, request: AgentRequest) -> bool:
        """
        Stop a running task.
        
        Args:
            request: The agent request context
            
        Returns:
            True if task was stopped, False if no task running
        """
        pass
    
    async def clear_sessions(self, session_id: str) -> int:
        """
        Clear session state.
        
        Args:
            session_id: The session to clear
            
        Returns:
            Number of sessions cleared
        """
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            return 1
        return 0
    
    def is_available(self) -> bool:
        """Check if this agent is available (CLI installed)."""
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status info."""
        return {
            "name": self.name,
            "available": self.is_available(),
            "active_sessions": len(self._active_sessions)
        }
