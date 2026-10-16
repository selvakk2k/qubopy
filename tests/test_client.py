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
from tests.conftest import MockClientResponse


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

    with (
        patch.object(
            sample_client.auth, "refresh_session", new_callable=AsyncMock
        ) as mock_refresh,
        patch("aiohttp.ClientSession.request", side_effect=mock_handler),
    ):
        mock_refresh.return_value = sample_client.auth.set_tokens(
            access_token="tok2",
            refresh_token="ref1",
            user_uuid="user-1",
        )
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


@pytest.mark.asyncio
async def test_client_get_device_shadow_v2(sample_client):
    """Verify get_device_shadow_v2 calls the v2 deviceshadow path with params."""
    mock_resp = MockClientResponse(
        200, json.dumps({"attributeValue": "unlocked", "timestamp": 123456789})
    )
    with patch("aiohttp.ClientSession.request", return_value=mock_resp) as mock_req:
        res = await sample_client.get_device_shadow_v2(
            "lock-123", service_name="lockControl", attribute_name="lockState"
        )
        assert res["attributeValue"] == "unlocked"
        mock_req.assert_called_once()
        call_url = mock_req.call_args[0][1]
        assert "/api/v2/sp/" in call_url
        assert "/devices/lock-123/deviceshadow" in call_url
        assert mock_req.call_args[1]["params"] == {
            "serviceName": "lockControl",
            "attributeName": "lockState",
        }

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_device_events(sample_client):
    """Verify get_device_events supports v2 metadata and v3 video clip downloads."""
    mock_resp_v2 = MockClientResponse(200, json.dumps({"events": [{"id": "ev1"}]}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_v2) as mock_req:
        evs = await sample_client.get_device_events(
            "unit-1", "cam-1", version="v2", limit=20
        )
        assert evs == [{"id": "ev1"}]
        assert "/content-manager/api/v2/" in mock_req.call_args[0][1]
        assert mock_req.call_args[1]["params"]["limit"] == 20

    mock_resp_v3 = MockClientResponse(
        200, json.dumps([{"id": "ev2", "downloadUrl": "https://s3/clip.mp4"}])
    )
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_v3) as mock_req:
        evs = await sample_client.get_device_events("unit-1", "cam-1", version="v3")
        assert evs == [{"id": "ev2", "downloadUrl": "https://s3/clip.mp4"}]
        assert "/content-manager/api/v3/" in mock_req.call_args[0][1]

    with pytest.raises(ValueError, match="Unsupported device events version"):
        await sample_client.get_device_events("unit-1", "cam-1", version="v4")

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_generate_lock_otp(sample_client):
    """Verify generate_lock_otp calls roi-manager POST endpoint."""
    mock_resp = MockClientResponse(200, json.dumps({"otp": "987654", "validTill": 1728000}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp) as mock_req:
        res = await sample_client.generate_lock_otp("lock-123")
        assert res["otp"] == "987654"
        assert mock_req.call_args[0][0] == "POST"
        assert "/roi-manager/api/v1/sp/" in mock_req.call_args[0][1]
        assert "/device/lock-123/lock/pin/otp" in mock_req.call_args[0][1]

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_plug_energy_history(sample_client):
    """Verify get_plug_energy_history routes period parameters to matching paths."""
    mock_resp = MockClientResponse(200, json.dumps({"data": [{"kwh": 1.5}]}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp) as mock_req:
        res = await sample_client.get_plug_energy_history("plug-123", period="day")
        assert res == {"data": [{"kwh": 1.5}]}
        assert "energyMeasurementDayEvents" in mock_req.call_args[0][1]

        await sample_client.get_plug_energy_history("plug-123", period="hour")
        assert "energyMeasurementHourEvents" in mock_req.call_args[0][1]

        await sample_client.get_plug_energy_history("plug-123", period="month")
        assert "energyMeasurementMonthEvents" in mock_req.call_args[0][1]

        await sample_client.get_plug_energy_history("plug-123", period="overall")
        assert "energyMeasurementOverallData" in mock_req.call_args[0][1]

    with pytest.raises(ValueError, match="Unsupported energy history period"):
        await sample_client.get_plug_energy_history("plug-123", period="invalid_period")

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_device_storage_and_purifier_insights(sample_client):
    """Verify device storage and purifier PM2.5 insights endpoints."""
    mock_resp_storage = MockClientResponse(
        200, json.dumps({"status": "mounted", "available": 1000000})
    )
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_storage) as mock_req:
        storage = await sample_client.get_device_storage("unit-1", "cam-1")
        assert storage["status"] == "mounted"
        assert "/control-monitor/api/v1/" in mock_req.call_args[0][1]
        assert "/storage" in mock_req.call_args[0][1]

    mock_resp_pm25 = MockClientResponse(200, json.dumps({"avgPM25": 42}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_pm25) as mock_req:
        insights = await sample_client.get_purifier_pm25_insights("unit-1", "pur-1")
        assert insights["avgPM25"] == 42
        assert "/airpurifier/pm25/dayInsight" in mock_req.call_args[0][1]

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_initiate_p2p_call(sample_client):
    """Verify initiate_p2p_call generates AES keys and dispatches p2pCall payload."""
    mock_resp = MockClientResponse(200, json.dumps({"status": "SUCCESS"}))
    with patch("aiohttp.ClientSession.request", return_value=mock_resp) as mock_req:
        res = await sample_client.initiate_p2p_call(
            unit_uuid="unit-1",
            device_uuid="cam-1",
            local_ip="192.168.1.50",
            local_port=49700,
            quality="high",
        )
        assert res["response"] == {"status": "SUCCESS"}
        assert len(res["aes_key"]) == 16
        assert len(res["aes_iv"]) == 16
        assert len(res["aes_key_hex"]) == 32
        assert len(res["aes_iv_hex"]) == 32
        assert res["local_ip"] == "192.168.1.50"
        assert res["local_port"] == 49700
        assert res["quality"] == "high"

        # Check request url and json payload
        mock_req.assert_called_once()
        method, url = mock_req.call_args[0][:2]
        assert method == "POST"
        assert "/stream-manager/api/v2/sp/" in url
        assert "/unit/unit-1/device/cam-1/p2pCall" in url

        payload = mock_req.call_args[1]["json"]
        assert payload["aesKey"] == res["aes_key_hex"]
        assert payload["aesIV"] == res["aes_iv_hex"]
        assert "192.168.1.50:49700" in payload["offerData"]
        assert payload["protocols"] == "udp"

    await sample_client.close()


@pytest.mark.asyncio
async def test_client_get_ooi_and_lock_events(sample_client):
    """Verify get_ooi_events and get_lock_events call control-monitor endpoints."""
    mock_resp_ooi = MockClientResponse(
        200, json.dumps({"events": [{"id": "ooi-1", "type": "person"}]})
    )
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_ooi) as mock_req:
        res = await sample_client.get_ooi_events(unit_uuid="unit-1", limit=10)
        assert res == [{"id": "ooi-1", "type": "person"}]
        assert "/control-monitor/api/v1/sp/" in mock_req.call_args[0][1]
        assert "/unit/unit-1/ooi-events" in mock_req.call_args[0][1]
        assert mock_req.call_args[1]["params"]["limit"] == 10

    mock_resp_lock = MockClientResponse(
        200, json.dumps([{"id": "le-1", "action": "manual_unlock"}])
    )
    with patch("aiohttp.ClientSession.request", return_value=mock_resp_lock) as mock_req:
        res_lock = await sample_client.get_lock_events(device_uuid="lock-1")
        assert res_lock == [{"id": "le-1", "action": "manual_unlock"}]
        assert "/control-monitor/api/v1/sp/" in mock_req.call_args[0][1]
        assert "/device/lock-1/event" in mock_req.call_args[0][1]
        assert mock_req.call_args[1]["params"] is None

    await sample_client.close()




