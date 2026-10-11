"""Environmental and security sensor device abstraction (HDS, HGS, HSA, HDT)."""

from qubopy.devices.base import QuboDevice


class QuboSensor(QuboDevice):
    """Qubo Security and Climate Sensors."""

    @property
    def is_contact_open(self) -> bool | None:
        """Return True if door/window contact sensor is open (HDS series)."""
        rep = self.reported_state
        val = rep.get("contact") or rep.get("door_state") or rep.get("open")
        return bool(val) if val is not None else None

    @property
    def is_gas_alarm(self) -> bool:
        """Return True if flammable gas leak is detected (HGS series)."""
        rep = self.reported_state
        return bool(rep.get("gas_alarm") or rep.get("gas_detected"))

    @property
    def is_smoke_alarm(self) -> bool:
        """Return True if smoke alarm is active (HSA series)."""
        rep = self.reported_state
        return bool(rep.get("smoke_alarm") or rep.get("smoke_detected"))

    @property
    def temperature_celsius(self) -> float | None:
        """Return temperature in degrees Celsius (HDT series)."""
        rep = self.reported_state
        val = rep.get("temperature") or rep.get("temp")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def humidity_percent(self) -> float | None:
        """Return relative humidity percentage (HDT series)."""
        rep = self.reported_state
        val = rep.get("humidity") or rep.get("rh")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def battery_percent(self) -> int | None:
        """Return sensor battery level (0-100)."""
        rep = self.reported_state
        val = rep.get("battery") or rep.get("power")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None
