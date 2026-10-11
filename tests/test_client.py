"""Tests for QuboClient REST operations and discovery."""

import json
from unittest.mock import patch
import pytest

from qubopy.client import QuboClient
from qubopy.devices import QuboPlug
from qubopy.exceptions import QuboAuthError, QuboCommandError
from tests.test_auth import MockClientResponse


@pytest.mark.asyncio
async def test_get_all_shadows(sample_client):
    """Verify fetching bulk shadows."""
    bulk_data = [
        {
            "deviceId": "dev-001",
            "state": {"reported": {"state": "ON", "power": 1250.5}},
            "timestamp": 1690000000,
        },
        {
            "deviceId": "dev-002",
            "state": {"reported": {"state": "OFF"}},
            "timestamp": 1690000005,
        },
    ]

    mock_resp = MockClientResponse(200, json.dumps(bulk_data))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp):
        shadows = await sample_client.get_all_shadows()
        assert len(shadows) == 2
        assert "dev-001" in shadows
        assert shadows["dev-001"].reported["state"] == "ON"
        assert shadows["dev-001"].reported["power"] == 1250.5

    await sample_client.close()


@pytest.mark.asyncio
async def test_get_all_devices_factory(sample_client):
    """Verify device factory correctly instantiates typed devices."""
    bulk_data = [
        {
            "deviceId": "plug-01",
            "name": "Kitchen Plug",
            "model": "HSP01",
            "type": "SmartPlug",
            "state": {"reported": {"state": "ON", "power": 85.0}},
        }
    ]

    mock_resp = MockClientResponse(200, json.dumps(bulk_data))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp):
        devices = await sample_client.get_all_devices()
        assert len(devices) == 1
        device = devices[0]
        assert isinstance(device, QuboPlug)
        assert device.is_on is True
        assert device.power_watts == 85.0

    await sample_client.close()


@pytest.mark.asyncio
async def test_send_command(sample_client):
    """Verify command dispatching via POST."""
    cmd_resp = {"status": "SUCCESS"}
    mock_resp = MockClientResponse(200, json.dumps(cmd_resp))

    with patch("aiohttp.ClientSession.request", return_value=mock_resp):
        res = await sample_client.send_command(
            unit_uuid="u1", entity_uuid="e1", device_uuid="d1", command={"state": "ON"}
        )
        assert res["status"] == "SUCCESS"

    await sample_client.close()


@pytest.mark.asyncio
async def test_camera_rtsp_query(sample_client):
    """Verify camera RTSP query parser."""
    rtsp_resp = {
        "supported": True,
        "rtspUrl": "rtsp://192.168.1.50:554/live/ch0",
        "authRequired": True,
    }
    mock_resp = MockClientResponse(200, json.dumps(rtsp_resp))

    with patch("aiohttp.ClientSession.request", return_value=mock_resp):
        rtsp = await sample_client.get_camera_rtsp_support("u1", "cam-01")
        assert rtsp.is_supported is True
        assert rtsp.stream_url == "rtsp://192.168.1.50:554/live/ch0"
        assert rtsp.auth_required is True

    await sample_client.close()
