"""Tests for QuboClient REST operations and discovery."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.devices import QuboLock, QuboPlug
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
    units_data = [{"unitUUID": "u1", "name": "Kitchen"}]
    devices_data = [
        {
            "deviceId": "plug-01",
            "name": "Kitchen Plug",
            "model": "HSP01",
            "type": "SmartPlug",
            "state": {"reported": {"state": "ON", "power": 85.0}},
        }
    ]

    def mock_request(method, url, **kwargs):
        if "/devices" in url:
            return MockClientResponse(200, json.dumps(devices_data))
        return MockClientResponse(200, json.dumps(units_data))

    with patch("aiohttp.ClientSession.request", side_effect=mock_request):
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


@pytest.mark.asyncio
async def test_get_units_and_devices_hierarchy(sample_client):
    """Verify hierarchical discovery via units and unit devices."""
    units_payload = [{"unitUUID": "unit-home-1", "name": "My Home"}]
    devices_payload = [
        {
            "deviceUUID": "cam-100",
            "deviceName": "Front Door Cam",
            "deviceModel": "HCP01",
            "deviceType": "Camera",
            "unitUUID": "unit-home-1",
            "isOnline": True,
        }
    ]

    def mock_request(method, url, **kwargs):
        if "/units/unit-home-1/devices" in url:
            return MockClientResponse(200, json.dumps(devices_payload))
        if "/units" in url:
            return MockClientResponse(200, json.dumps(units_payload))
        return MockClientResponse(404, "{}")

    with patch("aiohttp.ClientSession.request", side_effect=mock_request):
        units = await sample_client.get_units()
        assert len(units) == 1
        assert units[0]["unitUUID"] == "unit-home-1"

        unit_devs = await sample_client.get_devices_for_unit("unit-home-1")
        assert len(unit_devs) == 1
        assert unit_devs[0]["deviceUUID"] == "cam-100"

        devices = await sample_client.get_all_devices()
        assert len(devices) == 1
        cam = devices[0]
        assert cam.device_id == "cam-100"
        assert cam.name == "Front Door Cam"
        assert cam.model == "HCP01"

    await sample_client.close()


@pytest.mark.asyncio
async def test_lock_gateway_auto_association(sample_client):
    """Verify sibling gateway device is auto-associated with a smart lock."""
    units_payload = [{"unitUUID": "unit-home-1", "name": "My Home"}]
    devices_payload = [
        {
            "deviceUUID": "cam-100",
            "deviceName": "Living Room Cam",
            "deviceModel": "HCP01",
            "deviceType": "Camera",
            "unitUUID": "unit-home-1",
        },
        {
            "deviceUUID": "lock-200",
            "deviceName": "Main Door Lock",
            "deviceModel": "HLM01",
            "deviceType": "SmartDoorLock",
            "unitUUID": "unit-home-1",
        },
    ]

    def mock_request(method, url, **kwargs):
        if "/devices" in url:
            return MockClientResponse(200, json.dumps(devices_payload))
        return MockClientResponse(200, json.dumps(units_payload))

    with patch("aiohttp.ClientSession.request", side_effect=mock_request):
        devices = await sample_client.get_all_devices()
        assert len(devices) == 2
        lock = next(d for d in devices if isinstance(d, QuboLock))
        assert lock.gateway_id == "cam-100"
        assert lock.is_gateway_accessible is True

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_401_real_refresh_retry():
    """Bug 1: Real QuboAuth with token expiring in 1 hour should actually refresh on 401."""
    auth = QuboAuth(base_url="https://srvcapp.platform.quboworld.com:443")
    # Active token expiring in 1 hour (3600 seconds)
    auth.set_tokens(
        access_token="initial-valid-token-for-1-hour",
        refresh_token="valid-refresh-token",
        user_uuid="user-1",
        expires_at=time.time() + 3600,
    )
    client = QuboClient(auth)

    refresh_called = False
    requests_handled = []

    def mock_post(url, *args, **kwargs):
        nonlocal refresh_called
        if "auth/refresh" in url:
            refresh_called = True
            return MockClientResponse(
                200,
                json.dumps({
                    "accessToken": "newly-refreshed-jwt-token",
                    "refreshToken": "new-refresh-token",
                }),
            )
        return MockClientResponse(404, "Not Found")

    def mock_request(method, url, *args, **kwargs):
        headers = kwargs.get("headers", {})
        token_sent = headers.get("Authorization", "")
        requests_handled.append(token_sent)
        if len(requests_handled) == 1:
            # First call returns 401
            return MockClientResponse(401, json.dumps({"error": "Revoked"}))
        # Retry call succeeds
        return MockClientResponse(200, json.dumps({"success": True}))

    with patch("aiohttp.ClientSession.post", side_effect=mock_post), \
         patch("aiohttp.ClientSession.request", side_effect=mock_request):
        res = await client.request("GET", "/test/data")
        assert res == {"success": True}
        assert refresh_called is True
        assert len(requests_handled) == 2
        assert requests_handled[0] == "Bearer initial-valid-token-for-1-hour"
        assert requests_handled[1] == "Bearer newly-refreshed-jwt-token"

    await client.close()


@pytest.mark.asyncio
async def test_client_concurrent_401_single_refresh():
    """Two simultaneous requests hitting 401 trigger exactly one refresh call."""
    auth = QuboAuth(base_url="https://srvcapp.platform.quboworld.com:443")
    auth.set_tokens(
        access_token="initial-token",
        refresh_token="valid-refresh-token",
        user_uuid="user-1",
        expires_at=time.time() + 3600,
    )
    client = QuboClient(auth)

    refresh_count = 0

    def mock_post(url, *args, **kwargs):
        nonlocal refresh_count
        if "auth/refresh" in url:
            refresh_count += 1
            return MockClientResponse(
                200,
                json.dumps({
                    "accessToken": "newly-refreshed-jwt-token",
                    "refreshToken": "new-refresh-token",
                }),
                delay=0.01,
            )
        return MockClientResponse(404, "Not Found")

    def mock_request(method, url, *args, **kwargs):
        headers = kwargs.get("headers", {})
        token_sent = headers.get("Authorization", "")
        if token_sent == "Bearer initial-token":
            return MockClientResponse(401, json.dumps({"error": "Revoked"}))
        return MockClientResponse(200, json.dumps({"status": "OK"}))

    with patch("aiohttp.ClientSession.post", side_effect=mock_post), \
         patch("aiohttp.ClientSession.request", side_effect=mock_request):
        results = await asyncio.gather(
            client.request("GET", "/test/res1"),
            client.request("GET", "/test/res2"),
        )
        assert results == [{"status": "OK"}, {"status": "OK"}]
        assert refresh_count == 1

    await client.close()


@pytest.mark.asyncio
async def test_client_retry_propagates_500_error(sample_client):
    """Bug 2: When retry returns 500, caller sees QuboCommandError, not QuboAuthError."""
    sample_client.auth.set_tokens(
        access_token="tok1",
        refresh_token="ref1",
        user_uuid="user-1",
    )

    call_count = 0

    def mock_handler(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockClientResponse(401, json.dumps({"error": "Unauthorized"}))
        return MockClientResponse(500, "Internal Server Error")

    with patch.object(sample_client.auth, "refresh_session", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = sample_client.auth.set_tokens(
            access_token="tok2",
            refresh_token="ref1",
            user_uuid="user-1",
        )
        with patch("aiohttp.ClientSession.request", side_effect=mock_handler):
            with pytest.raises(QuboCommandError):
                await sample_client.request("GET", "/test/error")
            assert call_count == 2

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_url_validation_rejections(sample_client):
    """Bug 3: Reject lookalike hosts, userinfo forms, and allow valid paths."""
    # Lookalike suffix
    with pytest.raises(ValueError, match="Invalid request URL"):
        await sample_client.request("GET", "https://srvcapp.platform.quboworld.com:443.evil.com/api")

    # Userinfo form
    with pytest.raises(ValueError, match="Invalid request URL"):
        await sample_client.request("GET", "https://srvcapp.platform.quboworld.com:443@evil.com/api")

    # Relative path works normally
    mock_resp = MockClientResponse(200, json.dumps({"ok": True}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp):
        res = await sample_client.request("GET", "/valid/relative/path")
        assert res == {"ok": True}

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_all_shadows_reraises_auth_error(sample_client):
    """Verify that get_all_shadows does not mask 401 as an empty dict."""
    mock_resp = MockClientResponse(401, json.dumps({"error": "Unauthorized"}))
    with (
        patch("aiohttp.ClientSession.request", return_value=mock_resp),
        pytest.raises(QuboAuthError),
    ):
        await sample_client.get_all_shadows()

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_units_reraises_auth_error(sample_client):
    """Verify that get_units does not mask authentication failures as an empty list."""
    mock_resp = MockClientResponse(401, json.dumps({"error": "Unauthorized"}))
    with (
        patch("aiohttp.ClientSession.request", return_value=mock_resp),
        pytest.raises(QuboAuthError),
    ):
        await sample_client.get_units()

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_devices_for_unit_reraises_auth_error(sample_client):
    """Verify that get_devices_for_unit does not mask authentication failures as an empty list."""
    mock_resp = MockClientResponse(401, json.dumps({"error": "Unauthorized"}))
    with (
        patch("aiohttp.ClientSession.request", return_value=mock_resp),
        pytest.raises(QuboAuthError),
    ):
        await sample_client.get_devices_for_unit("unit-123")

    await sample_client.close()



