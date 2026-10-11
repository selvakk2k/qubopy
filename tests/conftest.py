"""Shared pytest fixtures and mock utilities."""

import pytest
from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.models import DeviceModelInfo, DeviceShadow


@pytest.fixture
def sample_auth():
    """Return an authenticated QuboAuth instance."""
    auth = QuboAuth()
    auth.set_tokens(
        access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE5OTk5OTk5OTksInV1aWQiOiJ1c2VyLTEyMyJ9.signature",
        refresh_token="ref-tok-abc-123",
        user_uuid="user-123",
    )
    return auth


@pytest.fixture
def sample_client(sample_auth):
    """Return a QuboClient instance with pre-configured auth."""
    return QuboClient(sample_auth)


@pytest.fixture
def mock_plug_info():
    """Return sample DeviceModelInfo for HSP01 Smart Plug."""
    return DeviceModelInfo(
        uuid="plug-uuid-1",
        deviceId="plug-uuid-1",
        name="Geyser Smart Plug",
        model="HSP01",
        type="SmartPlug",
        unitUUID="unit-1",
        entityUUID="entity-1",
        isOnline=True,
    )


@pytest.fixture
def mock_lock_info():
    """Return sample DeviceModelInfo for HLM01 Smart Lock with Deftun P01 keys."""
    return DeviceModelInfo(
        uuid="lock-uuid-1",
        deviceId="lock-uuid-1",
        name="Main Entrance Door",
        model="HLM01",
        type="SmartLock",
        unitUUID="unit-1",
        entityUUID="entity-1",
        isOnline=True,
        extraData={
            "dmac": "AA:BB:CC:DD:EE:FF",
            "dbtauthkey": "0123456789ABCDEF0123456789ABCDEF",
            "dbtoffkey": "FEDCBA9876543210FEDCBA9876543210",
            "dbtoffkeyflag": "1",
            "dadminpass": "123456",
            "dadminflag": "1",
            "dbtname": "Qubo_HLM01_P01",
            "dpower": 85,
            "isOpen": False,
        },
    )
