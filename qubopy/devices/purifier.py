"""Smart air purifier device abstraction (HPH series)."""

from typing import Any
from qubopy.devices.base import QuboDevice


class QuboAirPurifier(QuboDevice):
    """Qubo Smart Air Purifier (HPH01 to HPH08 - Q200 to Q1000)."""

    @property
    def is_on(self) -> bool:
        """Return True if air purifier is running."""
        rep = self.reported_state
        state = rep.get("state") or rep.get("power") or rep.get("power_state")
        if isinstance(state, str):
            return state.upper() in ("ON", "1", "TRUE")
        if isinstance(state, (int, float)):
            return state == 1
        if isinstance(state, bool):
            return state
        return False

    @property
    def fan_speed(self) -> int | None:
        """Return fan speed level (1 to 3)."""
        rep = self.reported_state
        val = rep.get("speed") or rep.get("fan_speed") or rep.get("fanSpeed")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def mode(self) -> str | None:
        """Return current operation mode (e.g. auto, sleep, manual)."""
        rep = self.reported_state
        val = rep.get("mode") or rep.get("preset_mode")
        return str(val).lower() if val is not None else None

    @property
    def pm25(self) -> int | None:
        """Return PM2.5 particulate measurement in ug/m3."""
        rep = self.reported_state
        val = rep.get("pm2_5") or rep.get("pm25") or rep.get("aqi")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def filter_life_percent(self) -> int | None:
        """Return remaining filter life percentage."""
        rep = self.reported_state
        val = rep.get("filter_life") or rep.get("filter_life_percent")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def is_child_lock_on(self) -> bool:
        """Return True if child lock is engaged."""
        rep = self.reported_state
        val = rep.get("child_lock") or rep.get("childLock")
        return bool(val)

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
