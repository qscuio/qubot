"""JSON output formatting for remote commands."""
import json
from typing import Optional


def format_result(
    host: str,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: int
) -> str:
    """Format command execution result as JSON."""
    return json.dumps({
        "success": exit_code == 0,
        "host": host,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms
    }, indent=2)


def format_error(
    host: str,
    error: str,
    command: Optional[str] = None
) -> str:
    """Format connection/execution error as JSON."""
    result = {
        "success": False,
        "host": host,
        "error": error
    }
    if command:
        result["command"] = command
    return json.dumps(result, indent=2)
