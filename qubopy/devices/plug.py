"""Smart plug device abstraction (HSP series)."""

from typing import Any
from qubopy.devices.base import QuboDevice


class QuboPlug(QuboDevice):
    """Qubo Smart Plug (HSP01 16A, HSP02 10A, HSP10)."""

    @property
    def is_on(self) -> bool:
        """Return True if plug relay is closed / switched on."""
        rep = self.reported_state
        state = rep.get("state") or rep.get("switch") or rep.get("power_state")
        if isinstance(state, str):
            return state.upper() in ("ON", "1", "TRUE")
        if isinstance(state, (int, float)):
            return state == 1
        if isinstance(state, bool):
            return state
        return False

    @property
    def power_watts(self) -> float | None:
        """Return active power consumption in Watts."""
        rep = self.reported_state
        val = rep.get("power") or rep.get("active_power") or rep.get("watts")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def voltage(self) -> float | None:
        """Return line voltage in Volts."""
        rep = self.reported_state
        val = rep.get("voltage") or rep.get("volts")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def current(self) -> float | None:
        """Return line current in Amperes."""
        rep = self.reported_state
        val = rep.get("current") or rep.get("amps")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def energy_kwh(self) -> float | None:
        """Return cumulative energy consumption in kilowatt-hours."""
        rep = self.reported_state
        val = rep.get("energy") or rep.get("total_energy") or rep.get("kwh")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    async def turn_on(self) -> dict[str, Any]:
        """Switch the plug relay on."""
        return await self.send_command({"state": "ON", "switch": True})

    async def turn_off(self) -> dict[str, Any]:
        """Switch the plug relay off."""
        return await self.send_command({"state": "OFF", "switch": False})
