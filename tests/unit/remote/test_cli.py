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
