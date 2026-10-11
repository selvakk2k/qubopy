"""Base device abstraction for Qubo hardware."""

from typing import TYPE_CHECKING, Any
from qubopy.models import DeviceModelInfo, DeviceShadow

if TYPE_CHECKING:
    from qubopy.client import QuboClient


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
        shadow = await self.client.get_device_shadow(self.device_id)
        self.update_shadow(shadow)
        return shadow

    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a control command payload."""
        return await self.client.send_command(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            device_uuid=self.device_id,
            command=command,
        )

    async def update_attribute(self, attributes: dict[str, Any]) -> dict[str, Any]:
        """Update shadow attributes directly."""
        return await self.client.update_shadow_attribute(
            unit_uuid=self.unit_id,
            entity_uuid=self.entity_id,
            device_uuid=self.device_id,
            attributes=attributes,
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} model={self.model!r} id={self.device_id!r}>"
