"""
Vibe Remote Service - Remote AI coding agent control via Telegram.

Supports multiple CLI agents:
- Claude Code (claude_code_sdk)
- Gemini CLI (subprocess)
- Codex (JSON streaming)

Also includes Git operations and GitHub Actions integration.
"""

from app.services.vibe_remote.service import vibe_remote_service

__all__ = ["vibe_remote_service"]
