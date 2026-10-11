"""Smart lighting device abstraction (HLB series)."""

from typing import Any
from qubopy.devices.base import QuboDevice


class QuboLight(QuboDevice):
    """Qubo Smart Lighting (HLB01, HLB10)."""

    @property
    def is_on(self) -> bool:
        """Return True if light is illuminated."""
        rep = self.reported_state
        state = rep.get("state") or rep.get("switch") or rep.get("power")
        if isinstance(state, str):
            return state.upper() in ("ON", "1", "TRUE")
        if isinstance(state, (int, float)):
            return state == 1
        if isinstance(state, bool):
            return state
        return False

    @property
    def brightness(self) -> int | None:
        """Return brightness level (0 to 100)."""
        rep = self.reported_state
        val = rep.get("brightness") or rep.get("dimmer")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def color_temp(self) -> int | None:
        """Return color temperature value."""
        rep = self.reported_state
        val = rep.get("color_temp") or rep.get("cct") or rep.get("temperature")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return (red, green, blue) color tuple if active."""
        rep = self.reported_state
        rgb = rep.get("rgb") or rep.get("color")
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            try:
                return (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            except (ValueError, TypeError):
                pass
        return None

    async def turn_on(
        self,
        brightness: int | None = None,
        rgb: tuple[int, int, int] | None = None,
        color_temp: int | None = None,
    ) -> dict[str, Any]:
        """Turn on the light with optional brightness and color parameters."""
        cmd: dict[str, Any] = {"state": "ON", "switch": True}
        if brightness is not None:
            cmd["brightness"] = max(0, min(100, brightness))
        if rgb is not None:
            cmd["rgb"] = [rgb[0], rgb[1], rgb[2]]
        if color_temp is not None:
            cmd["color_temp"] = color_temp
        return await self.send_command(cmd)

    async def turn_off(self) -> dict[str, Any]:
        """Turn off the light."""
        return await self.send_command({"state": "OFF", "switch": False})

    async def set_brightness(self, level: int) -> dict[str, Any]:
        """Adjust brightness level (0-100)."""
        clamped = max(0, min(100, level))
        return await self.send_command({"brightness": clamped})

    async def set_rgb(self, r: int, g: int, b: int) -> dict[str, Any]:
        """Set RGB color."""
        return await self.send_command({"rgb": [r, g, b]})

    async def set_color_temp(self, temp: int) -> dict[str, Any]:
        """Set white color temperature."""
        return await self.send_command({"color_temp": temp})
