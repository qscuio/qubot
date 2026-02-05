"""Predefined shortcuts for common remote tasks."""
from typing import Optional, Dict, Any, List
from scripts.remote.executor import execute_command


def deploy(
    host: str,
    user: str,
    path: str = "/var/www/app",
    service: Optional[str] = None,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 60
) -> Dict[str, Any]:
    """
    Deploy: git pull, install deps, restart service.

    Steps:
    1. cd to path and git pull
    2. pip install -r requirements.txt (if exists)
    3. systemctl restart service (if provided)
    """
    auth = {"key_path": key_path, "password": password, "port": port, "timeout": timeout}
    steps: List[Dict[str, Any]] = []
    overall_success = True

    # Step 1: Git pull
    result = execute_command(
        host=host, user=user,
        command=f"cd {path} && git pull",
        **auth
    )
    steps.append({"name": "git_pull", **result})
    if not result["success"]:
        overall_success = False

    # Step 2: Install deps (optional, ignore if no requirements.txt)
    result = execute_command(
        host=host, user=user,
        command=f"cd {path} && [ -f requirements.txt ] && pip install -r requirements.txt || true",
        **auth
    )
    steps.append({"name": "install_deps", **result})

    # Step 3: Restart service
    if service:
        result = execute_command(
            host=host, user=user,
            command=f"sudo systemctl restart {service}",
            **auth
        )
        steps.append({"name": "restart_service", **result})
        if not result["success"]:
            overall_success = False

    return {
        "success": overall_success,
        "host": host,
        "operation": "deploy",
        "path": path,
        "service": service,
        "steps": steps
    }


def get_logs(
    host: str,
    user: str,
    service: str = "nginx",
    lines: int = 100,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """Get recent logs for a service."""
    auth = {"key_path": key_path, "password": password, "port": port, "timeout": timeout}

    result = execute_command(
        host=host, user=user,
        command=f"journalctl -u {service} -n {lines} --no-pager 2>/dev/null || tail -n {lines} /var/log/{service}/error.log 2>/dev/null || tail -n {lines} /var/log/{service}.log 2>/dev/null || echo 'No logs found for {service}'",
        **auth
    )

    return {
        "success": result["success"],
        "host": host,
        "operation": "logs",
        "service": service,
        "lines": lines,
        "stdout": result["stdout"],
        "stderr": result["stderr"]
    }


def get_status(
    host: str,
    user: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """Get system status: disk, memory, load, uptime."""
    auth = {"key_path": key_path, "password": password, "port": port, "timeout": timeout}

    # Combined command for efficiency
    result = execute_command(
        host=host, user=user,
        command="echo '=== DISK ===' && df -h && echo '=== MEMORY ===' && free -m && echo '=== LOAD ===' && uptime && echo '=== SERVICES ===' && (systemctl is-active nginx postgresql redis 2>/dev/null || true)",
        **auth
    )

    return {
        "success": result["success"],
        "host": host,
        "operation": "status",
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "duration_ms": result["duration_ms"]
    }


def restart_service(
    host: str,
    user: str,
    service: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """Restart a systemd service and show its status."""
    auth = {"key_path": key_path, "password": password, "port": port, "timeout": timeout}

    result = execute_command(
        host=host, user=user,
        command=f"sudo systemctl restart {service} && systemctl status {service} --no-pager",
        **auth
    )

    return {
        "success": result["success"],
        "host": host,
        "operation": "restart",
        "service": service,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "duration_ms": result["duration_ms"]
    }
