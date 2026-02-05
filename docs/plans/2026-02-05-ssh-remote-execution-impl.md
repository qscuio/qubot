# SSH Remote Execution Toolkit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI module for executing commands, transferring files, and managing services on remote VPS servers via SSH with structured JSON output.

**Architecture:** Python module using paramiko for SSH operations, typer for CLI. All commands output JSON with success/failure status. Predefined shortcuts for common tasks (deploy, logs, status, restart).

**Tech Stack:** Python 3.10+, paramiko, typer

---

## Task 1: Project Setup

**Files:**
- Create: `scripts/remote/__init__.py`
- Create: `scripts/remote/__main__.py`
- Modify: `requirements.txt`
- Create: `tests/unit/remote/__init__.py`

**Step 1: Create remote package directory**

```bash
mkdir -p scripts/remote tests/unit/remote
```

**Step 2: Add dependencies to requirements.txt**

Add these lines to `requirements.txt`:
```
paramiko>=3.0.0
typer>=0.9.0
```

**Step 3: Create package init files**

`scripts/remote/__init__.py`:
```python
"""SSH remote execution toolkit."""
```

`scripts/remote/__main__.py`:
```python
"""Entry point for python -m scripts.remote"""
from scripts.remote.cli import app

if __name__ == "__main__":
    app()
```

`tests/unit/remote/__init__.py`:
```python
"""Tests for remote execution toolkit."""
```

**Step 4: Install dependencies**

```bash
pip install paramiko typer
```

**Step 5: Commit**

```bash
git add scripts/remote/ tests/unit/remote/ requirements.txt
git commit -m "feat(remote): initialize SSH remote execution module"
```

---

## Task 2: Output Formatter

**Files:**
- Create: `scripts/remote/output.py`
- Create: `tests/unit/remote/test_output.py`

**Step 1: Write the failing test**

`tests/unit/remote/test_output.py`:
```python
"""Tests for output formatting."""
import json
import pytest
from scripts.remote.output import format_result, format_error


def test_format_result_success():
    result = format_result(
        host="192.168.1.10",
        command="whoami",
        exit_code=0,
        stdout="ubuntu\n",
        stderr="",
        duration_ms=123
    )
    data = json.loads(result)
    assert data["success"] is True
    assert data["host"] == "192.168.1.10"
    assert data["command"] == "whoami"
    assert data["exit_code"] == 0
    assert data["stdout"] == "ubuntu\n"
    assert data["stderr"] == ""
    assert data["duration_ms"] == 123


def test_format_result_failure():
    result = format_result(
        host="192.168.1.10",
        command="badcmd",
        exit_code=127,
        stdout="",
        stderr="command not found",
        duration_ms=50
    )
    data = json.loads(result)
    assert data["success"] is False
    assert data["exit_code"] == 127


def test_format_error():
    result = format_error(
        host="192.168.1.10",
        error="Connection refused"
    )
    data = json.loads(result)
    assert data["success"] is False
    assert data["host"] == "192.168.1.10"
    assert data["error"] == "Connection refused"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/remote/test_output.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'scripts.remote.output'"

**Step 3: Write minimal implementation**

`scripts/remote/output.py`:
```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/remote/test_output.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/remote/output.py tests/unit/remote/test_output.py
git commit -m "feat(remote): add JSON output formatter"
```

---

## Task 3: SSH Executor

**Files:**
- Create: `scripts/remote/executor.py`
- Create: `tests/unit/remote/test_executor.py`

**Step 1: Write the failing test**

`tests/unit/remote/test_executor.py`:
```python
"""Tests for SSH executor."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from scripts.remote.executor import execute_command, SSHConnectionError


@pytest.fixture
def mock_ssh_client():
    """Create a mock SSH client."""
    with patch('scripts.remote.executor.paramiko.SSHClient') as mock:
        client_instance = MagicMock()
        mock.return_value = client_instance

        # Mock stdout/stderr
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"output\n"
        mock_stdout.channel.recv_exit_status.return_value = 0

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""

        client_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        yield client_instance


def test_execute_command_with_key(mock_ssh_client):
    result = execute_command(
        host="192.168.1.10",
        user="ubuntu",
        command="whoami",
        key_path="/home/user/.ssh/id_rsa"
    )

    assert result["success"] is True
    assert result["stdout"] == "output\n"
    assert result["exit_code"] == 0
    mock_ssh_client.connect.assert_called_once()


def test_execute_command_with_password(mock_ssh_client):
    result = execute_command(
        host="192.168.1.10",
        user="ubuntu",
        command="whoami",
        password="secret"
    )

    assert result["success"] is True
    mock_ssh_client.connect.assert_called_once()
    call_kwargs = mock_ssh_client.connect.call_args[1]
    assert call_kwargs["password"] == "secret"


def test_execute_command_connection_error():
    with patch('scripts.remote.executor.paramiko.SSHClient') as mock:
        client_instance = MagicMock()
        mock.return_value = client_instance
        client_instance.connect.side_effect = Exception("Connection refused")

        with pytest.raises(SSHConnectionError) as exc:
            execute_command(
                host="192.168.1.10",
                user="ubuntu",
                command="whoami"
            )
        assert "Connection refused" in str(exc.value)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/remote/test_executor.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

`scripts/remote/executor.py`:
```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/remote/test_executor.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/remote/executor.py tests/unit/remote/test_executor.py
git commit -m "feat(remote): add SSH command executor"
```

---

## Task 4: File Transfer

**Files:**
- Create: `scripts/remote/transfer.py`
- Create: `tests/unit/remote/test_transfer.py`

**Step 1: Write the failing test**

`tests/unit/remote/test_transfer.py`:
```python
"""Tests for file transfer."""
import pytest
from unittest.mock import MagicMock, patch
from scripts.remote.transfer import upload_file, download_file, TransferError


@pytest.fixture
def mock_sftp():
    """Create mock SSH and SFTP clients."""
    with patch('scripts.remote.transfer.paramiko.SSHClient') as mock:
        client_instance = MagicMock()
        mock.return_value = client_instance

        sftp_instance = MagicMock()
        client_instance.open_sftp.return_value = sftp_instance

        yield sftp_instance, client_instance


def test_upload_file(mock_sftp):
    sftp, client = mock_sftp

    result = upload_file(
        host="192.168.1.10",
        user="ubuntu",
        local_path="/tmp/test.txt",
        remote_path="/home/ubuntu/test.txt",
        key_path="/home/user/.ssh/id_rsa"
    )

    assert result["success"] is True
    assert result["operation"] == "upload"
    sftp.put.assert_called_once_with("/tmp/test.txt", "/home/ubuntu/test.txt")


def test_download_file(mock_sftp):
    sftp, client = mock_sftp

    result = download_file(
        host="192.168.1.10",
        user="ubuntu",
        remote_path="/home/ubuntu/test.txt",
        local_path="/tmp/test.txt",
        key_path="/home/user/.ssh/id_rsa"
    )

    assert result["success"] is True
    assert result["operation"] == "download"
    sftp.get.assert_called_once_with("/home/ubuntu/test.txt", "/tmp/test.txt")


def test_upload_file_error(mock_sftp):
    sftp, client = mock_sftp
    sftp.put.side_effect = Exception("Permission denied")

    with pytest.raises(TransferError) as exc:
        upload_file(
            host="192.168.1.10",
            user="ubuntu",
            local_path="/tmp/test.txt",
            remote_path="/root/test.txt"
        )
    assert "Permission denied" in str(exc.value)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/remote/test_transfer.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

`scripts/remote/transfer.py`:
```python
"""File transfer via SFTP."""
import time
from typing import Optional, Dict, Any
import paramiko


class TransferError(Exception):
    """Raised when file transfer fails."""
    pass


def _get_sftp_client(
    host: str,
    user: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
):
    """Create SSH client and return SFTP client."""
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

    client.connect(**connect_args)
    return client, client.open_sftp()


def upload_file(
    host: str,
    user: str,
    local_path: str,
    remote_path: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """Upload a file to remote host."""
    client = None
    try:
        start_time = time.time()
        client, sftp = _get_sftp_client(host, user, key_path, password, port, timeout)
        sftp.put(local_path, remote_path)
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "host": host,
            "operation": "upload",
            "local_path": local_path,
            "remote_path": remote_path,
            "duration_ms": duration_ms
        }
    except Exception as e:
        raise TransferError(f"Upload failed: {e}")
    finally:
        if client:
            client.close()


def download_file(
    host: str,
    user: str,
    remote_path: str,
    local_path: str,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Dict[str, Any]:
    """Download a file from remote host."""
    client = None
    try:
        start_time = time.time()
        client, sftp = _get_sftp_client(host, user, key_path, password, port, timeout)
        sftp.get(remote_path, local_path)
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "host": host,
            "operation": "download",
            "remote_path": remote_path,
            "local_path": local_path,
            "duration_ms": duration_ms
        }
    except Exception as e:
        raise TransferError(f"Download failed: {e}")
    finally:
        if client:
            client.close()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/remote/test_transfer.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/remote/transfer.py tests/unit/remote/test_transfer.py
git commit -m "feat(remote): add SFTP file transfer"
```

---

## Task 5: Predefined Shortcuts

**Files:**
- Create: `scripts/remote/shortcuts.py`
- Create: `tests/unit/remote/test_shortcuts.py`

**Step 1: Write the failing test**

`tests/unit/remote/test_shortcuts.py`:
```python
"""Tests for predefined shortcuts."""
import pytest
from unittest.mock import patch, MagicMock
from scripts.remote.shortcuts import (
    deploy, get_logs, get_status, restart_service
)


@pytest.fixture
def mock_execute():
    """Mock the execute_command function."""
    with patch('scripts.remote.shortcuts.execute_command') as mock:
        mock.return_value = {
            "success": True,
            "exit_code": 0,
            "stdout": "ok\n",
            "stderr": "",
            "duration_ms": 100
        }
        yield mock


def test_deploy(mock_execute):
    result = deploy(
        host="192.168.1.10",
        user="ubuntu",
        path="/var/www/app",
        service="app"
    )

    assert result["success"] is True
    assert "steps" in result
    assert len(result["steps"]) >= 2  # git pull + restart


def test_get_logs(mock_execute):
    result = get_logs(
        host="192.168.1.10",
        user="ubuntu",
        service="nginx",
        lines=50
    )

    assert result["success"] is True
    mock_execute.assert_called_once()
    call_args = mock_execute.call_args
    assert "journalctl" in call_args[1]["command"] or "tail" in call_args[1]["command"]


def test_get_status(mock_execute):
    mock_execute.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       50G   20G   30G  40% /\n",
        "stderr": "",
        "duration_ms": 100
    }

    result = get_status(
        host="192.168.1.10",
        user="ubuntu"
    )

    assert result["success"] is True
    assert "disk" in result or "stdout" in result


def test_restart_service(mock_execute):
    result = restart_service(
        host="192.168.1.10",
        user="ubuntu",
        service="nginx"
    )

    assert result["success"] is True
    call_args = mock_execute.call_args
    assert "systemctl restart nginx" in call_args[1]["command"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/remote/test_shortcuts.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

`scripts/remote/shortcuts.py`:
```python
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/remote/test_shortcuts.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/remote/shortcuts.py tests/unit/remote/test_shortcuts.py
git commit -m "feat(remote): add predefined shortcuts (deploy, logs, status, restart)"
```

---

## Task 6: CLI Interface

**Files:**
- Create: `scripts/remote/cli.py`
- Create: `tests/unit/remote/test_cli.py`

**Step 1: Write the failing test**

`tests/unit/remote/test_cli.py`:
```python
"""Tests for CLI interface."""
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from scripts.remote.cli import app

runner = CliRunner()


@pytest.fixture
def mock_execute():
    with patch('scripts.remote.cli.execute_command') as mock:
        mock.return_value = {
            "success": True,
            "exit_code": 0,
            "stdout": "hello\n",
            "stderr": "",
            "duration_ms": 100
        }
        yield mock


def test_exec_command(mock_execute):
    result = runner.invoke(app, [
        "exec",
        "--host", "192.168.1.10",
        "--user", "ubuntu",
        "--key", "/home/user/.ssh/id_rsa",
        "whoami"
    ])

    assert result.exit_code == 0
    assert "success" in result.stdout
    mock_execute.assert_called_once()


def test_exec_missing_host():
    result = runner.invoke(app, [
        "exec",
        "--user", "ubuntu",
        "whoami"
    ])

    assert result.exit_code != 0


@patch('scripts.remote.cli.upload_file')
def test_upload_command(mock_upload):
    mock_upload.return_value = {
        "success": True,
        "operation": "upload",
        "duration_ms": 200
    }

    result = runner.invoke(app, [
        "upload",
        "--host", "192.168.1.10",
        "--user", "ubuntu",
        "/tmp/local.txt",
        "/home/ubuntu/remote.txt"
    ])

    assert result.exit_code == 0
    mock_upload.assert_called_once()


@patch('scripts.remote.cli.get_status')
def test_status_command(mock_status):
    mock_status.return_value = {
        "success": True,
        "operation": "status",
        "stdout": "disk info..."
    }

    result = runner.invoke(app, [
        "status",
        "--host", "192.168.1.10",
        "--user", "ubuntu"
    ])

    assert result.exit_code == 0
    mock_status.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/remote/test_cli.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

`scripts/remote/cli.py`:
```python
"""CLI interface for remote execution toolkit."""
import json
import getpass
from typing import Optional
import typer

from scripts.remote.executor import execute_command, SSHConnectionError
from scripts.remote.transfer import upload_file, download_file, TransferError
from scripts.remote.shortcuts import deploy, get_logs, get_status, restart_service
from scripts.remote.output import format_result, format_error

app = typer.Typer(help="SSH remote execution toolkit")


def get_auth_args(key: Optional[str], password: bool) -> dict:
    """Build authentication arguments."""
    if password:
        pwd = getpass.getpass("SSH Password: ")
        return {"password": pwd}
    elif key:
        return {"key_path": key}
    return {}


@app.command()
def exec(
    command: str = typer.Argument(..., help="Command to execute"),
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only show stdout/stderr"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show connection details")
):
    """Execute a command on remote host."""
    auth = get_auth_args(key, password)

    if verbose:
        typer.echo(f"Connecting to {user}@{host}:{port}...")

    try:
        result = execute_command(
            host=host, user=user, command=command,
            port=port, timeout=timeout, **auth
        )

        if quiet:
            typer.echo(result["stdout"], nl=False)
            if result["stderr"]:
                typer.echo(result["stderr"], nl=False, err=True)
        else:
            output = format_result(
                host=host, command=command,
                exit_code=result["exit_code"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                duration_ms=result["duration_ms"]
            )
            typer.echo(output)

        raise typer.Exit(result["exit_code"])
    except SSHConnectionError as e:
        typer.echo(format_error(host=host, error=str(e), command=command), err=True)
        raise typer.Exit(1)


@app.command()
def upload(
    local_path: str = typer.Argument(..., help="Local file path"),
    remote_path: str = typer.Argument(..., help="Remote file path"),
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds")
):
    """Upload a file to remote host."""
    auth = get_auth_args(key, password)

    try:
        result = upload_file(
            host=host, user=user,
            local_path=local_path, remote_path=remote_path,
            port=port, timeout=timeout, **auth
        )
        typer.echo(json.dumps(result, indent=2))
    except TransferError as e:
        typer.echo(format_error(host=host, error=str(e)), err=True)
        raise typer.Exit(1)


@app.command()
def download(
    remote_path: str = typer.Argument(..., help="Remote file path"),
    local_path: str = typer.Argument(..., help="Local file path"),
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds")
):
    """Download a file from remote host."""
    auth = get_auth_args(key, password)

    try:
        result = download_file(
            host=host, user=user,
            remote_path=remote_path, local_path=local_path,
            port=port, timeout=timeout, **auth
        )
        typer.echo(json.dumps(result, indent=2))
    except TransferError as e:
        typer.echo(format_error(host=host, error=str(e)), err=True)
        raise typer.Exit(1)


@app.command(name="deploy")
def deploy_cmd(
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    path: str = typer.Option("/var/www/app", "--path", help="App directory"),
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Service to restart"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in seconds")
):
    """Deploy: git pull, install deps, restart service."""
    auth = get_auth_args(key, password)

    result = deploy(
        host=host, user=user, path=path, service=service,
        port=port, timeout=timeout, **auth
    )
    typer.echo(json.dumps(result, indent=2))
    raise typer.Exit(0 if result["success"] else 1)


@app.command(name="logs")
def logs_cmd(
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    service: str = typer.Option("nginx", "--service", "-s", help="Service name"),
    lines: int = typer.Option(100, "--lines", "-n", help="Number of lines"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds")
):
    """Get recent logs for a service."""
    auth = get_auth_args(key, password)

    result = get_logs(
        host=host, user=user, service=service, lines=lines,
        port=port, timeout=timeout, **auth
    )
    typer.echo(json.dumps(result, indent=2))


@app.command(name="status")
def status_cmd(
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds")
):
    """Get system status: disk, memory, load."""
    auth = get_auth_args(key, password)

    result = get_status(
        host=host, user=user,
        port=port, timeout=timeout, **auth
    )
    typer.echo(json.dumps(result, indent=2))


@app.command(name="restart")
def restart_cmd(
    host: str = typer.Option(..., "--host", "-h", help="Remote host"),
    user: str = typer.Option(..., "--user", "-u", help="SSH username"),
    service: str = typer.Option(..., "--service", "-s", help="Service to restart"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="SSH key path"),
    password: bool = typer.Option(False, "--password", "-p", help="Prompt for password"),
    port: int = typer.Option(22, "--port", help="SSH port"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds")
):
    """Restart a systemd service."""
    auth = get_auth_args(key, password)

    result = restart_service(
        host=host, user=user, service=service,
        port=port, timeout=timeout, **auth
    )
    typer.echo(json.dumps(result, indent=2))
    raise typer.Exit(0 if result["success"] else 1)


if __name__ == "__main__":
    app()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/remote/test_cli.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/remote/cli.py tests/unit/remote/test_cli.py scripts/remote/__main__.py
git commit -m "feat(remote): add typer CLI interface"
```

---

## Task 7: Integration Test

**Files:**
- Update: `scripts/remote/__main__.py`

**Step 1: Run all tests**

```bash
pytest tests/unit/remote/ -v
```
Expected: All PASS

**Step 2: Test CLI help**

```bash
python -m scripts.remote --help
python -m scripts.remote exec --help
```
Expected: Shows help text

**Step 3: Commit final state**

```bash
git add -A
git commit -m "feat(remote): complete SSH remote execution toolkit"
```

---

## Task 8: Create Skill Document (TDD for Skills)

**Files:**
- Create: `~/.claude/skills/ssh-remote-execution/SKILL.md`

**Step 1: Run baseline test WITHOUT skill**

Dispatch a subagent with this prompt (no skill loaded):
> "Connect to server 192.168.1.10 as ubuntu and check disk space"

Document how the agent approaches this without the skill.

**Step 2: Write the skill**

`~/.claude/skills/ssh-remote-execution/SKILL.md`:
```markdown
---
name: ssh-remote-execution
description: Use when needing to execute commands, transfer files, or manage services on remote VPS servers via SSH
---

# SSH Remote Execution

## Overview

Python CLI toolkit for remote server management via SSH. All commands output structured JSON for easy parsing.

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `exec` | Run any command | `remote exec -h HOST -u USER "df -h"` |
| `upload` | Upload file | `remote upload -h HOST -u USER local.txt /tmp/remote.txt` |
| `download` | Download file | `remote download -h HOST -u USER /tmp/remote.txt local.txt` |
| `deploy` | Git pull + restart | `remote deploy -h HOST -u USER --service app` |
| `logs` | View service logs | `remote logs -h HOST -u USER --service nginx` |
| `status` | System health | `remote status -h HOST -u USER` |
| `restart` | Restart service | `remote restart -h HOST -u USER --service nginx` |

## Authentication

```bash
# SSH key (recommended)
remote exec -h HOST -u USER -k ~/.ssh/id_rsa "command"

# Password (prompts securely)
remote exec -h HOST -u USER -p "command"

# Default (uses SSH agent or ~/.ssh/id_rsa)
remote exec -h HOST -u USER "command"
```

## Output Format

All commands return JSON:
```json
{
  "success": true,
  "host": "192.168.1.10",
  "exit_code": 0,
  "stdout": "...",
  "stderr": ""
}
```

## Common Workflows

**Check server health:**
```bash
remote status -h 192.168.1.10 -u ubuntu
```

**Deploy application:**
```bash
remote deploy -h 192.168.1.10 -u ubuntu --path /var/www/app --service myapp
```

**Debug service:**
```bash
remote logs -h 192.168.1.10 -u ubuntu --service nginx --lines 200
```

## Error Handling

| Error | Meaning | Fix |
|-------|---------|-----|
| Connection refused | SSH not running or blocked | Check firewall, SSH service |
| Auth failed | Bad key/password | Verify credentials |
| Timeout | Command took too long | Increase --timeout |
| Permission denied | No sudo access | Add user to sudoers |

## Security Notes

- Never pass passwords on command line (use -p flag for prompt)
- Use SSH keys when possible
- Avoid storing credentials in scripts
```

**Step 3: Verify skill works**

Dispatch same subagent prompt WITH skill loaded. Verify it uses the toolkit correctly.

**Step 4: Close loopholes**

If agent made mistakes, update skill to address them. Re-test.

**Step 5: Commit skill**

```bash
mkdir -p ~/.claude/skills/ssh-remote-execution
# Copy SKILL.md content
git -C ~/.claude/skills add ssh-remote-execution/
git -C ~/.claude/skills commit -m "feat: add ssh-remote-execution skill"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Project setup (directories, dependencies) |
| 2 | Output formatter (JSON formatting) |
| 3 | SSH executor (paramiko command execution) |
| 4 | File transfer (SFTP upload/download) |
| 5 | Predefined shortcuts (deploy, logs, status, restart) |
| 6 | CLI interface (typer commands) |
| 7 | Integration test |
| 8 | Skill document (TDD approach) |
