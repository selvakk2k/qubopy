"""Tests for QuboLock Deftun P01 BLE key extraction."""

from unittest.mock import AsyncMock
import pytest
from qubopy.devices.lock import QuboLock
from qubopy.exceptions import QuboKeyExtractionError
from qubopy.models import DeviceModelInfo, DeviceShadow


@pytest.mark.asyncio
async def test_get_ble_lock_keys_success(sample_client, mock_lock_info):
    """Verify extracting P01DeviceBean cryptographic keys from metadata."""
    lock = QuboLock(mock_lock_info, sample_client)
    keys = await lock.get_ble_lock_keys()

    assert keys.device_uuid == "lock-uuid-1"
    assert keys.device_name == "Main Entrance Door"
    assert keys.mac_address == "AA:BB:CC:DD:EE:FF"
    assert keys.auth_key == "0123456789ABCDEF0123456789ABCDEF"
    assert keys.offline_key == "FEDCBA9876543210FEDCBA9876543210"
    assert keys.admin_pass == "123456"
    assert keys.battery_level == 85
    assert keys.bluetooth_name == "Qubo_HLM01_P01"
    assert keys.is_open is False


@pytest.mark.asyncio
async def test_get_ble_lock_keys_from_shadow(sample_client):
    """Verify extracting keys from shadow when not in info extraData."""
    info = DeviceModelInfo(
        uuid="lock-uuid-2",
        deviceId="lock-uuid-2",
        name="Side Gate Lock",
        model="HLM02",
        type="SmartLock",
    )
    shadow = DeviceShadow(
        device_uuid="lock-uuid-2",
        reported={
            "dmac": "11:22:33:44:55:66",
            "dbtauthkey": "SECRET_AUTH_KEY_XYZ",
            "dbtoffkey": "OFFLINE_SEED_KEY_XYZ",
            "isOpen": True,
            "dpower": 70,
        },
    )
    lock = QuboLock(info, sample_client, shadow)
    keys = await lock.get_ble_lock_keys()

    assert keys.mac_address == "11:22:33:44:55:66"
    assert keys.auth_key == "SECRET_AUTH_KEY_XYZ"
    assert keys.offline_key == "OFFLINE_SEED_KEY_XYZ"
    assert keys.battery_level == 70
    assert keys.is_open is True


@pytest.mark.asyncio
async def test_get_ble_lock_keys_missing_raises_error(sample_client):
    """Verify QuboKeyExtractionError is raised if essential keys are absent."""
    info = DeviceModelInfo(
        uuid="lock-uuid-3",
        deviceId="lock-uuid-3",
        name="Empty Lock",
        model="HLM03",
        type="SmartLock",
    )
    shadow = DeviceShadow(
        device_uuid="lock-uuid-3",
        reported={"power": 50},
    )
    lock = QuboLock(info, sample_client, shadow)
    lock.refresh = AsyncMock()

    with pytest.raises(QuboKeyExtractionError, match="Failed to locate offline BLE keys"):
        await lock.get_ble_lock_keys()
