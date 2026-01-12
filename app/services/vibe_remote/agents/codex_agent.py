"""
Codex Agent - Integration with OpenAI's Codex CLI.

Uses subprocess with JSON streaming mode (codex exec --json).
"""

import asyncio
import json
import os
import shutil
import signal
from asyncio.subprocess import Process
from typing import Any, Dict, Optional

from app.services.vibe_remote.agents.base import AgentRequest, AgentMessage, BaseCLIAgent

STREAM_BUFFER_LIMIT = 8 * 1024 * 1024  # 8MB


class CodexAgent(BaseCLIAgent):
    """Codex CLI integration via codex exec --json streaming."""
    
    name = "codex"
    
    def __init__(self, service: Any, model: Optional[str] = None):
        super().__init__(service)
        self._binary_path: Optional[str] = None
        self._model = model or "gpt-4o"
        self._active_processes: Dict[str, Process] = {}
    
    def _find_binary(self) -> Optional[str]:
        """Find the codex binary."""
        if self._binary_path:
            return self._binary_path
        
        import glob
        
        paths = [
            shutil.which("codex"),
            "/usr/local/bin/codex",
            "/usr/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
            os.path.expanduser("~/node_modules/.bin/codex"),
        ]
        
        # Add nvm paths (glob pattern)
        nvm_pattern = os.path.expanduser("~/.nvm/versions/node/*/bin/codex")
        paths.extend(glob.glob(nvm_pattern))
        
        # Add npm global (root installed)
        paths.extend([
            "/root/.nvm/versions/node/v20.19.6/bin/codex",
            "/root/node_modules/.bin/codex",
        ])
        
        for path in paths:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                self._binary_path = path
                self.logger.info(f"Found codex binary at: {path}")
                return path
        
        return None
    
    def is_available(self) -> bool:
        """Check if Codex CLI is installed."""
        return self._find_binary() is not None
    
    async def handle_message(self, request: AgentRequest) -> None:
        """Process message through Codex CLI."""
        binary = self._find_binary()
        if not binary:
            await self.emit_message(request, AgentMessage(
                text="❌ Codex CLI not found. Install with: `npm install -g @openai/codex`",
                message_type="error"
            ))
            return
        
        # Cancel existing process if any
        if request.session_id in self._active_processes:
            proc = self._active_processes[request.session_id]
            if proc.returncode is None:
                await self.emit_message(request, AgentMessage(
                    text="⚠️ Cancelling previous Codex task...",
                    message_type="system"
                ))
                await self._terminate_process(request.session_id)
        
        # Ensure working directory exists
        if not os.path.exists(request.working_path):
            os.makedirs(request.working_path, exist_ok=True)
        
        # Build command
        cmd = self._build_command(binary, request)
        
        self.logger.info(f"Executing Codex: {' '.join(cmd[:-1])} <prompt>")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=request.working_path,
                limit=STREAM_BUFFER_LIMIT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            
            self._active_processes[request.session_id] = process
            self._active_sessions[request.session_id] = {
                "process": process,
                "started_at": request.started_at
            }
            
            # Stream output
            stdout_task = asyncio.create_task(self._consume_stdout(process, request))
            stderr_task = asyncio.create_task(self._consume_stderr(process, request))
            
            try:
                await process.wait()
                await asyncio.gather(stdout_task, stderr_task)
            finally:
                self._active_processes.pop(request.session_id, None)
                self._active_sessions.pop(request.session_id, None)
            
            if process.returncode != 0:
                await self.emit_message(request, AgentMessage(
                    text="⚠️ Codex exited with non-zero status.",
                    message_type="system"
                ))
                
        except FileNotFoundError:
            await self.emit_message(request, AgentMessage(
                text="❌ Failed to start Codex CLI.",
                message_type="error"
            ))
        except Exception as e:
            self.logger.error(f"Codex error: {e}")
            await self.emit_message(request, AgentMessage(
                text=f"❌ Codex error: {e}",
                message_type="error"
            ))
    
    def _build_command(self, binary: str, request: AgentRequest) -> list:
        """Build codex command."""
        cmd = [
            binary, "exec", "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model", self._model,
            "--cd", request.working_path,
            request.message
        ]
        return cmd
    
    async def _consume_stdout(self, process: Process, request: AgentRequest) -> None:
        """Consume JSON streaming stdout."""
        assert process.stdout is not None
        
        try:
            while True:
                try:
                    line = await process.stdout.readline()
                except (asyncio.LimitOverrunError, ValueError) as e:
                    self.logger.error(f"Codex stdout overflow: {e}")
                    break
                
                if not line:
                    break
                
                decoded = line.decode("utf-8", errors="ignore").strip()
                if not decoded:
                    continue
                
                try:
                    event = json.loads(decoded)
                    await self._handle_event(event, request)
                except json.JSONDecodeError:
                    self.logger.debug(f"Codex non-JSON: {decoded}")
                    
        except Exception as e:
            self.logger.error(f"Codex stdout error: {e}")
    
    async def _consume_stderr(self, process: Process, request: AgentRequest) -> None:
        """Consume stderr."""
        assert process.stderr is not None
        
        buffer = []
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="ignore").rstrip()
            buffer.append(decoded)
            self.logger.debug(f"Codex stderr: {decoded}")
        
        if buffer:
            joined = "\n".join(buffer[-10:])
            await self.emit_message(request, AgentMessage(
                text=f"❗️ Codex stderr:\n```\n{joined}\n```",
                message_type="system"
            ))
    
    async def _handle_event(self, event: Dict, request: AgentRequest) -> None:
        """Handle Codex JSON event."""
        event_type = event.get("type")
        
        if event_type == "message":
            content = event.get("content", "")
            if content:
                await self.emit_message(request, AgentMessage(
                    text=content,
                    message_type="assistant"
                ))
        
        elif event_type == "tool_use":
            tool = event.get("tool", "unknown")
            await self.emit_message(request, AgentMessage(
                text=f"🔧 Using tool: `{tool}`",
                message_type="system"
            ))
        
        elif event_type == "done":
            result = event.get("result", "")
            await self.emit_result(request, result if result else None)
        
        elif event_type == "error":
            error = event.get("error", "Unknown error")
            await self.emit_message(request, AgentMessage(
                text=f"❌ {error}",
                message_type="error"
            ))
    
    async def _terminate_process(self, session_id: str) -> bool:
        """Terminate active process."""
        if session_id not in self._active_processes:
            return False
        
        proc = self._active_processes[session_id]
        try:
            if hasattr(os, "getpgid"):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        
        self._active_processes.pop(session_id, None)
        return True
    
    async def handle_stop(self, request: AgentRequest) -> bool:
        """Stop running Codex process."""
        result = await self._terminate_process(request.session_id)
        if result:
            self.logger.info(f"Codex session {request.session_id} stopped")
        return result
    
    async def clear_sessions(self, session_id: str) -> int:
        """Clear Codex sessions."""
        await self._terminate_process(session_id)
        return await super().clear_sessions(session_id)
