"""Tests for authentication and token lifecycle."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from qubopy.auth import QuboAuth, _decode_jwt_expiry
from qubopy.exceptions import QuboAuthError, QuboConnectionError


class MockClientResponse:
    """Mock aiohttp ClientResponse context manager."""

    def __init__(self, status: int, text_data: str) -> None:
        self.status = status
        self._text_data = text_data

    async def __aenter__(self):
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
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        tokens = await auth.login_with_email("user@example.com", "mypassword")

        assert tokens.access_token == response_payload["accessToken"]
        assert tokens.refresh_token == "refresh-token-xyz"
        assert tokens.user_uuid == "user-999"
        assert auth.is_authenticated is True
        assert auth.user_uuid == "user-999"

    await auth.close()


@pytest.mark.asyncio
async def test_email_login_invalid_credentials():
    """Verify that 401 error raises QuboAuthError."""
    auth = QuboAuth()
    mock_resp = MockClientResponse(401, "Invalid email or password")

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        with pytest.raises(QuboAuthError, match="Email login failed"):
            await auth.login_with_email("user@example.com", "wrong")

    await auth.close()


@pytest.mark.asyncio
async def test_phone_otp_flow():
    """Verify phone OTP request and verification."""
    auth = QuboAuth()

    mock_resp_request = MockClientResponse(200, json.dumps({"status": "OTP_SENT"}))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp_request):
        req_res = await auth.request_phone_otp("9876543210", "+91")
        assert req_res["status"] == "OTP_SENT"

    otp_payload = {
        "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsInV1aWQiOiJ1c2VyLTg4OCJ9.sig",
        "refreshToken": "ref-888",
        "uuid": "user-888",
    }
    mock_resp_verify = MockClientResponse(200, json.dumps(otp_payload))
    with patch("aiohttp.ClientSession.post", return_value=mock_resp_verify):
        tokens = await auth.verify_phone_otp("9876543210", "1234")
        assert tokens.user_uuid == "user-888"
        assert tokens.access_token == otp_payload["accessToken"]

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

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        new_tokens = await auth.refresh_session()
        assert new_tokens.access_token == refresh_payload["accessToken"]
        assert new_tokens.refresh_token == "new-refresh-token"

    await auth.close()


@pytest.mark.asyncio
async def test_get_headers(sample_auth):
    """Verify standard authenticated headers construction."""
    headers = await sample_auth.get_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"].startswith("Bearer eyJ")
    assert headers["Token-Type"] == "accessToken"
    assert headers["User-UUID"] == "user-123"
    assert headers["Subscriber-Key"] == sample_auth.tokens.access_token
    await sample_auth.close()
