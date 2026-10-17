"""Base device abstraction for Qubo hardware."""

import logging
from typing import TYPE_CHECKING, Any

from qubopy.exceptions import QuboCommandError
from qubopy.models import DeviceModelInfo, DeviceShadow

if TYPE_CHECKING:
    from qubopy.client import QuboClient

_LOGGER = logging.getLogger(__name__)


def _first_not_none(mapping: dict[str, Any] | None, *keys: str) -> Any:
    """Return the value of the first key in mapping whose value is not None."""
    if not mapping or not isinstance(mapping, dict):
        return None
    for k in keys:
        if k in mapping and mapping[k] is not None:
            return mapping[k]
    return None


def _as_bool(val: Any) -> bool | None:
    """Coerce boolean, integer, or string representations into bool or None."""
    if val is None or isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val in (1, 1.0):
            return True
        if val in (0, 0.0):
            return False
        return None
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes", "on", "enable", "enabled"):
            return True
        if v in ("false", "0", "no", "off", "disable", "disabled"):
            return False
        _LOGGER.debug("Unrecognized boolean string value: %r", val)
        return None
    return None


def _parse_battery_level(val: Any) -> int | None:
    """Safely parse battery percentage from int, float, or string and clamp 0-100."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            pct = int(round(val))
        elif isinstance(val, str):
            clean = val.strip().rstrip("%").strip()
            if not clean:
                return None
            pct = int(round(float(clean)))
        else:
            return None
        return max(0, min(100, pct))
    except (ValueError, TypeError):
        return None


class QuboDevice:
    """Base class for all Qubo appliances and peripherals."""

    def __init__(
        self,
        info: DeviceModelInfo,
        client: "QuboClient",
        shadow: DeviceShadow | None = None,
    ) -> None:
        self.info = info
        self.client = client
        self.shadow = shadow or DeviceShadow(device_uuid=self.device_id)

    @property
    def device_id(self) -> str:
        """Return unique device UUID."""
        return self.info.uuid or self.info.device_id

    @property
    def name(self) -> str:
        """Return human-readable device name."""
        return self.info.name

    @property
    def model(self) -> str:
        """Return device model string."""
        return self.info.model

    @property
    def unit_id(self) -> str:
        """Return parent unit UUID."""
        return self.info.unit_uuid

    @property
    def entity_id(self) -> str:
        """Return parent entity UUID."""
        return self.info.entity_uuid

    @property
    def is_online(self) -> bool:
        """Return whether device is reported online."""
        return self.info.is_online

    @property
    def reported_state(self) -> dict[str, Any]:
        """Return raw reported shadow state."""
        return self.shadow.reported

    def update_shadow(self, shadow: DeviceShadow) -> None:
        """Update cached shadow state."""
        self.shadow = shadow

    async def refresh(self) -> DeviceShadow:
        """Fetch and cache latest device shadow state from cloud."""
        shadow = await self.client.get_device_shadow(
            device_uuid=self.device_id,
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
        )
        self.update_shadow(shadow)
        return shadow

    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a control command payload."""
        if not self.unit_id or not self.entity_id:
            raise QuboCommandError(
                f"{self.name} has no unit/entity binding and cannot be commanded"
            )
        return await self.client.send_command(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            device_uuid=self.device_id,
            command=command,
        )

    async def update_attribute(self, attributes: dict[str, Any]) -> dict[str, Any]:
        """Update shadow attributes directly."""
        if not self.unit_id or not self.entity_id:
            raise QuboCommandError(
                f"{self.name} has no unit/entity binding and cannot be commanded"
            )
        return await self.client.update_shadow_attribute(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            device_uuid=self.device_id,
            attributes=attributes,
        )

    async def read_attribute_v2(self, service: str, attribute: str) -> dict[str, Any]:
        """Read one attribute with its device-reported timestamp via the v2 shadow."""
        if not self.client:
            raise QuboCommandError("Device client not initialized")
        return await self.client.get_device_shadow_v2(
            device_uuid=self.device_id,
            service_name=service,
            attribute_name=attribute,
        )

    async def write_attribute(
        self, service: str, attribute: str, value: Any, instance_id: int = 0
    ) -> dict[str, Any]:
        """Write one shadow attribute directly using the official cloud envelope."""
        val_str = str(value).lower() if isinstance(value, bool) else str(value)
        payload = {
            "instanceId": instance_id,
            "serviceName": service,
            "attributeName": attribute,
            "attributeValue": val_str,
        }
        return await self.update_attribute(payload)

    async def set_service_attribute(
        self, service: str, attribute: str, value: Any, instance_id: int = 0
    ) -> dict[str, Any]:
        """Update a specific service attribute in the device shadow."""
        return await self.write_attribute(
            service=service,
            attribute=attribute,
            value=value,
            instance_id=instance_id,
        )

    async def send_service_command(
        self,
        service: str,
        command: str,
        parameters: dict[str, Any] | None = None,
        instance_id: int = 0,
    ) -> dict[str, Any]:
        """Dispatch a control command using the official cloud envelope."""
        payload = {
            "devices": {
                "handleName": self.name,
                "deviceUUID": self.device_id,
                "services": {
                    service: {
                        "commands": {
                            command: {
                                "parameters": parameters or {},
                                "instanceId": instance_id,
                            }
                        }
                    }
                },
            }
        }
        return await self.send_command(payload)

    async def reboot(self) -> dict[str, Any]:
        """Send a restart command to the device."""
        return await self.send_service_command("deviceReboot", "reboot")

    def __repr__(self) -> str:
        cls_name = self.__class__.__name__
        return f"<{cls_name} name={self.name!r} model={self.model!r} id={self.device_id!r}>"
