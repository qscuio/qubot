"""
Gemini CLI Agent - Integration with Google's Gemini CLI.

Uses subprocess to communicate with the gemini CLI tool.
"""

import asyncio
import os
import shutil
import signal
from asyncio.subprocess import Process
from typing import Any, Dict, Optional

from app.services.vibe_remote.agents.base import AgentRequest, AgentMessage, BaseCLIAgent


class GeminiAgent(BaseCLIAgent):
    """Gemini CLI integration via subprocess."""
    
    name = "gemini"
    
    def __init__(self, service: Any):
        super().__init__(service)
        self._binary_path: Optional[str] = None
        self._active_processes: Dict[str, Process] = {}
    
    def _find_binary(self) -> Optional[str]:
        """Find the gemini binary."""
        if self._binary_path:
            return self._binary_path
        
        import glob
        
        # Check common locations
        paths = [
            shutil.which("gemini"),
            "/usr/local/bin/gemini",
            "/usr/bin/gemini",
            os.path.expanduser("~/.local/bin/gemini"),
            os.path.expanduser("~/node_modules/.bin/gemini"),
        ]
        
        # Add nvm paths (glob pattern)
        nvm_pattern = os.path.expanduser("~/.nvm/versions/node/*/bin/gemini")
        paths.extend(glob.glob(nvm_pattern))
        
        # Add npm global (root installed)
        paths.extend([
            "/root/.nvm/versions/node/v20.19.6/bin/gemini",
            "/root/node_modules/.bin/gemini",
        ])
        
        for path in paths:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                self._binary_path = path
                self.logger.info(f"Found gemini binary at: {path}")
                return path
        
        return None
    
    def is_available(self) -> bool:
        """Check if gemini CLI is installed."""
        return self._find_binary() is not None
    
    async def handle_message(self, request: AgentRequest) -> None:
        """Process message through Gemini CLI."""
        binary = self._find_binary()
        if not binary:
            await self.emit_message(request, AgentMessage(
                text="❌ Gemini CLI not found. Install with: `npm install -g @google/gemini-cli`",
                message_type="error"
            ))
            return
        
        # Check for existing process
        if request.session_id in self._active_processes:
            proc = self._active_processes[request.session_id]
            if proc.returncode is None:
                await self.emit_message(request, AgentMessage(
                    text="⚠️ A task is already running. Use /stop to cancel it first.",
                    message_type="system"
                ))
                return
        
        # Ensure working directory exists
        if not os.path.exists(request.working_path):
            os.makedirs(request.working_path, exist_ok=True)
        
        # Build command
        cmd = [
            binary,
            "--non-interactive",
            "--cwd", request.working_path,
            request.message
        ]
        
        self.logger.info(f"Executing Gemini: {' '.join(cmd[:-1])} <prompt>")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=request.working_path,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            
            self._active_processes[request.session_id] = process
            self._active_sessions[request.session_id] = {
                "process": process,
                "started_at": request.started_at
            }
            
            # Stream output
            await self._stream_output(process, request)
            
        except FileNotFoundError:
            await self.emit_message(request, AgentMessage(
                text="❌ Failed to start Gemini CLI.",
                message_type="error"
            ))
        except Exception as e:
            self.logger.error(f"Gemini CLI error: {e}")
            await self.emit_message(request, AgentMessage(
                text=f"❌ Gemini error: {e}",
                message_type="error"
            ))
        finally:
            self._active_processes.pop(request.session_id, None)
            self._active_sessions.pop(request.session_id, None)
    
    async def _stream_output(self, process: Process, request: AgentRequest) -> None:
        """Stream stdout and collect stderr."""
        assert process.stdout is not None
        assert process.stderr is not None
        
        output_buffer = []
        
        async def read_stdout():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="ignore").rstrip()
                if decoded:
                    output_buffer.append(decoded)
                    # Emit progressively for long outputs
                    if len(output_buffer) % 10 == 0:
                        await self.emit_message(request, AgentMessage(
                            text=decoded,
                            message_type="assistant"
                        ))
        
        async def read_stderr():
            stderr_lines = []
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="ignore").rstrip()
                if decoded:
                    stderr_lines.append(decoded)
                    self.logger.debug(f"Gemini stderr: {decoded}")
            return stderr_lines
        
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        
        try:
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)
            stderr_lines = stderr_task.result()
            
            # Emit final result
            if output_buffer:
                final_output = "\n".join(output_buffer[-50:])  # Last 50 lines
                await self.emit_result(request, final_output)
            elif stderr_lines:
                await self.emit_message(request, AgentMessage(
                    text=f"❌ Error:\n```\n{chr(10).join(stderr_lines[-10:])}\n```",
                    message_type="error"
                ))
            else:
                await self.emit_result(request, None)
                
        except asyncio.CancelledError:
            await self.emit_result(request, None, subtype="interrupted")
    
    async def handle_stop(self, request: AgentRequest) -> bool:
        """Stop running Gemini process."""
        session_id = request.session_id
        
        if session_id not in self._active_processes:
            return False
        
        proc = self._active_processes[session_id]
        if proc.returncode is not None:
            return False
        
        try:
            if hasattr(os, "getpgid"):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                proc.terminate()
            
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
        except ProcessLookupError:
            pass
        
        self._active_processes.pop(session_id, None)
        self._active_sessions.pop(session_id, None)
        
        self.logger.info(f"Gemini session {session_id} stopped")
        return True
    
    async def clear_sessions(self, session_id: str) -> int:
        """Clear Gemini sessions."""
        await self.handle_stop(AgentRequest(
            user_id=0,
            chat_id=0,
            message="",
            working_path="",
            session_id=session_id
        ))
        return await super().clear_sessions(session_id)
