"""Environmental and security sensor device abstraction (HDS, HGS, HSA, HDT)."""

from qubopy.devices.base import (
    QuboDevice,
    _as_bool,
    _first_not_none,
    _parse_battery_level,
)


class QuboSensor(QuboDevice):
    """Qubo Security and Climate Sensors."""

    @property
    def is_contact_open(self) -> bool | None:
        """Return True if door/window contact sensor is open (HDS series)."""
        val = _first_not_none(self.reported_state, "contact", "door_state", "open")
        return _as_bool(val)

    @property
    def is_gas_alarm(self) -> bool:
        """Return True if flammable gas leak is detected (HGS series)."""
        val = _first_not_none(self.reported_state, "gas_alarm", "gas_detected")
        return bool(_as_bool(val))

    @property
    def is_smoke_alarm(self) -> bool:
        """Return True if smoke alarm is active (HSA series)."""
        val = _first_not_none(self.reported_state, "smoke_alarm", "smoke_detected")
        return bool(_as_bool(val))

    @property
    def temperature_celsius(self) -> float | None:
        """Return temperature in degrees Celsius (HDT series)."""
        val = _first_not_none(self.reported_state, "temperature", "temp")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def humidity_percent(self) -> float | None:
        """Return relative humidity percentage (HDT series)."""
        val = _first_not_none(self.reported_state, "humidity", "rh")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def battery_percent(self) -> int | None:
        """Return sensor battery level (0-100)."""
        val = _first_not_none(self.reported_state, "battery", "power")
        return _parse_battery_level(val)
