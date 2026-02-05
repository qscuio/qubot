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
