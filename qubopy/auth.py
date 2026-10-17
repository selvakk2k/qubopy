"""Authentication engine for Qubo cloud services."""

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from qubopy.const import (
    DEFAULT_APP_ID,
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_ATTRIBUTE,
    DEFAULT_SP_ID,
    PATH_AUTH_REFRESH,
    PATH_LOGIN_EMAIL,
    PATH_LOGIN_PHONE_REQUEST,
    PATH_LOGIN_PHONE_VERIFY,
)
from qubopy.exceptions import QuboAuthError, QuboConnectionError
from qubopy.models import TokenPayload

_LOGGER = logging.getLogger(__name__)
DEVICE_ID_FILE = Path.home() / ".qubopy_device_id"


def _get_or_create_device_id() -> str:
    """Return persistent device UUID matching Android uniqueAndroidID behavior."""
    try:
        if DEVICE_ID_FILE.exists():
            saved_id = DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
            if saved_id:
                return saved_id
        new_id = str(uuid.uuid4())
        fd = os.open(str(DEVICE_ID_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as f:
                f.write(new_id)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        return new_id
    except Exception as err:
        _LOGGER.debug("Could not persist or read device ID (%s); generating ephemeral UUID", err)
        return str(uuid.uuid4())


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
    except Exception as err:
        _LOGGER.debug("Could not parse JWT expiry from token: %s", err)
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
        parsed = urlsplit(base_url)
        if "@" in (parsed.netloc or ""):
            raise ValueError("Insecure base_url: userinfo is not permitted")
        if parsed.scheme == "https":
            if not parsed.hostname:
                raise ValueError(f"Invalid base_url: missing hostname in {base_url}")
        elif parsed.scheme == "http":
            allowed_local = ("localhost", "127.0.0.1", "::1")
            if parsed.hostname not in allowed_local:
                raise ValueError(
                    f"Insecure base_url: HTTP is only permitted for local testing "
                    f"({allowed_local}), got {parsed.hostname}"
                )
        else:
            raise ValueError(f"Insecure or unsupported scheme in base_url: {parsed.scheme}")
        self.base_url = base_url.rstrip("/")
        self.sp_id = sp_id
        self.app_id = app_id
        self.device_id = device_id or _get_or_create_device_id()
        self._session = session
        self._owns_session = session is None
        self._tokens: TokenPayload | None = None
        self._login_uuid: str | None = None
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
    def mqtt_password(self) -> str | None:
        """Return MQTT broker password if present in login response.

        Unverified on hardware; not used by the listener.
        """
        return self._tokens.mqtt_password if self._tokens else None

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
        mqtt_password: str | None = None,
    ) -> TokenPayload:
        """Manually configure cached credentials."""
        if expires_at is None:
            expires_at = _decode_jwt_expiry(access_token)
            if expires_at is None:
                # Default to 24 hours expiry if absent
                expires_at = time.time() + 86400

        self._tokens = TokenPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            user_uuid=user_uuid,
            mqtt_password=mqtt_password,
            expires_at=expires_at,
        )
        return self._tokens

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return an active aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            self._owns_session = True
        return self._session

    async def login_with_email(
        self,
        email: str,
        password: str,
        device_attribute: str = DEFAULT_DEVICE_ATTRIBUTE,
    ) -> TokenPayload:
        """Authenticate using account email and password."""
        url = f"{self.base_url}{PATH_LOGIN_EMAIL.format(sp=self.sp_id)}"
        payload = {
            "username": email,
            "email": email,
            "password": password,
            "deviceAttribute": device_attribute,
        }
        headers = {
            "Content-Type": "application/json",
            "App-Id": self.app_id,
            "Source-Device-Id": self.device_id,
            "Source": "USER",
            "Token-Type": "USER",
        }

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    _LOGGER.debug(
                        "Email login error response (HTTP %s): %s", response.status, text[:200]
                    )
                    raise QuboAuthError(f"Email login failed (HTTP {response.status})")
                data = json.loads(text)
                if isinstance(data, list) and data:
                    data = data[0]
                if not isinstance(data, dict):
                    raise QuboAuthError(
                        f"Unexpected response format from login: {type(data).__name__}"
                    )
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error during login: {err}") from err
        except json.JSONDecodeError as err:
            raise QuboAuthError(f"Invalid JSON returned by server: {err}") from err

        access_token = data.get("accessToken") or data.get("token")
        user_uuid = data.get("uuid") or data.get("userUUID") or data.get("userId")
        if not access_token or not user_uuid:
            raise QuboAuthError("Missing required token fields in login response")

        refresh_token = data.get("refreshToken")
        expires_at = _decode_jwt_expiry(access_token) or (time.time() + 86400)

        mqtt_password = data.get("mqttPassword")
        self._tokens = TokenPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            user_uuid=str(user_uuid),
            mqtt_password=mqtt_password,
            expires_at=expires_at,
        )
        return self._tokens

    async def request_phone_otp(
        self,
        phone: str,
        isd_code: str = "+91",
        device_attribute: str = DEFAULT_DEVICE_ATTRIBUTE,
    ) -> dict[str, Any]:
        """Request a one-time SMS password for phone login."""
        url = f"{self.base_url}{PATH_LOGIN_PHONE_REQUEST.format(sp=self.sp_id)}"
        clean_isd = isd_code if isd_code.startswith("+") else f"+{isd_code}"
        payload = {
            "phone": phone,
            "isdCode": clean_isd,
            "deviceAttribute": device_attribute,
        }
        headers = {
            "Content-Type": "application/json",
            "App-Id": self.app_id,
            "Source-Device-Id": self.device_id,
            "Source": "USER",
        }

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    _LOGGER.debug(
                        "OTP request error response (HTTP %s): %s", response.status, text[:200]
                    )
                    raise QuboAuthError(f"OTP request failed (HTTP {response.status})")
                data = json.loads(text)
                self._login_uuid = data.get("uuid")
                return data
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error requesting OTP: {err}") from err

    async def get_phone_otp_profiles(
        self,
        phone: str,
        otp: str,
        isd_code: str = "+91",
        session_uuid: str | None = None,
        device_attribute: str = DEFAULT_DEVICE_ATTRIBUTE,
    ) -> list[dict[str, Any]]:
        """Verify SMS OTP and return all matching account profiles."""
        url = f"{self.base_url}{PATH_LOGIN_PHONE_VERIFY.format(sp=self.sp_id)}"
        clean_isd = isd_code if isd_code.startswith("+") else f"+{isd_code}"
        target_uuid = session_uuid or self._login_uuid
        if not target_uuid:
            raise QuboAuthError(
                "Missing login session UUID. Call request_phone_otp first or provide session_uuid."
            )

        payload = {
            "phone": phone,
            "isdCode": clean_isd,
            "otp": otp,
            "deviceAttribute": device_attribute,
            "uuid": target_uuid,
        }
        headers = {
            "Content-Type": "application/json",
            "App-Id": self.app_id,
            "Source-Device-Id": self.device_id,
            "Source": "USER",
        }

        session = await self._get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                text = await response.text()
                if response.status != 200:
                    _LOGGER.debug(
                        "OTP verification error response (HTTP %s): %s", response.status, text[:200]
                    )
                    raise QuboAuthError(f"OTP verification failed (HTTP {response.status})")
                data = json.loads(text)
                if isinstance(data, dict):
                    return [data]
                if isinstance(data, list):
                    return data
                raise QuboAuthError(f"Unexpected response format from OTP verification: {data}")
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"Network error verifying OTP: {err}") from err
        except json.JSONDecodeError as err:
            raise QuboAuthError(f"Invalid JSON returned by server: {err}") from err

    @staticmethod
    def find_profile_index(
        profiles: list[dict[str, Any]],
        profile_index: int = 0,
        account_uuid: str | None = None,
    ) -> int:
        """Find the matching profile index from verification results."""
        if not profiles:
            raise QuboAuthError("No account profiles returned in OTP verification response")

        if account_uuid:
            for idx, p in enumerate(profiles):
                p_uuid = str(p.get("uuid") or p.get("userUUID") or p.get("userId") or "")
                if p_uuid == account_uuid:
                    return idx
            raise QuboAuthError(f"Account UUID '{account_uuid}' not found among returned profiles")

        if profile_index < 0 or profile_index >= len(profiles):
            raise QuboAuthError(
                f"Profile index {profile_index} out of range (0-{len(profiles) - 1})"
            )
        return profile_index

    def select_profile(
        self,
        profiles: list[dict[str, Any]],
        profile_index: int = 0,
        account_uuid: str | None = None,
    ) -> TokenPayload:
        """Adopt session tokens from a selected profile returned by OTP verification."""
        idx = self.find_profile_index(
            profiles, profile_index=profile_index, account_uuid=account_uuid
        )
        selected_profile = profiles[idx]

        access_token = selected_profile.get("accessToken") or selected_profile.get("token")
        user_uuid = (
            selected_profile.get("uuid")
            or selected_profile.get("userUUID")
            or selected_profile.get("userId")
        )
        if not access_token or not user_uuid:
            raise QuboAuthError("Missing tokens in OTP response")

        refresh_token = selected_profile.get("refreshToken")
        expires_at = _decode_jwt_expiry(access_token) or (time.time() + 86400)

        mqtt_password = selected_profile.get("mqttPassword")
        self._tokens = TokenPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            user_uuid=str(user_uuid),
            mqtt_password=mqtt_password,
            expires_at=expires_at,
        )
        return self._tokens

    async def verify_phone_otp(
        self,
        phone: str,
        otp: str,
        isd_code: str = "+91",
        session_uuid: str | None = None,
        device_attribute: str = DEFAULT_DEVICE_ATTRIBUTE,
        profile_index: int = 0,
        account_uuid: str | None = None,
    ) -> TokenPayload:
        """Verify received SMS OTP and obtain session tokens.

        If multiple account profiles are linked to the phone number, specify
        either `profile_index` (default 0) or `account_uuid` to select the account.
        """
        profiles = await self.get_phone_otp_profiles(
            phone=phone,
            otp=otp,
            isd_code=isd_code,
            session_uuid=session_uuid,
            device_attribute=device_attribute,
        )
        return self.select_profile(
            profiles,
            profile_index=profile_index,
            account_uuid=account_uuid,
        )

    async def refresh_session(self, failed_token: str | None = None) -> TokenPayload:
        """Renew the JWT access token using the stored refresh token."""
        async with self._refresh_lock:
            if not self._tokens or not self._tokens.refresh_token:
                raise QuboAuthError("No refresh token available to renew session")

            # Concurrency / Double-checked locking
            if failed_token is not None:
                # If another coroutine already refreshed the token while we waited for the lock
                if self._tokens.access_token != failed_token:
                    return self._tokens
            elif self._tokens.expires_at and (self._tokens.expires_at - time.time()) > 300:
                # Proactive background refresh path: token still has > 5 min validity
                return self._tokens

            url = (
                f"{self.base_url}"
                f"{PATH_AUTH_REFRESH.format(sp=self.sp_id, user_uuid=self._tokens.user_uuid)}"
            )
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._tokens.access_token}",
                "Subscriber-Key": self._tokens.access_token,
                "User-UUID": self._tokens.user_uuid,
                "Token-Type": "USER",
                "Source-Device-Id": self.device_id,
                "App-Id": self.app_id,
                "Source": "Android",
            }
            payload = {
                "accessToken": self._tokens.access_token,
                "refreshToken": self._tokens.refresh_token,
            }

            session = await self._get_session()
            try:
                async with session.post(url, json=payload, headers=headers) as response:
                    text = await response.text()
                    if response.status != 200:
                        _LOGGER.debug(
                            "Session refresh error response (HTTP %s): %s",
                            response.status,
                            text[:200],
                        )
                        if response.status in (400, 401, 403):
                            self._tokens = None
                            raise QuboAuthError(
                                f"Session refresh rejected (HTTP {response.status}): "
                                "refresh token expired or invalid; re-login required"
                            )
                        raise QuboAuthError(f"Session refresh failed (HTTP {response.status})")
                    data = json.loads(text)
            except aiohttp.ClientError as err:
                raise QuboConnectionError(f"Network error during token refresh: {err}") from err
            except json.JSONDecodeError as err:
                raise QuboAuthError(
                    f"Invalid JSON returned by server during refresh: {err}"
                ) from err

            new_access_token = data.get("accessToken") or data.get("access_token")
            if not new_access_token:
                raise QuboAuthError("Refresh response missing access token")

            new_refresh_token = (
                data.get("refreshToken")
                or data.get("refresh_token")
                or (self._tokens.refresh_token if self._tokens else None)
            )
            expires_at = _decode_jwt_expiry(new_access_token) or (time.time() + 86400)

            mqtt_password = data.get("mqttPassword") or (
                self._tokens.mqtt_password if self._tokens else None
            )
            self._tokens = TokenPayload(
                access_token=new_access_token,
                refresh_token=new_refresh_token,
                user_uuid=self._tokens.user_uuid,
                mqtt_password=mqtt_password,
                expires_at=expires_at,
            )
            return self._tokens

    async def get_valid_access_token(self) -> str:
        """Return a valid access token, proactively refreshing if near expiration."""
        if not self._tokens:
            raise QuboAuthError("Authentication required: No tokens present")

        now = time.time()
        # If token expires in less than 5 minutes (300 seconds), refresh it
        if (
            self._tokens.expires_at
            and (self._tokens.expires_at - now) < 300
            and self._tokens.refresh_token
        ):
            try:
                await self.refresh_session()
            except Exception as err:
                if self._tokens.expires_at <= now:
                    raise QuboAuthError(
                        f"Session expired and automatic token renewal failed: {err}"
                    ) from err
                _LOGGER.warning("Proactive token refresh near expiration failed: %s", err)

        if (
            self._tokens.expires_at
            and self._tokens.expires_at <= now
            and not self._tokens.refresh_token
        ):
            raise QuboAuthError("Session expired; please log in again")

        return self._tokens.access_token

    async def get_headers(self) -> dict[str, str]:
        """Generate standard authenticated request headers."""
        token = await self.get_valid_access_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Token-Type": "USER",
            "User-UUID": self._tokens.user_uuid,  # type: ignore[union-attr]
            "Subscriber-Key": token,
            "Source-Device-Id": self.device_id,
            "App-Id": self.app_id,
            "Source": "Android",
        }

    async def close(self) -> None:
        """Close underlying HTTP session if owned."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
