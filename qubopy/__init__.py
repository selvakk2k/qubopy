"""Qubo Python Client Library & BLE Enabler."""

from importlib.metadata import PackageNotFoundError, version

from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.devices import (
    QuboAirPurifier,
    QuboCamera,
    QuboDevice,
    QuboLight,
    QuboLock,
    QuboPlug,
    QuboSensor,
    create_device,
)
from qubopy.exceptions import (
    QuboAuthError,
    QuboCommandError,
    QuboConnectionError,
    QuboDeviceNotFoundError,
    QuboError,
    QuboKeyExtractionError,
)
from qubopy.models import (
    BleLockCredentials,
    DeviceModelInfo,
    DeviceShadow,
    Entity,
    RtspStreamInfo,
    TokenPayload,
    Unit,
)

try:
    __version__ = version("qubopy")
except PackageNotFoundError:
    __version__ = "0.1.0-alpha.1"

__all__ = [
    "BleLockCredentials",
    "DeviceModelInfo",
    "DeviceShadow",
    "Entity",
    "QuboAirPurifier",
    "QuboAuth",
    "QuboAuthError",
    "QuboCamera",
    "QuboClient",
    "QuboCommandError",
    "QuboConnectionError",
    "QuboDevice",
    "QuboDeviceNotFoundError",
    "QuboError",
    "QuboKeyExtractionError",
    "QuboLight",
    "QuboLock",
    "QuboPlug",
    "QuboSensor",
    "RtspStreamInfo",
    "TokenPayload",
    "Unit",
    "__version__",
    "create_device",
]
