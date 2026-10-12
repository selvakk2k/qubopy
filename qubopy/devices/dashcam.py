"""Automotive dashcam device abstraction (HCA series, Qubo Go / Qubo Pro)."""

from typing import Any
from qubopy.devices.base import QuboDevice


class QuboDashcam(QuboDevice):
    """Qubo Smart Dashcam (HCA01-08, 2K Dashcam, 4K Dashcam, Dashcam Pro)."""

    @property
    def serial_number(self) -> str:
        """Return dashcam hardware serial number."""
        return str(self.info.extra_data.get("serialNumber") or "")

    @property
    def is_recording(self) -> bool:
        """Return True if dashcam loop recording is currently active."""
        rep = self.reported_state
        val = rep.get("recording") or rep.get("isRecording") or rep.get("loop_record")
        return bool(val)

    @property
    def sd_card_status(self) -> str | None:
        """Return SD card state (e.g. NORMAL, ERROR, FULL, NOT_INSERTED)."""
        rep = self.reported_state
        return rep.get("sdcard_status") or rep.get("sdStatus") or rep.get("sd_card")

    @property
    def is_parking_monitoring_on(self) -> bool:
        """Return True if 24/7 parking surveillance mode is enabled."""
        rep = self.reported_state
        val = rep.get("parking_mode") or rep.get("parkingMonitoring")
        return bool(val)
