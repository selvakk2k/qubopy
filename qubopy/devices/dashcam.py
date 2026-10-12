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

    @property
    def wifi_ap_ssid(self) -> str:
        """Return dashcam in-car Wi-Fi AP SSID name."""
        return str(self.reported_state.get("dashcam_wifi_name") or "")

    @property
    def wifi_ap_password(self) -> str:
        """Return dashcam in-car Wi-Fi AP WPA2 passphrase."""
        return str(self.reported_state.get("dashcam_wifi_password") or "")

    @property
    def overspeed_limit(self) -> int | None:
        """Return configured overspeed warning threshold in km/h."""
        val = self.reported_state.get("overspeed_limit")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def speed_unit(self) -> str:
        """Return speed display unit ('km' or 'mph')."""
        return str(self.reported_state.get("speed_unit") or "km")

    @property
    def is_audio_recording_on(self) -> bool:
        """Return True if cabin microphone audio recording is enabled."""
        val = self.reported_state.get("audio_recording")
        if val is not None:
            return bool(val)
        return True

    async def set_parking_monitoring(self, enabled: bool) -> dict[str, Any]:
        """Toggle 24/7 parking surveillance mode."""
        return await self.set_service_attribute(
            service="parkingConfig",
            attribute="state",
            value="enable" if enabled else "disable",
        )

    async def set_overspeed_limit(self, limit_kmh: int) -> dict[str, Any]:
        """Configure GPS overspeed alert threshold."""
        return await self.set_service_attribute(
            service="dashcamGpsConfig",
            attribute="overSpeedLimits",
            value=str(limit_kmh),
        )

    async def set_audio_recording(self, enabled: bool) -> dict[str, Any]:
        """Toggle cabin audio recording in dashcam video files."""
        return await self.set_service_attribute(
            service="dashcamRecordingConfig",
            attribute="audioTrack",
            value="enable" if enabled else "disable",
        )
