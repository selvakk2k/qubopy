"""Tests for authentication and token lifecycle."""

import json
import time
from unittest.mock import patch

import pytest

from qubopy.auth import QuboAuth
from qubopy.exceptions import QuboAuthError


class MockClientResponse:
    """Mock aiohttp ClientResponse context manager."""

    def __init__(self, status: int, text_data: str, delay: float = 0.0) -> None:
        self.status = status
        self._text_data = text_data
        self.delay = delay

    async def __aenter__(self):
        if self.delay > 0:
            import asyncio
            await asyncio.sleep(self.delay)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def text(self) -> str:
        return self._text_data


@pytest.mark.asyncio
async def test_email_login_success():
    """Verify email and password login flow."""
    auth = QuboAuth()
    response_payload = {
        "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTk5OSJ9.sig",
        "refreshToken": "refresh-token-xyz",
        "uuid": "user-999",
    }

    mock_resp = MockClientResponse(200, json.dumps(response_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp) as mock_post:
        tokens = await auth.login_with_email("user@example.com", "mypassword")

        assert tokens.access_token == response_payload["accessToken"]
        assert tokens.refresh_token == "refresh-token-xyz"
        assert tokens.user_uuid == "user-999"
        assert auth.is_authenticated is True
        assert auth.user_uuid == "user-999"
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["App-Id"] == "com.hero.iot"
        assert kwargs["headers"]["Source"] == "USER"
        assert kwargs["headers"]["Token-Type"] == "USER"
        assert "Source-Device-Id" in kwargs["headers"]
        assert kwargs["json"]["username"] == "user@example.com"
        assert kwargs["json"]["email"] == "user@example.com"
        assert kwargs["json"]["password"] == "mypassword"
        assert kwargs["json"]["deviceAttribute"] == "Qubopy"
        assert "/user/login?system=CS" in args[0]

    await auth.close()


@pytest.mark.asyncio
async def test_email_login_invalid_credentials():
    """Verify that 401 error raises QuboAuthError."""
    auth = QuboAuth()
    mock_resp = MockClientResponse(401, "Invalid email or password")

    with (
        patch("aiohttp.ClientSession.post", return_value=mock_resp),
        pytest.raises(QuboAuthError, match="Email login failed"),
    ):
        await auth.login_with_email("user@example.com", "wrong")

    await auth.close()


@pytest.mark.asyncio
async def test_phone_otp_flow():
    """Verify phone OTP request and verification with required App-Id, Source, and deviceAttribute."""
    auth = QuboAuth(device_id="test-device-uuid")

    mock_resp_request = MockClientResponse(200, json.dumps({"uuid": "session-123", "status": "OTP_SENT"}))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp_request) as mock_post:
        req_res = await auth.request_phone_otp("9876543210", "+91")
        assert req_res["status"] == "OTP_SENT"
        assert req_res["uuid"] == "session-123"
        # Assert headers and payload
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["App-Id"] == "com.hero.iot"
        assert kwargs["headers"]["Source"] == "USER"
        assert kwargs["headers"]["Source-Device-Id"] == "test-device-uuid"
        assert kwargs["json"]["isdCode"] == "+91"
        assert kwargs["json"]["deviceAttribute"] == "Qubopy"

    otp_payload = {
        "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTg4OCJ9.sig",
        "refreshToken": "ref-888",
        "uuid": "user-888",
    }
    mock_resp_verify = MockClientResponse(200, json.dumps(otp_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp_verify) as mock_post:
        tokens = await auth.verify_phone_otp("9876543210", "1234", isd_code="+91")
        assert tokens.user_uuid == "user-888"
        assert tokens.access_token == otp_payload["accessToken"]
        _args, kwargs = mock_post.call_args
        assert kwargs["headers"]["App-Id"] == "com.hero.iot"
        assert kwargs["headers"]["Source"] == "USER"
        assert kwargs["json"]["uuid"] == "session-123"
        assert kwargs["json"]["deviceAttribute"] == "Qubopy"

    await auth.close()


@pytest.mark.asyncio
async def test_phone_otp_multi_account_list():
    """Verify phone OTP verification succeeds when server returns a list of accounts."""
    auth = QuboAuth(device_id="test-device-uuid")

    multi_account_payload = [
        {
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTExMSJ9.sig",
            "uuid": "user-111",
            "email": "user1@example.com",
            "name": "User One",
        },
        {
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTIyMiJ9.sig",
            "uuid": "user-222",
            "email": "user2@example.com",
            "name": "User Two",
        },
    ]
    mock_resp_verify = MockClientResponse(200, json.dumps(multi_account_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp_verify):
        tokens = await auth.verify_phone_otp(
            "9876543210", "865321", isd_code="+91", session_uuid="session-multi"
        )
        assert tokens.user_uuid == "user-111"
        assert tokens.access_token == multi_account_payload[0]["token"]
        assert tokens.refresh_token is None

    await auth.close()


@pytest.mark.asyncio
async def test_get_phone_otp_profiles():
    """Verify get_phone_otp_profiles returns all profiles returned by server."""
    auth = QuboAuth(device_id="test-device-uuid")
    multi_account_payload = [
        {"uuid": "user-111", "email": "user1@example.com", "name": "User One"},
        {"uuid": "user-222", "email": "user2@example.com", "name": "User Two"},
    ]
    mock_resp = MockClientResponse(200, json.dumps(multi_account_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        profiles = await auth.get_phone_otp_profiles(
            "9876543210", "865321", isd_code="+91", session_uuid="session-multi"
        )
        assert len(profiles) == 2
        assert profiles[0]["email"] == "user1@example.com"
        assert profiles[1]["uuid"] == "user-222"

    await auth.close()


@pytest.mark.asyncio
async def test_phone_otp_select_by_index_and_uuid():
    """Verify selecting specific profile by index or account UUID."""
    auth = QuboAuth(device_id="test-device-uuid")
    multi_account_payload = [
        {
            "token": "token-1",
            "uuid": "user-111",
            "email": "user1@example.com",
            "name": "User One",
        },
        {
            "token": "token-2",
            "uuid": "user-222",
            "email": "user2@example.com",
            "name": "User Two",
        },
    ]

    # Select by profile_index = 1
    mock_resp1 = MockClientResponse(200, json.dumps(multi_account_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp1):
        tokens = await auth.verify_phone_otp(
            "9876543210", "123456", session_uuid="session-multi", profile_index=1
        )
        assert tokens.user_uuid == "user-222"
        assert tokens.access_token == "token-2"

    # Select by account_uuid = "user-111"
    mock_resp2 = MockClientResponse(200, json.dumps(multi_account_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp2):
        tokens = await auth.verify_phone_otp(
            "9876543210", "123456", session_uuid="session-multi", account_uuid="user-111"
        )
        assert tokens.user_uuid == "user-111"
        assert tokens.access_token == "token-1"

    # Out of range index raises QuboAuthError
    mock_resp3 = MockClientResponse(200, json.dumps(multi_account_payload))
    with (
        patch("aiohttp.ClientSession.post", return_value=mock_resp3),
        pytest.raises(QuboAuthError, match="Profile index 5 out of range"),
    ):
        await auth.verify_phone_otp(
            "9876543210", "123456", session_uuid="session-multi", profile_index=5
        )

    # Unknown UUID raises QuboAuthError
    mock_resp4 = MockClientResponse(200, json.dumps(multi_account_payload))
    with (
        patch("aiohttp.ClientSession.post", return_value=mock_resp4),
        pytest.raises(QuboAuthError, match="Account UUID 'unknown-uuid' not found"),
    ):
        await auth.verify_phone_otp(
            "9876543210", "123456", session_uuid="session-multi", account_uuid="unknown-uuid"
        )

    await auth.close()



@pytest.mark.asyncio
async def test_token_refresh():
    """Verify proactive or manual session refresh."""
    auth = QuboAuth()
    auth.set_tokens(
        access_token="old-token",
        refresh_token="valid-refresh",
        user_uuid="user-999",
        expires_at=100.0,
    )

    refresh_payload = {
        "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIxMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTk5OSJ9.sig",
        "refreshToken": "new-refresh-token",
    }
    mock_resp = MockClientResponse(200, json.dumps(refresh_payload))

    with patch("aiohttp.ClientSession.post", return_value=mock_resp) as mock_post:
        new_tokens = await auth.refresh_session()
        assert new_tokens.access_token == refresh_payload["accessToken"]
        assert new_tokens.refresh_token == "new-refresh-token"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {
            "accessToken": "old-token",
            "refreshToken": "valid-refresh",
        }

    await auth.close()


@pytest.mark.asyncio
async def test_get_headers(sample_auth):
    """Verify standard authenticated headers construction."""
    headers = await sample_auth.get_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"].startswith("Bearer eyJ")
    assert headers["Token-Type"] == "USER"
    assert headers["User-UUID"] == "user-123"
    assert headers["Subscriber-Key"] == sample_auth.tokens.access_token
    assert headers["Source-Device-Id"] == sample_auth.device_id
    assert headers["Source"] == "Android"
    await sample_auth.close()


def test_auth_rejects_insecure_url():
    """Verify that insecure HTTP base URLs, lookalike hosts, and userinfo are rejected."""
    with pytest.raises(ValueError, match="Insecure base_url"):
        QuboAuth(base_url="http://insecure-api.quboworld.com")

    with pytest.raises(ValueError, match="Insecure base_url"):
        QuboAuth(base_url="http://localhost.evil.com")

    with pytest.raises(ValueError, match="Insecure base_url: userinfo"):
        QuboAuth(base_url="https://user:pass@srvcapp.platform.quboworld.com")


def test_auth_allows_valid_urls():
    """Verify that HTTPS and loopback HTTP testing URLs are accepted."""
    a1 = QuboAuth(base_url="https://srvcapp.platform.quboworld.com:443")
    assert a1.base_url == "https://srvcapp.platform.quboworld.com:443"

    a2 = QuboAuth(base_url="http://localhost:8080")
    assert a2.base_url == "http://localhost:8080"

    a3 = QuboAuth(base_url="http://127.0.0.1:8000")
    assert a3.base_url == "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_auth_refresh_session_double_checked_lock():
    """Verify that if tokens were refreshed by another coroutine, no network call is made."""
    auth = QuboAuth(base_url="http://localhost")
    # Set fresh token expiring 1 hour from now
    auth.set_tokens(
        access_token="fresh-token",
        refresh_token="valid-refresh",
        user_uuid="user-999",
        expires_at=time.time() + 3600,
    )

    with patch("aiohttp.ClientSession.post") as mock_post:
        # Proactive path
        tokens = await auth.refresh_session()
        assert tokens.access_token == "fresh-token"
        mock_post.assert_not_called()

        # Failed token mismatch (another coroutine already refreshed)
        tokens = await auth.refresh_session(failed_token="old-expired-token")
        assert tokens.access_token == "fresh-token"
        mock_post.assert_not_called()

    await auth.close()


@pytest.mark.asyncio
async def test_auth_get_valid_access_token_expired_failure():
    """When token is expired and refresh fails, get_valid_access_token raises QuboAuthError."""
    auth = QuboAuth(base_url="http://localhost")
    # Token expired 10 seconds ago
    auth.set_tokens(
        access_token="expired-tok",
        refresh_token="invalid-ref",
        user_uuid="u-1",
        expires_at=time.time() - 10,
    )

    with (
        patch.object(auth, "refresh_session", side_effect=Exception("Network down")),
        pytest.raises(QuboAuthError, match="Session expired and automatic token renewal failed"),
    ):
        await auth.get_valid_access_token()

    await auth.close()


@pytest.mark.asyncio
async def test_auth_get_valid_access_token_near_expiry_warning():
    """When token is near expiry (< 300s) but not yet expired, failed refresh logs warning and returns token."""
    auth = QuboAuth(base_url="http://localhost")
    # Token expires 100 seconds in the future
    auth.set_tokens(
        access_token="valid-tok",
        refresh_token="ref",
        user_uuid="u-1",
        expires_at=time.time() + 100,
    )

    with patch.object(auth, "refresh_session", side_effect=Exception("Temporary glitch")):
        token = await auth.get_valid_access_token()
        assert token == "valid-tok"

    await auth.close()

