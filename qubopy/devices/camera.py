"""Smart camera and doorbell device abstraction (HCP, HCO, HCD series)."""

from typing import Any

from qubopy.devices.base import QuboDevice, _as_bool, _first_not_none
from qubopy.exceptions import QuboCommandError
from qubopy.models import RtspStreamInfo


class QuboCamera(QuboDevice):
    """Qubo Smart Camera and Video Doorbell (HCP01-19, HCO04-07, HCD01/04)."""

    @property
    def is_privacy_mode_on(self) -> bool:
        """Return True if privacy mask / lens shutter is closed or camera disabled."""
        rep = self.reported_state
        if "camera_enabled" in rep:
            cam_en = _as_bool(rep["camera_enabled"])
            if cam_en is not None:
                return not cam_en
        val = _first_not_none(rep, "privacy", "privacy_mode", "lens_mask")
        return bool(_as_bool(val))

    @property
    def is_siren_on(self) -> bool:
        """Return True if camera alarm siren is sounding."""
        val = _first_not_none(self.reported_state, "siren", "alarm")
        return bool(_as_bool(val))

    @property
    def is_motion_detected(self) -> bool:
        """Return True if motion sensor is currently active."""
        val = _first_not_none(self.reported_state, "motion", "motion_detected")
        return bool(_as_bool(val))

    @property
    def is_person_detected(self) -> bool:
        """Return True if AI person recognition is currently triggered."""
        val = _first_not_none(self.reported_state, "person", "person_detected")
        return bool(_as_bool(val))

    @property
    def is_motion_tracking_on(self) -> bool:
        """Return True if auto motion tracking is enabled."""
        val = _first_not_none(self.reported_state, "motion_tracking")
        return bool(_as_bool(val))

    @property
    def night_mode(self) -> str:
        """Return active night vision mode ('true', 'false', 'auto')."""
        return str(self.reported_state.get("night_mode") or "auto")

    @property
    def pan_tilt_position(self) -> str:
        """Return pan and tilt coordinates (e.g. '0,-181')."""
        return str(self.reported_state.get("ptz_position") or "")

    @property
    def lan_ip_address(self) -> str:
        """Return local network IP address if reported by device."""
        return str(self.reported_state.get("ip_address") or "")

    @property
    def wifi_rssi(self) -> int | None:
        """Return Wi-Fi signal strength in dBm."""
        val = self.reported_state.get("signal_strength")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def wifi_ssid(self) -> str:
        """Return connected Wi-Fi SSID name."""
        return str(self.reported_state.get("wifi_ssid") or "")

    @property
    def sd_card_status(self) -> str:
        """Return SD storage status (e.g. 'statusOk')."""
        return str(self.reported_state.get("sd_card_status") or "")

    @property
    def sd_storage_free_mb(self) -> float | None:
        """Return available SD card storage in megabytes."""
        val = self.reported_state.get("sd_available_storage")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def sd_storage_total_mb(self) -> float | None:
        """Return total SD card storage in megabytes."""
        val = self.reported_state.get("sd_total_storage")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    async def start_stream(self, quality: str = "high") -> str:
        """Mint and return a live single-consumer Wowza RTSPS video stream URL."""
        return await self.client.get_live_stream_url(
            unit_uuid=self.unit_id,
            device_uuid=self.device_id,
            device_type=self.info.device_type,
            quality=quality,
        )

    async def get_rtsp_info(self) -> RtspStreamInfo:
        """Query camera RTSP streaming support and endpoint details."""
        return await self.client.get_camera_rtsp_support(self.unit_id, self.device_id)

    async def set_privacy_mode(self, enabled: bool) -> dict[str, Any]:
        """Toggle privacy mode (disables camera sensor and rolls lens)."""
        return await self.set_service_attribute(
            service="cameraFunction",
            attribute="state",
            value="disable" if enabled else "enable",
        )

    async def set_night_mode(self, mode: str) -> dict[str, Any]:
        """Configure night mode ('true', 'false', 'auto')."""
        return await self.set_service_attribute(
            service="nightModeControl",
            attribute="nightMode",
            value=mode,
        )

    async def set_motion_tracking(self, enabled: bool) -> dict[str, Any]:
        """Toggle pan/tilt auto motion tracking."""
        return await self.set_service_attribute(
            service="motionTracking",
            attribute="enabled",
            value="true" if enabled else "false",
        )

    async def pan_tilt(self, x: int, y: int) -> dict[str, Any]:
        """Command camera PTZ motors to target horizontal and vertical position."""
        return await self.set_service_attribute(
            service="panTiltControl",
            attribute="horizontalVerticalPostion",
            value=f"{x},{y}",
        )

    async def set_siren(self, enabled: bool) -> dict[str, Any]:
        """Trigger or dismiss the deterrent siren."""
        return await self.send_command({"siren": enabled})

    async def get_events(
        self,
        version: str = "v2",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch timeline events. Use version='v3' for direct media download URLs."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.get_device_events(
            self.unit_id,
            self.device_id,
            version=version,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    async def get_storage_info(self) -> dict[str, Any]:
        """Fetch SD card capacity, status, and partition diagnostics."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.get_device_storage(self.unit_id, self.device_id)
