"""
Claude Code Agent - Integration with Anthropic's Claude Code CLI.

Uses claude_code_sdk for communication with Claude Code.
"""

import asyncio
import os
import shutil
from typing import Any, Dict, Optional

from app.services.vibe_remote.agents.base import AgentRequest, AgentMessage, BaseCLIAgent

# Try to import claude_code_sdk (optional dependency)
try:
    from claude_code_sdk import (
        ClaudeCodeClient,
        ClaudeCodeOptions,
        TextBlock,
    )
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False


class ClaudeAgent(BaseCLIAgent):
    """Claude Code CLI integration using claude_code_sdk."""
    
    name = "claude"
    
    def __init__(self, service: Any):
        super().__init__(service)
        self._clients: Dict[str, Any] = {}
        self._receiver_tasks: Dict[str, asyncio.Task] = {}
    
    def is_available(self) -> bool:
        """Check if Claude Code CLI is available."""
        if not CLAUDE_SDK_AVAILABLE:
            return False
        # Check if binary exists
        return shutil.which("claude") is not None
    
    async def handle_message(self, request: AgentRequest) -> None:
        """Process message through Claude Code."""
        if not CLAUDE_SDK_AVAILABLE:
            await self.emit_message(request, AgentMessage(
                text="❌ Claude Code SDK not installed. Install with: `pip install claude_code_sdk`",
                message_type="error"
            ))
            return
        
        if not shutil.which("claude"):
            await self.emit_message(request, AgentMessage(
                text="❌ Claude Code CLI not found. Install with: `npm install -g @anthropic-ai/claude-code`",
                message_type="error"
            ))
            return
        
        # Ensure working directory exists
        if not os.path.exists(request.working_path):
            os.makedirs(request.working_path, exist_ok=True)
        
        try:
            client = await self._get_or_create_client(request)
            
            await client.query(request.message, session_id=request.session_id)
            self.logger.info(f"Sent message to Claude for session {request.session_id}")
            
            # Start receiver if not running
            if request.session_id not in self._receiver_tasks or self._receiver_tasks[request.session_id].done():
                self._receiver_tasks[request.session_id] = asyncio.create_task(
                    self._receive_messages(client, request)
                )
                
        except Exception as e:
            self.logger.error(f"Claude error: {e}")
            await self.emit_message(request, AgentMessage(
                text=f"❌ Claude error: {e}",
                message_type="error"
            ))
    
    async def _get_or_create_client(self, request: AgentRequest) -> Any:
        """Get or create Claude Code client for session."""
        if request.session_id in self._clients:
            return self._clients[request.session_id]
        
        options = ClaudeCodeOptions(
            permission_mode="bypassPermissions",
            cwd=request.working_path,
        )
        
        client = ClaudeCodeClient(options)
        self._clients[request.session_id] = client
        self._active_sessions[request.session_id] = {
            "client": client,
            "started_at": request.started_at
        }
        
        return client
    
    async def _receive_messages(self, client: Any, request: AgentRequest) -> None:
        """Receive streaming messages from Claude."""
        try:
            async for message in client.receive_messages():
                try:
                    formatted = self._format_message(message)
                    if formatted:
                        await self.emit_message(request, AgentMessage(
                            text=formatted,
                            message_type=self._detect_type(message)
                        ))
                except Exception as e:
                    self.logger.error(f"Error processing Claude message: {e}")
        except Exception as e:
            self.logger.error(f"Claude receiver error: {e}")
            await self.emit_message(request, AgentMessage(
                text=f"❌ Claude stream error: {e}",
                message_type="error"
            ))
    
    def _format_message(self, message: Any) -> Optional[str]:
        """Format Claude message for Telegram."""
        class_name = message.__class__.__name__
        
        if class_name == "AssistantMessage":
            parts = []
            for block in getattr(message, "content", []) or []:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
            return "\n\n".join(parts) if parts else None
        
        elif class_name == "ResultMessage":
            duration = getattr(message, "duration_ms", 0)
            result = getattr(message, "result", None)
            subtype = getattr(message, "subtype", "success")
            
            emoji = "✅" if subtype == "success" else "❌"
            duration_str = self.format_duration(duration)
            
            if result:
                return f"{emoji} *Completed* ({duration_str})\n\n{result}"
            return f"{emoji} *Completed* ({duration_str})"
        
        elif class_name == "SystemMessage":
            subtype = getattr(message, "subtype", None)
            if subtype == "init":
                data = getattr(message, "data", {}) or {}
                cwd = data.get("cwd", "unknown")
                return f"🚀 Claude session started in `{cwd}`"
        
        return None
    
    def _detect_type(self, message: Any) -> str:
        """Detect message type."""
        class_name = message.__class__.__name__
        mapping = {
            "SystemMessage": "system",
            "AssistantMessage": "assistant",
            "ResultMessage": "result",
        }
        return mapping.get(class_name, "assistant")
    
    async def handle_stop(self, request: AgentRequest) -> bool:
        """Stop Claude session."""
        session_id = request.session_id
        
        if session_id not in self._clients:
            return False
        
        client = self._clients[session_id]
        try:
            if hasattr(client, "interrupt"):
                await client.interrupt()
                self.logger.info(f"Claude session {session_id} interrupted")
                return True
        except Exception as e:
            self.logger.error(f"Failed to interrupt Claude: {e}")
        
        return False
    
    async def clear_sessions(self, session_id: str) -> int:
        """Clear Claude sessions."""
        count = 0
        
        if session_id in self._clients:
            client = self._clients.pop(session_id)
            if hasattr(client, "close"):
                try:
                    await client.close()
                except Exception:
                    pass
            count += 1
        
        if session_id in self._receiver_tasks:
            task = self._receiver_tasks.pop(session_id)
            task.cancel()
        
        await super().clear_sessions(session_id)
        return count
