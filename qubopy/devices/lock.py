import logging
from typing import Any

from qubopy.devices.base import QuboDevice, _as_bool, _first_not_none
from qubopy.exceptions import QuboCommandError, QuboKeyExtractionError
from qubopy.models import BleLockCredentials

_LOGGER = logging.getLogger(__name__)


class QuboLock(QuboDevice):
    """Qubo Smart Door Lock (HLM01-10, HLW01, HLR01)."""

    @property
    def gateway_id(self) -> str | None:
        """Return paired in-home gateway device UUID if present in metadata."""
        return _first_not_none(
            self.info.extra_data, "gatewayUUID", "gatewayId"
        ) or _first_not_none(self.shadow.reported, "gatewayUUID", "gatewayId")

    @property
    def is_gateway_accessible(self) -> bool:
        """Return True if an in-home RF/BLE gateway is paired for cloud actuation."""
        return bool(self.gateway_id)


    @property
    def is_locked(self) -> bool | None:
        """Return True if door is locked, False if unlocked, None if unknown."""
        rep = self.reported_state
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
        val = _first_not_none(self.reported_state, "dpower", "battery")
        if val is None:
            val = _first_not_none(self.info.extra_data, "dpower", "battery")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

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
            raise QuboCommandError(
                f"Cannot unlock {self.device_id} ({self.name}): no in-home gateway "
                f"(Video Doorbell Pro or Smart Camera) was found in unit '{self.unit_id or 'default'}'. "
                "This lock is operating in standalone Bluetooth mode; use local BLE key export "
                "(get_ble_lock_keys()) or provide an explicit gateway_uuid."
            )
        return await self.client.unlock_lock_via_gateway(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            gateway_uuid=target_gw,
        )
