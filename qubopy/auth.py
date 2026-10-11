"""Authentication engine for Qubo cloud services."""

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from qubopy.const import (
    DEFAULT_APP_ID,
    DEFAULT_BASE_URL,
    DEFAULT_SP_ID,
    PATH_AUTH_REFRESH,
    PATH_LOGIN_EMAIL,
    PATH_LOGIN_PHONE_REQUEST,
    PATH_LOGIN_PHONE_VERIFY,
)
from qubopy.exceptions import QuboAuthError, QuboConnectionError
from qubopy.models import TokenPayload

_LOGGER = logging.getLogger(__name__)


def _decode_jwt_expiry(token: str) -> float | None:
    """Extract expiry timestamp from JWT payload without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        # Add padding if needed
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if "exp" in payload and isinstance(payload["exp"], (int, float)):
            return float(payload["exp"])
    except Exception:
        pass
    return None


class QuboAuth:
    """Manages credentials, JWT token lifecycle, and session headers."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        sp_id: str = DEFAULT_SP_ID,
        app_id: str = DEFAULT_APP_ID,
        device_id: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sp_id = sp_id
        self.app_id = app_id
        self.device_id = device_id or str(uuid.uuid4())
        self._session = session
        self._owns_session = session is None
        self._tokens: TokenPayload | None = None
        self._refresh_lock = asyncio.Lock()

    @property
    def is_authenticated(self) -> bool:
        """Return True if active tokens exist."""
        return self._tokens is not None and bool(self._tokens.access_token)

    @property
    def user_uuid(self) -> str | None:
        """Return user account UUID if authenticated."""
        return self._tokens.user_uuid if self._tokens else None

    @property
    def tokens(self) -> TokenPayload | None:
        """Return current token payload."""
        return self._tokens

    def set_tokens(
        self,
        access_token: str,
        refresh_token: str | None = None,
        user_uuid: str = "",
        expires_at: float | None = None,
    ) -> TokenPayload:
        """Manually configure cached credentials."""
        if expires_at is None:
            expires_at = _decode_jwt_expiry(access_token)
            if expires_at is None:
                # Default to 24 hours expiry if absent
                expires_at = time.time() + 86400

        self._tokens = TokenPayload(
            accessToken=access_token,
            refreshToken=refresh_token,
            uuid=user_uuid,
            expires_at=expires_at,
        )
        return self._tokens

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return an active aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def login_with_email(self, email: str, password: str) -> TokenPayload:
        """Authenticate using account email and password."""
        url = f"{self.base_url}{PATH_LOGIN_EMAIL.format(sp=self.sp_id)}"
        payload = {"email": email, "password": password}

        session = await self._get_session()
        try:
            async with session.post(
                url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise QuboAuthError(
                        f"Email login failed (HTTP {response.status}): {text}"
                    )
                data = json.loads(text)
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error during login: {err}") from err
        except json.JSONDecodeError as err:
            raise QuboAuthError(f"Invalid JSON returned by server: {err}") from err

        access_token = data.get("accessToken")
        user_uuid = data.get("uuid") or data.get("userUUID") or data.get("userId")
        if not access_token or not user_uuid:
            raise QuboAuthError(f"Missing required token fields in login response: {data}")

        refresh_token = data.get("refreshToken")
        expires_at = _decode_jwt_expiry(access_token) or (time.time() + 86400)

        self._tokens = TokenPayload(
            accessToken=access_token,
            refreshToken=refresh_token,
            uuid=str(user_uuid),
            expires_at=expires_at,
        )
        return self._tokens

    async def request_phone_otp(
        self, phone: str, isd_code: str = "91"
    ) -> dict[str, Any]:
        """Request a one-time SMS password for phone login."""
        url = f"{self.base_url}{PATH_LOGIN_PHONE_REQUEST.format(sp=self.sp_id)}"
        clean_isd = isd_code.lstrip("+") or "91"
        payload = {
            "phone": phone,
            "isdCode": clean_isd,
            "deviceAttribute": "android",
        }
        headers = {
            "Content-Type": "application/json",
            "App-Id": self.app_id,
            "Source-Device-Id": self.device_id,
        }

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    raise QuboAuthError(
                        f"OTP request failed (HTTP {response.status}): {text}"
                    )
                return json.loads(text)
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error requesting OTP: {err}") from err

    async def verify_phone_otp(
        self, phone: str, otp: str, isd_code: str = "91"
    ) -> TokenPayload:
        """Verify received SMS OTP and obtain session tokens."""
        url = f"{self.base_url}{PATH_LOGIN_PHONE_VERIFY.format(sp=self.sp_id)}"
        clean_isd = isd_code.lstrip("+") or "91"
        payload = {
            "phone": phone,
            "isdCode": clean_isd,
            "otp": otp,
            "deviceAttribute": "android",
        }
        headers = {
            "Content-Type": "application/json",
            "App-Id": self.app_id,
            "Source-Device-Id": self.device_id,
        }

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    raise QuboAuthError(
                        f"OTP verification failed (HTTP {response.status}): {text}"
                    )
                data = json.loads(text)
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error verifying OTP: {err}") from err

        access_token = data.get("accessToken")
        user_uuid = data.get("uuid") or data.get("userUUID")
        if not access_token or not user_uuid:
            raise QuboAuthError(f"Missing tokens in OTP response: {data}")

        refresh_token = data.get("refreshToken")
        expires_at = _decode_jwt_expiry(access_token) or (time.time() + 86400)

        self._tokens = TokenPayload(
            accessToken=access_token,
            refreshToken=refresh_token,
            uuid=str(user_uuid),
            expires_at=expires_at,
        )
        return self._tokens

    async def refresh_session(self) -> TokenPayload:
        """Renew the JWT access token using the stored refresh token."""
        async with self._refresh_lock:
            if not self._tokens or not self._tokens.refresh_token:
                raise QuboAuthError("No refresh token available to renew session")

            url = f"{self.base_url}{PATH_AUTH_REFRESH.format(sp=self.sp_id, user_uuid=self._tokens.user_uuid)}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._tokens.access_token}",
                "refreshToken": self._tokens.refresh_token,
            }

            session = await self._get_session()
            try:
                async with session.post(url, headers=headers) as response:
                    text = await response.text()
                    if response.status != 200:
                        raise QuboAuthError(
                            f"Session refresh failed (HTTP {response.status}): {text}"
                        )
                    data = json.loads(text)
            except aiohttp.ClientError as err:
                raise QuboConnectionError(f"Network error during token refresh: {err}") from err

            new_access_token = data.get("accessToken") or self._tokens.access_token
            new_refresh_token = data.get("refreshToken") or self._tokens.refresh_token
            expires_at = _decode_jwt_expiry(new_access_token) or (time.time() + 86400)

            self._tokens = TokenPayload(
                accessToken=new_access_token,
                refreshToken=new_refresh_token,
                uuid=self._tokens.user_uuid,
                expires_at=expires_at,
            )
            return self._tokens

    async def get_valid_access_token(self) -> str:
        """Return a valid access token, proactively refreshing if near expiration."""
        if not self._tokens:
            raise QuboAuthError("Authentication required: No tokens present")

        # If token expires in less than 5 minutes (300 seconds), refresh it
        if self._tokens.expires_at and (self._tokens.expires_at - time.time()) < 300:
            if self._tokens.refresh_token:
                try:
                    await self.refresh_session()
                except Exception as err:
                    _LOGGER.warning("Proactive token refresh failed: %s", err)

        return self._tokens.access_token

    async def get_headers(self) -> dict[str, str]:
        """Generate standard authenticated request headers."""
        token = await self.get_valid_access_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Token-Type": "accessToken",
            "User-UUID": self._tokens.user_uuid,  # type: ignore[union-attr]
            "Subscriber-Key": token,
        }

    async def close(self) -> None:
        """Close underlying HTTP session if owned."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
