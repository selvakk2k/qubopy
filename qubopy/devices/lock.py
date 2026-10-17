"""Smart lock device abstraction and local BLE key enabler (HLM, HLW, HLR)."""

import logging
from typing import Any

from qubopy.devices.base import (
    QuboDevice,
    _as_bool,
    _first_not_none,
    _parse_battery_level,
)
from qubopy.exceptions import QuboCommandError, QuboKeyExtractionError
from qubopy.models import BleLockCredentials

_LOGGER = logging.getLogger(__name__)


class QuboLock(QuboDevice):
    """Qubo Smart Door Lock (HLM01-10, HLW01, HLR01)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_lock_state_timestamp: int | None = None

    @property
    def gateway_id(self) -> str | None:
        """Return paired in-home gateway device UUID if present in metadata."""
        return _first_not_none(self.info.extra_data, "gatewayUUID", "gatewayId") or _first_not_none(
            self.shadow.reported, "gatewayUUID", "gatewayId"
        )

    @property
    def is_gateway_accessible(self) -> bool:
        """Return True if an in-home RF/BLE gateway is paired for cloud actuation."""
        return bool(self.gateway_id)

    @property
    def is_locked(self) -> bool | None:
        """Return True if door is locked, False if unlocked, None if unknown."""
        rep = self.reported_state
        raw_lock_state = _first_not_none(
            rep, "lockState", "lockControl_lockState", "lockControl.lockState"
        )
        if raw_lock_state is None and isinstance(rep.get("lockControl"), dict):
            raw_lock_state = rep["lockControl"].get("lockState")
        if raw_lock_state is not None:
            s = str(raw_lock_state).strip().lower()
            state_map = {
                "locked": True,
                "lock": True,
                "unlocked": False,
                "unlock": False,
            }
            if s in state_map:
                return state_map[s]
            return None
        raw_open = _first_not_none(rep, "isOpen", "open")
        if raw_open is not None:
            if isinstance(raw_open, str) and raw_open.strip().lower() in ("open", "opened"):
                return False
            if isinstance(raw_open, str) and raw_open.strip().lower() in ("close", "closed"):
                return True
            is_open_val = _as_bool(raw_open)
            if is_open_val is not None:
                return not is_open_val
        locked_val = _as_bool(_first_not_none(rep, "locked", "isLocked"))
        if locked_val is not None:
            return locked_val
        return None

    @property
    def battery_percent(self) -> int | None:
        """Return lock battery percentage (0-100)."""
        rep = self.reported_state
        val = _first_not_none(
            rep,
            "level",
            "batteryStatus_level",
            "batteryStatus.level",
            "dpower",
            "battery",
        )
        if val is None and isinstance(rep.get("batteryStatus"), dict):
            val = rep["batteryStatus"].get("level")
        if val is None:
            val = _first_not_none(self.info.extra_data, "dpower", "battery", "level")
        return _parse_battery_level(val)

    def _extract_field(self, *keys: str) -> Any | None:
        """Search for a key across info.extra_data, shadow.reported, and shadow.raw."""
        sources = [self.info.extra_data, self.shadow.reported, self.shadow.raw]
        for src in sources:
            if not isinstance(src, dict):
                continue
            for k in keys:
                if k in src and src[k] is not None:
                    return src[k]
                # Also check nested bean if present
                for nested_key in ("P01DeviceBean", "deviceBean", "bean", "bleInfo"):
                    if (
                        nested_key in src
                        and isinstance(src[nested_key], dict)
                        and k in src[nested_key]
                        and src[nested_key][k] is not None
                    ):
                        return src[nested_key][k]
        return None

    async def get_ble_lock_keys(self) -> BleLockCredentials:
        """Extract Deftun P01 Bluetooth Low Energy credentials for offline control.

        These keys enable 100% local operation using Home Assistant Bluetooth Proxy
        or ESPHome without requiring active internet connectivity.
        """
        # Ensure fresh shadow state before extraction
        if not self.shadow.reported and not self.info.extra_data:
            await self.refresh()

        mac = self._extract_field("dmac", "mac", "deviceMac", "bleMac")
        auth_key = self._extract_field("dbtauthkey", "authKey", "btauthkey")
        offline_key = self._extract_field("dbtoffkey", "offKey", "btoffkey")

        if not mac or not auth_key:
            # Attempt one explicit refresh if possible
            try:
                await self.refresh()
            except Exception as err:
                _LOGGER.debug("Could not refresh lock prior to BLE key extraction: %s", err)
            mac = self._extract_field("dmac", "mac", "deviceMac", "bleMac")
            auth_key = self._extract_field("dbtauthkey", "authKey", "btauthkey")
            offline_key = self._extract_field("dbtoffkey", "offKey", "btoffkey")

        if not mac or not auth_key:
            raise QuboKeyExtractionError(
                f"Failed to locate offline BLE keys for lock {self.device_id} ({self.name}). "
                "Ensure device was paired and synced in the Qubo mobile app."
            )

        offline_key_flag = self._extract_field("dbtoffkeyflag", "offKeyFlag")
        admin_pass = self._extract_field("dadminpass", "adminPass", "adminPin")
        admin_flag = self._extract_field("dadminflag", "adminFlag")
        bt_name = self._extract_field("dbtname", "btName", "advName")
        power = self.battery_percent
        is_open_val = self._extract_field("isOpen")

        return BleLockCredentials(
            device_uuid=self.device_id,
            device_name=self.name,
            mac_address=str(mac),
            auth_key=str(auth_key),
            offline_key=str(offline_key or ""),
            offline_key_flag=str(offline_key_flag) if offline_key_flag is not None else None,
            admin_pass=str(admin_pass) if admin_pass is not None else None,
            admin_flag=str(admin_flag) if admin_flag is not None else None,
            bluetooth_name=str(bt_name) if bt_name is not None else None,
            battery_level=power,
            is_open=_as_bool(is_open_val),
        )

    async def unlock(self, gateway_uuid: str | None = None) -> dict[str, Any]:
        """Dispatch cloud unlock command to the paired in-home gateway device.

        Qubo smart door locks actuate via Bluetooth Low Energy commands sent from a
        paired in-home Wi-Fi gateway (such as a Video Doorbell Pro or Smart Camera).
        """
        target_gw = gateway_uuid or self.gateway_id
        if not target_gw:
            u_id = self.unit_id or "unknown"
            raise QuboCommandError(
                f"Cannot unlock {self.device_id} ({self.name}): no in-home gateway "
                f"(Video Doorbell Pro or Smart Camera) was found in unit '{u_id}'. "
                "This lock is operating in standalone Bluetooth mode; use local BLE key export "
                "(get_ble_lock_keys()) or provide an explicit gateway_uuid."
            )
        if not self.unit_id or not self.entity_id:
            raise QuboCommandError(
                f"{self.name} has no unit/entity binding and cannot be commanded"
            )
        return await self.client.unlock_lock_via_gateway(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            gateway_uuid=target_gw,
        )

    @property
    def last_lock_state_timestamp(self) -> int | None:
        """Return the Unix timestamp (milliseconds) of the last fetched live lockState."""
        return self._last_lock_state_timestamp

    async def fetch_live_lock_state(self) -> str | None:
        """Fetch real-time lockState directly from v2/deviceshadow."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        resp = await self.client.get_device_shadow_v2(
            self.device_id, service_name="lockControl", attribute_name="lockState"
        )
        val = resp.get("attributeValue")
        if val is None:
            val = resp.get("state")

        raw_ts = resp.get("timestamp")
        if raw_ts is not None:
            try:
                ts_int = int(raw_ts)
                # If 10 digits or fewer (seconds), convert to milliseconds
                if 0 < ts_int < 100_000_000_000:
                    ts_int *= 1000
                self._last_lock_state_timestamp = ts_int
                self.shadow.reported["lockState_timestamp"] = ts_int
            except (ValueError, TypeError):
                pass

        if val is not None:
            self.shadow.reported["lockState"] = val
            return str(val)
        return None

    async def fetch_live_battery(self) -> int | None:
        """Fetch real-time battery level directly from v2/deviceshadow."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        resp = await self.client.get_device_shadow_v2(
            self.device_id, service_name="batteryStatus", attribute_name="level"
        )
        val = resp.get("attributeValue")
        if val is None:
            val = resp.get("level")
        pct = _parse_battery_level(val)
        if pct is not None:
            self.shadow.reported["level"] = pct
            return pct
        return None

    async def generate_guest_otp(self, validity_minutes: int | None = None) -> dict[str, Any]:
        """Generate a temporary one-time keypad PIN code for guest access.

        Note:
            The Android app sends an empty JSON array (`[]`) and parses a JSON array response.
            `validity_minutes` is experimental / unverified (not sent by Android app).

        Args:
            validity_minutes: Optional expiration window in minutes (experimental / unverified).
        """
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.generate_lock_otp(
            self.device_id, validity_minutes=validity_minutes
        )

    async def revoke_guest_otp(self, otp: str | None = None) -> dict[str, Any]:
        """Revoke an active temporary guest OTP PIN.

        Warning:
            EXPERIMENTAL / UNVERIFIED: This route is not present in the Android app;
            behavior on real lock hardware is unknown.

        Args:
            otp: Optional specific OTP string to invalidate.
        """
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.revoke_lock_otp(self.device_id, otp=otp)
