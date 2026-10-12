"""Tests for qubopy CLI and security protections."""

import argparse
import base64
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from qubopy.cli import _cmd_tokens, _cmd_verify_otp, _secure_write_text
from qubopy.models import BleLockCredentials, RtspStreamInfo, TokenPayload


@pytest.mark.asyncio
async def test_verify_otp_without_pending_file_no_unbound_error(tmp_path):
    """Bug 1: verify-otp should not crash with UnboundLocalError when pending file is absent."""
    non_existent = tmp_path / "does_not_exist.json"
    args = argparse.Namespace(
        phone="9876543210",
        isd="+91",
        session_uuid="sess-uuid-1234",
        otp="123456",
        device_name="TestDevice",
        profile_index=0,
        account_uuid=None,
    )

    with (
        patch("qubopy.cli.SESSION_TEMP_FILE", non_existent),
        patch("qubopy.cli.QuboAuth") as mock_auth_cls,
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.get_phone_otp_profiles = AsyncMock(
            return_value=[{"name": "User", "uuid": "u-1"}]
        )
        mock_auth.verify_phone_otp = AsyncMock(
            return_value=TokenPayload(
                accessToken="tok",
                refreshToken=None,
                uuid="u-1",
            )
        )
        mock_auth.close = AsyncMock()

        with patch("qubopy.cli._save_session"):
            code = await _cmd_verify_otp(args)
            assert code == 0


def test_models_repr_conceals_secrets():
    """Verify that credentials and secret keys are hidden from model repr."""
    tokens = TokenPayload(
        accessToken="secret_access_jwt_token",
        refreshToken="secret_refresh_token",
        uuid="user-123",
    )
    assert "secret_access_jwt_token" not in repr(tokens)
    assert "secret_refresh_token" not in repr(tokens)
    assert "user-123" in repr(tokens)

    ble = BleLockCredentials(
        device_uuid="lock-uuid",
        device_name="Main Door Lock",
        mac_address="AA:BB:CC:DD:EE:FF",
        auth_key="super_secret_auth_key",
        offline_key="super_secret_offline_key",
        admin_pass="master_passcode_9999",
    )
    assert "super_secret_auth_key" not in repr(ble)
    assert "super_secret_offline_key" not in repr(ble)
    assert "master_passcode_9999" not in repr(ble)
    assert "Main Door Lock" in repr(ble)

    stream = RtspStreamInfo(
        device_uuid="cam-uuid",
        is_supported=True,
        stream_url="rtsp://10.0.0.1/live",
        auth_required=True,
        username="admin",
        password="camera_secret_password",
    )
    assert "camera_secret_password" not in repr(stream)
    assert "admin" in repr(stream)


def test_secure_write_text(tmp_path):
    """Verify _secure_write_text successfully writes content."""
    target_file = tmp_path / "secure_session.json"
    _secure_write_text(target_file, '{"test": true}')
    assert target_file.read_text(encoding="utf-8") == '{"test": true}'


def test_cmd_tokens_no_session(tmp_path, capsys):
    """Verify _cmd_tokens returns error code 1 when no session file exists."""
    non_existent = tmp_path / "absent_session.json"
    args = argparse.Namespace(json=False, show_secrets=False)
    with patch("qubopy.cli.TOKEN_FILE", non_existent):
        ret = _cmd_tokens(args)
        assert ret == 1
        captured = capsys.readouterr()
        assert "No active session found" in captured.err


def test_cmd_tokens_active_session(tmp_path, capsys):
    """Verify _cmd_tokens prints masked active session info and expiration."""
    session_file = tmp_path / "valid_session.json"
    future_exp = int(time.time() + 1800)
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps({"exp": future_exp, "user": "u-456"}).encode())
        .decode()
        .rstrip("=")
    )
    fake_jwt = f"header.{payload_b64}.signature"
    session_data = {
        "accessToken": fake_jwt,
        "refreshToken": "ref-tok-long-secret-key-12345",
        "uuid": "u-456",
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    args = argparse.Namespace(json=False, show_secrets=False)
    with patch("qubopy.cli.TOKEN_FILE", session_file):
        ret = _cmd_tokens(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "User UUID     : u-456" in captured.out
        assert "Active" in captured.out
        assert "Email (Continuous / Refreshable)" in captured.out
        assert "header." in captured.out
        assert "ref-tok-long-secret-key-12345" not in captured.out


def test_cmd_tokens_show_secrets(tmp_path, capsys):
    """Verify _cmd_tokens with --show-secrets prints full unmasked tokens."""
    session_file = tmp_path / "valid_session.json"
    session_data = {
        "accessToken": "header.payload.unmasked_secret_signature",
        "refreshToken": "unmasked_secret_refresh_token",
        "uuid": "u-456",
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    args = argparse.Namespace(json=False, show_secrets=True)
    with patch("qubopy.cli.TOKEN_FILE", session_file):
        ret = _cmd_tokens(args)
        assert ret == 0
        captured = capsys.readouterr()
        assert "unmasked_secret_signature" in captured.out
        assert "unmasked_secret_refresh_token" in captured.out


def test_cmd_tokens_json(tmp_path, capsys):
    """Verify _cmd_tokens with --json outputs valid JSON matching session."""
    session_file = tmp_path / "valid_session.json"
    session_data = {
        "accessToken": "jwt-tok-123",
        "refreshToken": None,
        "uuid": "u-999",
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    args = argparse.Namespace(json=True, show_secrets=False)
    with patch("qubopy.cli.TOKEN_FILE", session_file):
        ret = _cmd_tokens(args)
        assert ret == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["accessToken"] == "jwt-tok-123"
        assert parsed["uuid"] == "u-999"
