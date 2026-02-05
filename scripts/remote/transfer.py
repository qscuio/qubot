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
