"""Device abstractions and factory router."""

from typing import TYPE_CHECKING
from qubopy.const import (
    PREFIX_AIR_PURIFIER,
    PREFIX_CAMERA,
    PREFIX_CLIMATE_SENSOR,
    PREFIX_DOORBELL,
    PREFIX_SECURITY_SENSOR,
    PREFIX_SMART_LIGHT,
    PREFIX_SMART_LOCK,
    PREFIX_SMART_PLUG,
)
from qubopy.devices.base import QuboDevice
from qubopy.devices.camera import QuboCamera
from qubopy.devices.light import QuboLight
from qubopy.devices.lock import QuboLock
from qubopy.devices.plug import QuboPlug
from qubopy.devices.purifier import QuboAirPurifier
from qubopy.devices.sensor import QuboSensor
from qubopy.models import DeviceModelInfo, DeviceShadow

if TYPE_CHECKING:
    from qubopy.client import QuboClient

__all__ = [
    "QuboDevice",
    "QuboPlug",
    "QuboAirPurifier",
    "QuboLight",
    "QuboLock",
    "QuboCamera",
    "QuboSensor",
    "create_device",
    "is_gateway_device",
]


def is_gateway_device(device_data: dict | DeviceModelInfo) -> bool:
    """Return True if device can act as an in-home RF/BLE gateway for locks."""
    if isinstance(device_data, DeviceModelInfo):
        model = device_data.model or ""
        dev_type = device_data.device_type or ""
    elif isinstance(device_data, dict):
        model = device_data.get("deviceModel") or device_data.get("model") or ""
        dev_type = device_data.get("deviceType") or device_data.get("type") or ""
    else:
        return False

    m_upper = model.upper()
    t_lower = dev_type.lower()

    if any(m_upper.startswith(p) for p in PREFIX_DOORBELL + PREFIX_CAMERA):
        return True
    if any(k in t_lower for k in ("doorbell", "camera", "cam", "gateway", "hhl")):
        return True
    return False



def create_device(
    info: DeviceModelInfo,
    client: "QuboClient",
    shadow: DeviceShadow | None = None,
) -> QuboDevice:
    """Instantiate a typed device class based on model prefix and type."""
    model_upper = (info.model or "").upper()
    type_upper = (info.device_type or "").upper()

    # Smart Plugs
    if any(model_upper.startswith(p) for p in PREFIX_SMART_PLUG) or "PLUG" in type_upper:
        return QuboPlug(info, client, shadow)

    # Air Purifiers
    if any(model_upper.startswith(p) for p in PREFIX_AIR_PURIFIER) or "PURIFIER" in type_upper:
        return QuboAirPurifier(info, client, shadow)

    # Smart Bulbs & Lights
    if any(model_upper.startswith(p) for p in PREFIX_SMART_LIGHT) or "LIGHT" in type_upper or "BULB" in type_upper:
        return QuboLight(info, client, shadow)

    # Smart Door Locks
    if any(model_upper.startswith(p) for p in PREFIX_SMART_LOCK) or "LOCK" in type_upper:
        return QuboLock(info, client, shadow)

    # Cameras and Doorbells
    if (
        any(model_upper.startswith(p) for p in PREFIX_CAMERA)
        or any(model_upper.startswith(p) for p in PREFIX_DOORBELL)
        or "CAM" in type_upper
        or "DOORBELL" in type_upper
    ):
        return QuboCamera(info, client, shadow)

    # Sensors (Security and Climate)
    if (
        any(model_upper.startswith(p) for p in PREFIX_SECURITY_SENSOR)
        or any(model_upper.startswith(p) for p in PREFIX_CLIMATE_SENSOR)
        or "SENSOR" in type_upper
    ):
        return QuboSensor(info, client, shadow)

    # Generic device fallback
    return QuboDevice(info, client, shadow)
