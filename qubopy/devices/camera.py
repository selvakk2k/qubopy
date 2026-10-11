"""Smart camera and doorbell device abstraction (HCP, HCO, HCD series)."""

from typing import Any
from qubopy.devices.base import QuboDevice
from qubopy.models import RtspStreamInfo


class QuboCamera(QuboDevice):
    """Qubo Smart Camera and Video Doorbell (HCP01-19, HCO04-07, HCD01/04)."""

    @property
    def is_privacy_mode_on(self) -> bool:
        """Return True if privacy mask / lens shutter is closed."""
        rep = self.reported_state
        val = rep.get("privacy") or rep.get("privacy_mode") or rep.get("lens_mask")
        return bool(val)

    @property
    def is_siren_on(self) -> bool:
        """Return True if camera alarm siren is sounding."""
        rep = self.reported_state
        val = rep.get("siren") or rep.get("alarm")
        return bool(val)

    @property
    def is_motion_detected(self) -> bool:
        """Return True if motion sensor is currently active."""
        rep = self.reported_state
        val = rep.get("motion") or rep.get("motion_detected")
        return bool(val)

    @property
    def is_person_detected(self) -> bool:
        """Return True if AI person recognition is currently triggered."""
        rep = self.reported_state
        val = rep.get("person") or rep.get("person_detected")
        return bool(val)

    async def get_rtsp_info(self) -> RtspStreamInfo:
        """Query camera RTSP streaming support and endpoint details."""
        return await self.client.get_camera_rtsp_support(self.unit_id, self.device_id)

    async def set_privacy_mode(self, enabled: bool) -> dict[str, Any]:
        """Toggle privacy mode (shuts off stream and tilts lens)."""
        return await self.send_command({"privacy_mode": enabled, "privacy": enabled})

    async def set_siren(self, enabled: bool) -> dict[str, Any]:
        """Trigger or dismiss the deterrent siren."""
        return await self.send_command({"siren": enabled})
