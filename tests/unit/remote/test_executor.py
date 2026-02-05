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
