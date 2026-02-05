"""SSH command execution."""
import time
from typing import Optional, Dict, Any
import paramiko


class SSHConnectionError(Exception):
    """Raised when SSH connection fails."""
    pass


def execute_command(
    host: str,
    user: str,
    command: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Execute a command on a remote host via SSH.

    Args:
        host: Remote hostname or IP
        user: SSH username
        command: Command to execute
        key_path: Path to SSH private key (optional)
        password: SSH password (optional)
        port: SSH port (default: 22)
        timeout: Command timeout in seconds (default: 30)

    Returns:
        Dict with success, exit_code, stdout, stderr, duration_ms

    Raises:
        SSHConnectionError: If connection fails
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_args = {
        "hostname": host,
        "username": user,
        "port": port,
        "timeout": timeout
    }

    if key_path:
        connect_args["key_filename"] = key_path
    elif password:
        connect_args["password"] = password

    try:
        start_time = time.time()
        client.connect(**connect_args)

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()

        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout.read().decode(),
            "stderr": stderr.read().decode(),
            "duration_ms": duration_ms
        }
    except Exception as e:
        raise SSHConnectionError(f"Failed to connect to {host}: {e}")
    finally:
        client.close()
