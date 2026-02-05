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
