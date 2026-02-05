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
