"""Smart air purifier device abstraction (HPH series)."""

from typing import Any

from qubopy.devices.base import QuboDevice, _as_bool, _first_not_none
from qubopy.exceptions import QuboCommandError


class QuboAirPurifier(QuboDevice):
    """Qubo Smart Air Purifier (HPH01 to HPH08 - Q200 to Q1000)."""

    @property
    def is_on(self) -> bool:
        """Return True if air purifier is running."""
        state = _first_not_none(self.reported_state, "state", "power", "power_state")
        return bool(_as_bool(state))

    @property
    def fan_speed(self) -> int | None:
        """Return fan speed level (1 to 3)."""
        val = _first_not_none(self.reported_state, "speed", "fan_speed", "fanSpeed")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def mode(self) -> str | None:
        """Return current operation mode (e.g. auto, sleep, manual)."""
        val = _first_not_none(self.reported_state, "mode", "preset_mode")
        return str(val).lower() if val is not None else None

    @property
    def pm25(self) -> int | None:
        """Return PM2.5 particulate measurement in ug/m3."""
        val = _first_not_none(self.reported_state, "pm2_5", "pm25", "aqi")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def filter_life_percent(self) -> int | None:
        """Return remaining filter life percentage."""
        val = _first_not_none(self.reported_state, "filter_life", "filter_life_percent")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def is_child_lock_on(self) -> bool:
        """Return True if child lock is engaged."""
        val = _first_not_none(self.reported_state, "child_lock", "childLock")
        return bool(_as_bool(val))

    async def turn_on(self) -> dict[str, Any]:
        """Power on the air purifier."""
        return await self.send_command({"state": "ON", "power": True})

    async def turn_off(self) -> dict[str, Any]:
        """Power off the air purifier."""
        return await self.send_command({"state": "OFF", "power": False})

    async def set_fan_speed(self, speed: int) -> dict[str, Any]:
        """Set fan speed (1 to 3)."""
        return await self.send_command({"fan_speed": speed, "speed": speed})

    async def set_mode(self, mode: str) -> dict[str, Any]:
        """Set preset mode ('auto', 'sleep', 'manual')."""
        return await self.send_command({"mode": mode.lower()})

    async def set_child_lock(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable physical button child lock."""
        return await self.send_command({"child_lock": enabled})

    async def get_pm25_insights(self) -> dict[str, Any]:
        """Fetch daily PM2.5 particulate history and trends."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.get_purifier_pm25_insights(self.unit_id, self.device_id)
