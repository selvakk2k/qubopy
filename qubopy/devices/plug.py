"""Smart plug device abstraction (HSP series)."""

from typing import Any

from qubopy.devices.base import QuboDevice, _as_bool, _first_not_none
from qubopy.exceptions import QuboCommandError


class QuboPlug(QuboDevice):
    """Qubo Smart Plug (HSP01 16A, HSP02 10A, HSP10)."""

    @property
    def is_on(self) -> bool:
        """Return True if plug relay is closed / switched on."""
        state = _first_not_none(self.reported_state, "state", "switch", "power_state")
        return bool(_as_bool(state))

    @property
    def power_watts(self) -> float | None:
        """Return active power consumption in Watts."""
        val = _first_not_none(self.reported_state, "power", "active_power", "watts")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def voltage(self) -> float | None:
        """Return line voltage in Volts."""
        val = _first_not_none(self.reported_state, "voltage", "volts")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def current(self) -> float | None:
        """Return line current in Amperes."""
        val = _first_not_none(self.reported_state, "current", "amps")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def energy_kwh(self) -> float | None:
        """Return cumulative energy consumption in kilowatt-hours."""
        val = _first_not_none(self.reported_state, "energy", "total_energy", "kwh")
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

    async def get_energy_history(
        self, period: str = "day"
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Fetch historical energy metering data (hour, day, month, overall)."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.get_plug_energy_history(self.device_id, period=period)
