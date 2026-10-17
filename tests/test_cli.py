"""Tests for qubopy CLI and security protections."""

import argparse
import base64
import json
import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

from qubopy.auth import QuboAuth
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
        mock_auth.get_phone_otp_profiles = AsyncMock(return_value=[{"name": "User", "uuid": "u-1"}])
        mock_auth.find_profile_index = QuboAuth.find_profile_index
        mock_auth.select_profile.return_value = TokenPayload(
            accessToken="tok",
            refreshToken=None,
            uuid="u-1",
        )
        mock_auth.close = AsyncMock()

        with patch("qubopy.cli._save_session"):
            code = await _cmd_verify_otp(args)
            assert code == 0


@pytest.mark.asyncio
async def test_cmd_login_phone_single_verify_call(monkeypatch):
    """Ensure interactive phone login verifies OTP exactly once across multiple profiles."""
    from qubopy.cli import _cmd_login_phone

    args = argparse.Namespace(
        phone="9876543210",
        isd="+91",
        device_name="TestDevice",
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    inputs = iter(["123456", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    with patch("qubopy.cli.QuboAuth") as mock_auth_cls:
        mock_auth = mock_auth_cls.return_value
        mock_auth.request_phone_otp = AsyncMock(return_value={"uuid": "sess-123"})
        mock_auth.get_phone_otp_profiles = AsyncMock(
            return_value=[
                {"name": "Profile0", "uuid": "u-0", "email": "p0@test.com"},
                {"name": "Profile1", "uuid": "u-1", "email": "p1@test.com"},
            ]
        )
        mock_auth.find_profile_index = QuboAuth.find_profile_index
        mock_auth.select_profile.return_value = TokenPayload(
            accessToken="tok-1",
            refreshToken=None,
            uuid="u-1",
        )
        mock_auth.close = AsyncMock()

        with patch("qubopy.cli._save_session") as mock_save:
            code = await _cmd_login_phone(args)
            assert code == 0
            mock_auth.get_phone_otp_profiles.assert_awaited_once()
            mock_auth.select_profile.assert_called_once()
            assert mock_auth.select_profile.call_args[1]["profile_index"] == 1
            mock_save.assert_called_once_with(
                {
                    "accessToken": "tok-1",
                    "refreshToken": None,
                    "uuid": "u-1",
                    "email": "p1@test.com",
                }
            )


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


def test_cmd_tokens_json_masks_tokens_by_default(tmp_path, capsys):
    """Verify --json masks tokens unless --show-secrets is passed."""
    session_file = tmp_path / "valid_session.json"
    session_data = {
        "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoidS0xIn0.sig1234567890",
        "refreshToken": "secret_refresh_token_abcdef123456",
        "uuid": "u-1",
        "email": "user@test.com",
    }
    session_file.write_text(json.dumps(session_data), encoding="utf-8")

    # 1. Without --show-secrets (masked)
    args_masked = argparse.Namespace(json=True, show_secrets=False)
    with patch("qubopy.cli.TOKEN_FILE", session_file):
        ret = _cmd_tokens(args_masked)
        assert ret == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "..." in parsed["accessToken"]
        assert "1234567890" in parsed["accessToken"]
        assert parsed["accessToken"] != session_data["accessToken"]
        assert "..." in parsed["refreshToken"]
        assert parsed["refreshToken"] != session_data["refreshToken"]
        assert parsed["email"] == "user@test.com"

    # 2. With --show-secrets (unmasked)
    args_unmasked = argparse.Namespace(json=True, show_secrets=True)
    with patch("qubopy.cli.TOKEN_FILE", session_file):
        ret = _cmd_tokens(args_unmasked)
        assert ret == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["accessToken"] == session_data["accessToken"]
        assert parsed["refreshToken"] == session_data["refreshToken"]


@pytest.mark.asyncio
async def test_cmd_verify_otp_account_uuid_saves_correct_email(tmp_path):
    """Verify selecting profile by account_uuid saves the matching profile's email."""
    session_file = tmp_path / "test_session.json"
    args = argparse.Namespace(
        phone="9876543210",
        isd="+91",
        session_uuid="sess-uuid-1234",
        otp="123456",
        device_name="TestDevice",
        profile_index=None,
        account_uuid="u-1",
    )

    profiles = [
        {"name": "User0", "uuid": "u-0", "email": "zero@test.com", "accessToken": "tok-0"},
        {"name": "User1", "uuid": "u-1", "email": "one@test.com", "accessToken": "tok-1"},
    ]

    with (
        patch("qubopy.cli.TOKEN_FILE", session_file),
        patch("qubopy.cli.SESSION_TEMP_FILE", tmp_path / "no_pending.json"),
        patch("qubopy.cli.QuboAuth") as mock_auth_cls,
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.get_phone_otp_profiles = AsyncMock(return_value=profiles)
        mock_auth.find_profile_index = QuboAuth.find_profile_index
        mock_auth.select_profile = QuboAuth().select_profile
        mock_auth.close = AsyncMock()

        code = await _cmd_verify_otp(args)
        assert code == 0
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        assert saved["uuid"] == "u-1"
        assert saved["email"] == "one@test.com"


@pytest.mark.asyncio
async def test_cmd_verify_otp_profile_index_saves_correct_email(tmp_path):
    """Verify selecting profile by profile_index saves the matching profile's email."""
    session_file = tmp_path / "test_session.json"
    args = argparse.Namespace(
        phone="9876543210",
        isd="+91",
        session_uuid="sess-uuid-1234",
        otp="123456",
        device_name="TestDevice",
        profile_index=1,
        account_uuid=None,
    )

    profiles = [
        {"name": "User0", "uuid": "u-0", "email": "zero@test.com", "accessToken": "tok-0"},
        {"name": "User1", "uuid": "u-1", "email": "one@test.com", "accessToken": "tok-1"},
    ]

    with (
        patch("qubopy.cli.TOKEN_FILE", session_file),
        patch("qubopy.cli.SESSION_TEMP_FILE", tmp_path / "no_pending.json"),
        patch("qubopy.cli.QuboAuth") as mock_auth_cls,
    ):
        mock_auth = mock_auth_cls.return_value
        mock_auth.get_phone_otp_profiles = AsyncMock(return_value=profiles)
        mock_auth.find_profile_index = QuboAuth.find_profile_index
        mock_auth.select_profile = QuboAuth().select_profile
        mock_auth.close = AsyncMock()

        code = await _cmd_verify_otp(args)
        assert code == 0
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        assert saved["uuid"] == "u-1"
        assert saved["email"] == "one@test.com"


def test_cli_debug_flag_configures_logging():
    """Verify that passing -v/--debug configures logging.basicConfig at DEBUG level."""
    from qubopy.cli import main

    for flag in ("--debug", "-v", "--verbose"):
        with (
            patch("sys.argv", ["qubopy", flag, "tokens"]),
            patch("qubopy.cli._cmd_tokens", return_value=0),
            patch("logging.basicConfig") as mock_basic_config,
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0
        mock_basic_config.assert_called_once()
        assert mock_basic_config.call_args[1]["level"] == logging.DEBUG
