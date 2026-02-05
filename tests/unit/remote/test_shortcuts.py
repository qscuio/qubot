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
