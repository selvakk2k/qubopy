"""Tests for typed device abstractions."""

import importlib
import pkgutil
from unittest.mock import AsyncMock

import pytest

import qubopy
from qubopy.devices import (
    QuboAirPurifier,
    QuboCamera,
    QuboDashcam,
    QuboLight,
    QuboLock,
    QuboPlug,
    QuboSensor,
    create_device,
    is_gateway_device,
)
from qubopy.devices.base import _as_bool, _first_not_none
from qubopy.exceptions import QuboCommandError
from qubopy.models import DeviceModelInfo, DeviceShadow, RtspStreamInfo


def test_plug_telemetry_and_state(sample_client, mock_plug_info):
    """Test QuboPlug properties with varied telemetry."""
    shadow = DeviceShadow(
        device_uuid=mock_plug_info.uuid,
        reported={
            "state": "ON",
            "power": 1820.4,
            "voltage": 230.1,
            "current": 7.91,
            "energy": 14.85,
        },
    )
    plug = QuboPlug(mock_plug_info, sample_client, shadow)

    assert plug.is_on is True
    assert plug.power_watts == 1820.4
    assert plug.voltage == 230.1
    assert plug.current == 7.91
    assert plug.energy_kwh == 14.85


def test_purifier_telemetry(sample_client):
    """Test QuboAirPurifier fan speeds, PM2.5 and modes."""
    info = DeviceModelInfo(
        uuid="purifier-1",
        deviceId="purifier-1",
        name="Living Room Purifier",
        model="HPH02",
        type="AirPurifier",
    )
    shadow = DeviceShadow(
        device_uuid="purifier-1",
        reported={
            "power": True,
            "speed": 2,
            "mode": "auto",
            "pm2_5": 38,
            "filter_life": 82,
            "child_lock": False,
        },
    )
    purifier = QuboAirPurifier(info, sample_client, shadow)

    assert purifier.is_on is True
    assert purifier.fan_speed == 2
    assert purifier.mode == "auto"
    assert purifier.pm25 == 38
    assert purifier.filter_life_percent == 82
    assert purifier.is_child_lock_on is False


def test_light_color_and_brightness(sample_client):
    """Test QuboLight RGB and dimming controls."""
    info = DeviceModelInfo(
        uuid="light-1",
        deviceId="light-1",
        name="Study Desk Bulb",
        model="HLB01",
        type="SmartBulb",
    )
    shadow = DeviceShadow(
        device_uuid="light-1",
        reported={
            "state": "ON",
            "brightness": 75,
            "rgb": [255, 128, 0],
            "color_temp": 4000,
        },
    )
    light = QuboLight(info, sample_client, shadow)

    assert light.is_on is True
    assert light.brightness == 75
    assert light.rgb_color == (255, 128, 0)
    assert light.color_temp == 4000


def test_camera_and_doorbell(sample_client):
    """Test QuboCamera privacy mask and sirens."""
    info = DeviceModelInfo(
        uuid="cam-1",
        deviceId="cam-1",
        name="Balcony Camera",
        model="HCP01",
        type="Camera",
    )
    shadow = DeviceShadow(
        device_uuid="cam-1",
        reported={"privacy_mode": True, "siren": False, "motion": True},
    )
    cam = QuboCamera(info, sample_client, shadow)

    assert cam.is_privacy_mode_on is True
    assert cam.is_siren_on is False
    assert cam.is_motion_detected is True


def test_sensors(sample_client):
    """Test QuboSensor security alarms and climate readings."""
    info = DeviceModelInfo(
        uuid="sensor-1",
        deviceId="sensor-1",
        name="Kitchen Gas Sensor",
        model="HGS01",
        type="GasSensor",
    )
    shadow = DeviceShadow(
        device_uuid="sensor-1",
        reported={"gas_alarm": True, "battery": 92},
    )
    sensor = QuboSensor(info, sample_client, shadow)

    assert sensor.is_gas_alarm is True
    assert sensor.battery_percent == 92


@pytest.mark.asyncio
async def test_lock_gateway_accessibility_and_unlock(sample_client):
    """Test QuboLock gateway detection and unlock validation."""
    from qubopy.devices import QuboLock
    from qubopy.exceptions import QuboCommandError

    # 1. Lock with paired gateway
    info_gw = DeviceModelInfo(
        uuid="lock-01",
        deviceId="lock-01",
        name="Front Door Lock",
        model="HLM01",
        type="SmartDoorLock",
        extraData={"gatewayUUID": "cam-gw-01"},
    )
    lock_gw = QuboLock(info_gw, sample_client)
    assert lock_gw.gateway_id == "cam-gw-01"
    assert lock_gw.is_gateway_accessible is True

    # Mock send command
    sample_client.unlock_lock_via_gateway = AsyncMock(return_value={"status": "SUCCESS"})
    res = await lock_gw.unlock()
    assert res["status"] == "SUCCESS"

    # 2. Lock without paired gateway (standalone BLE only)
    info_ble = DeviceModelInfo(
        uuid="lock-02",
        deviceId="lock-02",
        name="Bedroom Lock",
        model="HLM02",
        type="SmartDoorLock",
    )
    lock_ble = QuboLock(info_ble, sample_client)
    assert lock_ble.gateway_id is None
    assert lock_ble.is_gateway_accessible is False

    with pytest.raises(QuboCommandError) as exc_info:
        await lock_ble.unlock()
    assert "standalone Bluetooth mode" in str(exc_info.value)


def test_dashcam_device(sample_client):
    """Test QuboDashcam instantiation, properties, and telemetry."""
    info = DeviceModelInfo.model_validate({
        "deviceUUID": "dash-01",
        "deviceName": "XUV 300 Dashcam",
        "aModelNo": "HCA08B",
        "deviceType": "2kDashCam",
        "extraData": {"serialNumber": "IN2507JJIM09358"},
    })
    assert info.model == "HCA08B"
    assert info.uuid == "dash-01"
    assert info.name == "XUV 300 Dashcam"

    shadow = DeviceShadow(
        device_uuid="dash-01",
        reported={
            "recording": True,
            "sdcard_status": "NORMAL",
            "parking_mode": True,
            "dashcam_wifi_name": "XUV 300_AP",
            "dashcam_wifi_password": "pass1234",
            "overspeed_limit": "120",
            "speed_unit": "km",
            "audio_recording": True,
        },
    )
    dev = create_device(info, sample_client, shadow)
    assert isinstance(dev, QuboDashcam)
    assert dev.serial_number == "IN2507JJIM09358"
    assert dev.is_recording is True
    assert dev.sd_card_status == "NORMAL"
    assert dev.is_parking_monitoring_on is True
    assert dev.wifi_ap_ssid == "XUV 300_AP"
    assert dev.wifi_ap_password == "pass1234"
    assert dev.overspeed_limit == 120
    assert dev.speed_unit == "km"
    assert dev.is_audio_recording_on is True


async def test_camera_controls_and_streaming(sample_client):
    """Test QuboCamera controls, streaming, PTZ, and diagnostics."""
    info = DeviceModelInfo(
        uuid="cam-01",
        deviceId="cam-01",
        name="Cam 360",
        model="HCP02A",
        type="ptzeCamera",
        unitUUID="u-01",
        entityUUID="e-01",
    )
    shadow = DeviceShadow(
        device_uuid="cam-01",
        reported={
            "camera_enabled": True,
            "night_mode": "auto",
            "ptz_position": "0,-181",
            "motion_tracking": True,
            "ip_address": "192.168.0.101",
            "signal_strength": "-45",
            "wifi_ssid": "HomeWiFi",
            "sd_card_status": "statusOk",
            "sd_available_storage": "2130.38",
            "sd_total_storage": "15174.7",
        },
    )
    cam = QuboCamera(info, sample_client, shadow)
    assert cam.is_privacy_mode_on is False
    assert cam.night_mode == "auto"
    assert cam.pan_tilt_position == "0,-181"
    assert cam.is_motion_tracking_on is True
    assert cam.lan_ip_address == "192.168.0.101"
    assert cam.wifi_rssi == -45
    assert cam.wifi_ssid == "HomeWiFi"
    assert cam.sd_card_status == "statusOk"
    assert cam.sd_storage_free_mb == 2130.38
    assert cam.sd_storage_total_mb == 15174.7

    # Mock client streaming and shadow attribute update
    sample_client.get_live_stream_url = AsyncMock(
        return_value="rtsps://wowza.platform.quboworld.com:443/live/cam-01"
    )
    sample_client.update_shadow_attribute = AsyncMock(return_value={"status": "SUCCESS"})

    stream_url = await cam.start_stream()
    assert "rtsps://wowza.platform.quboworld.com" in stream_url

    await cam.set_privacy_mode(True)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-01",
        entity_uuid="e-01",
        device_uuid="cam-01",
        attributes={"cameraFunction": {"attributes": {"state": "disable"}}},
    )

    await cam.set_night_mode("true")
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-01",
        entity_uuid="e-01",
        device_uuid="cam-01",
        attributes={"nightModeControl": {"attributes": {"nightMode": "true"}}},
    )

    await cam.set_motion_tracking(False)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-01",
        entity_uuid="e-01",
        device_uuid="cam-01",
        attributes={"motionTracking": {"attributes": {"enabled": "false"}}},
    )

    await cam.pan_tilt(10, -50)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-01",
        entity_uuid="e-01",
        device_uuid="cam-01",
        attributes={"panTiltControl": {"attributes": {"horizontalVerticalPostion": "10,-50"}}},
    )

    # Test P2P video call negotiation
    sample_client.initiate_p2p_call = AsyncMock(
        return_value={"session_id": "test-session", "aes_key_hex": "AA" * 16}
    )
    p2p_res = await cam.initiate_p2p_call(
        local_ip="192.168.0.50",
        local_port=49700,
        quality="high",
    )
    assert p2p_res["session_id"] == "test-session"
    sample_client.initiate_p2p_call.assert_called_with(
        unit_uuid="u-01",
        device_uuid="cam-01",
        local_ip="192.168.0.50",
        local_port=49700,
        quality="high",
    )

    cam_no_client = QuboCamera(info, None, shadow)
    with pytest.raises(QuboCommandError):
        await cam_no_client.initiate_p2p_call(local_ip="192.168.0.50")


async def test_dashcam_controls(sample_client):
    """Test QuboDashcam control methods."""
    info = DeviceModelInfo(
        uuid="dash-01",
        deviceId="dash-01",
        name="XUV 300 Dashcam",
        model="HCA08B",
        type="2kDashCam",
        unitUUID="u-dash",
        entityUUID="e-dash",
    )
    dash = QuboDashcam(info, sample_client)
    sample_client.update_shadow_attribute = AsyncMock(return_value={"status": "SUCCESS"})

    await dash.set_parking_monitoring(True)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-dash",
        entity_uuid="e-dash",
        device_uuid="dash-01",
        attributes={"parkingConfig": {"attributes": {"state": "enable"}}},
    )

    await dash.set_overspeed_limit(100)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-dash",
        entity_uuid="e-dash",
        device_uuid="dash-01",
        attributes={"dashcamGpsConfig": {"attributes": {"overSpeedLimits": "100"}}},
    )

    await dash.set_audio_recording(False)
    sample_client.update_shadow_attribute.assert_called_with(
        unit_uuid="u-dash",
        entity_uuid="e-dash",
        device_uuid="dash-01",
        attributes={"dashcamRecordingConfig": {"attributes": {"audioTrack": "disable"}}},
    )


def test_helpers_first_not_none_and_as_bool():
    """Verify helpers preserve zero, false, and properly coerce strings/ints."""
    data = {"zero_val": 0, "false_val": False, "none_val": None, "empty_str": ""}
    assert _first_not_none(data, "zero_val") == 0
    assert _first_not_none(data, "false_val") is False
    assert _first_not_none(data, "none_val", "zero_val") == 0
    assert _first_not_none(data, "missing", "zero_val") == 0
    assert _first_not_none(data, "missing1", "missing2") is None

    # _as_bool coercion tests
    assert _as_bool("false") is False
    assert _as_bool("False") is False
    assert _as_bool("0") is False
    assert _as_bool("disable") is False
    assert _as_bool("disabled") is False
    assert _as_bool("off") is False
    assert _as_bool(False) is False
    assert _as_bool(0) is False

    assert _as_bool("true") is True
    assert _as_bool("True") is True
    assert _as_bool("1") is True
    assert _as_bool("enable") is True
    assert _as_bool("enabled") is True
    assert _as_bool("on") is True
    assert _as_bool(True) is True
    assert _as_bool(1) is True

    assert _as_bool(None) is None


def test_plug_zero_power_telemetry(sample_client, mock_plug_info):
    """Bug 3: Zero power and zero energy should not be coerced to None."""
    shadow = DeviceShadow(
        device_uuid=mock_plug_info.uuid,
        reported={
            "state": "ON",
            "power": 0,
            "voltage": 220.0,
            "current": 0.0,
            "energy": 0,
        },
    )
    plug = QuboPlug(mock_plug_info, sample_client, shadow)
    assert plug.power_watts == 0.0
    assert plug.current == 0.0
    assert plug.energy_kwh == 0.0


def test_lock_is_locked_state(sample_client):
    """Bug 2: isOpen: False means door is shut/locked, should return True, not None."""
    info = DeviceModelInfo(
        uuid="lock-01",
        deviceId="lock-01",
        name="Front Door Lock",
        model="HLM01",
        type="SmartDoorLock",
    )
    # When door is not open (isOpen: False), is_locked is True
    shadow_closed = DeviceShadow(
        device_uuid="lock-01",
        reported={"isOpen": False, "battery": 0},
    )
    lock_closed = QuboLock(info, sample_client, shadow_closed)
    assert lock_closed.is_locked is True
    assert lock_closed.battery_percent == 0

    # When door is open (isOpen: True), is_locked is False
    shadow_open = DeviceShadow(
        device_uuid="lock-01",
        reported={"isOpen": True, "battery": 75},
    )
    lock_open = QuboLock(info, sample_client, shadow_open)
    assert lock_open.is_locked is False
    assert lock_open.battery_percent == 75

    # When isOpen is absent from shadow, is_locked is None
    shadow_empty = DeviceShadow(device_uuid="lock-01", reported={})
    lock_empty = QuboLock(info, sample_client, shadow_empty)
    assert lock_empty.is_locked is None


def test_purifier_zero_pm25_telemetry(sample_client):
    """Bug 3: Zero PM2.5 reading should not be coerced to None."""
    info = DeviceModelInfo(
        uuid="purifier-1",
        deviceId="purifier-1",
        name="Living Room Purifier",
        model="HPH02",
        type="AirPurifier",
    )
    shadow = DeviceShadow(
        device_uuid="purifier-1",
        reported={"pm2_5": 0, "filter_life": 0},
    )
    purifier = QuboAirPurifier(info, sample_client, shadow)
    assert purifier.pm25 == 0
    assert purifier.filter_life_percent == 0


def test_dashcam_audio_recording_safety(sample_client):
    """Bug 4: Absent audio recording in shadow should return None (not True)."""
    info = DeviceModelInfo(
        uuid="dash-01",
        deviceId="dash-01",
        name="Dashcam",
        model="HCA08B",
        type="2kDashCam",
    )
    shadow_empty = DeviceShadow(device_uuid="dash-01", reported={})
    dash = QuboDashcam(info, sample_client, shadow_empty)
    assert dash.is_audio_recording_on is None


def test_create_device_null_extra_data(sample_client):
    """Bug 5: extraData: null in JSON must not cause TypeError."""
    raw = {
        "uuid": "plug-null",
        "deviceId": "plug-null",
        "name": "Smart Plug",
        "deviceType": "SmartPlug",
        "deviceModel": "HSP01",
        "extraData": None,
    }
    dev = create_device(DeviceModelInfo.model_validate(raw), sample_client)
    assert isinstance(dev, QuboPlug)
    assert dev.name == "Smart Plug"


def test_create_device_floodlight_distinction(sample_client):
    """Bug 6: Floodlight Camera model HCP08 should create QuboCamera, not QuboLight."""
    raw = {
        "uuid": "cam-fl-01",
        "deviceId": "cam-fl-01",
        "name": "Floodlight Cam",
        "deviceModel": "HCP08",
        "deviceType": "FloodlightCamera",
    }
    dev = create_device(DeviceModelInfo.model_validate(raw), sample_client)
    assert isinstance(dev, QuboCamera)
    assert not isinstance(dev, QuboLight)


def test_as_bool_coercion(caplog):
    """Test _as_bool strictly coerces 0/1, strings, logs debug on unrecognized values."""
    assert _as_bool(True) is True
    assert _as_bool(False) is False
    assert _as_bool(None) is None

    # Exact numbers 0 and 1
    assert _as_bool(1) is True
    assert _as_bool(1.0) is True
    assert _as_bool(0) is False
    assert _as_bool(0.0) is False

    # Numbers outside 0 and 1 must return None
    assert _as_bool(2) is None
    assert _as_bool(-1) is None
    assert _as_bool(100) is None
    assert _as_bool(0.5) is None

    # Boolean strings
    assert _as_bool("true") is True
    assert _as_bool("1") is True
    assert _as_bool("yes") is True
    assert _as_bool("on") is True
    assert _as_bool("enable") is True
    assert _as_bool("false") is False
    assert _as_bool("0") is False
    assert _as_bool("no") is False
    assert _as_bool("off") is False
    assert _as_bool("disable") is False

    # Strings "open" and "close" removed from general _as_bool (handled by locks)
    import logging
    with caplog.at_level(logging.DEBUG):
        assert _as_bool("open") is None
        assert _as_bool("close") is None
        assert _as_bool("random_string") is None
        assert "Unrecognized boolean string value: 'open'" in caplog.text


def test_lock_is_locked_string_states(sample_client):
    """Test QuboLock handles string states like 'open', 'opened', 'close', 'closed'."""
    info = DeviceModelInfo(
        uuid="lock-02",
        deviceId="lock-02",
        name="Front Door Lock",
        model="HLM01",
        type="SmartDoorLock",
    )

    shadow_open_str = DeviceShadow(
        device_uuid="lock-02",
        reported={"isOpen": "open"},
    )
    lock_open = QuboLock(info, sample_client, shadow_open_str)
    assert lock_open.is_locked is False

    shadow_opened_str = DeviceShadow(
        device_uuid="lock-02",
        reported={"isOpen": "opened"},
    )
    lock_opened = QuboLock(info, sample_client, shadow_opened_str)
    assert lock_opened.is_locked is False

    shadow_close_str = DeviceShadow(
        device_uuid="lock-02",
        reported={"isOpen": "close"},
    )
    lock_close = QuboLock(info, sample_client, shadow_close_str)
    assert lock_close.is_locked is True

    shadow_closed_str = DeviceShadow(
        device_uuid="lock-02",
        reported={"isOpen": "closed"},
    )
    lock_closed = QuboLock(info, sample_client, shadow_closed_str)
    assert lock_closed.is_locked is True


def test_is_gateway_device_matching():
    """Verify gateway identification strictly matches cameras/doorbells and rejects dashcams."""
    # Dashcam models or types must be rejected
    assert not is_gateway_device({"deviceModel": "HCA01", "deviceType": "DashCam"})
    assert not is_gateway_device({"deviceModel": "HCA08B", "deviceType": "2kDashCam"})

    # Cameras and doorbells must match
    assert is_gateway_device({"deviceModel": "HCP01", "deviceType": "SmartCamera"})
    assert is_gateway_device({"deviceModel": "HCD01", "deviceType": "Doorbell"})
    assert is_gateway_device({"deviceModel": "HCB01", "deviceType": "OutdoorCamera"})
    assert is_gateway_device(DeviceModelInfo(uuid="gw1", model="HDB01", deviceType="Doorbell"))

    # Non-gateway peripherals must be rejected
    assert not is_gateway_device({"deviceModel": "HSP01", "deviceType": "SmartPlug"})
    assert not is_gateway_device({"deviceModel": "HPH02", "deviceType": "AirPurifier"})
    assert not is_gateway_device({"deviceModel": "HLB01", "deviceType": "SmartBulb"})
    assert not is_gateway_device({"deviceModel": "HLM01", "deviceType": "SmartDoorLock"})


@pytest.mark.asyncio
async def test_lock_v2_lock_state_and_battery_attributes(sample_client):
    """Verify QuboLock correctly resolves lockControl and batteryStatus attributes."""
    info = DeviceModelInfo(uuid="lock-01", model="HLM01", deviceType="SmartDoorLock")

    # 1. Nested dictionary format from v2 shadow / mobile app
    shadow_nested = DeviceShadow(
        device_uuid="lock-01",
        reported={
            "lockControl": {"lockState": "unlocked"},
            "batteryStatus": {"level": "85"},
        },
    )
    lock1 = QuboLock(info, sample_client, shadow_nested)
    assert lock1.is_locked is False
    assert lock1.battery_percent == 85

    # 2. Locked state with percentage symbol in level
    shadow_locked = DeviceShadow(
        device_uuid="lock-01",
        reported={
            "lockControl": {"lockState": "locked"},
            "batteryStatus": {"level": "90%"},
        },
    )
    lock2 = QuboLock(info, sample_client, shadow_locked)
    assert lock2.is_locked is True
    assert lock2.battery_percent == 90

    # 3. Flattened service attributes
    shadow_flat = DeviceShadow(
        device_uuid="lock-01",
        reported={
            "lockControl_lockState": "unlocked",
            "batteryStatus_level": 75,
        },
    )
    lock3 = QuboLock(info, sample_client, shadow_flat)
    assert lock3.is_locked is False
    assert lock3.battery_percent == 75

    await sample_client.close()


@pytest.mark.asyncio
async def test_lock_live_fetch_and_otp_methods(sample_client):
    """Verify fetch_live_lock_state, fetch_live_battery, and generate_guest_otp on QuboLock."""
    info = DeviceModelInfo(uuid="lock-live", model="HLM01", deviceType="SmartDoorLock")
    lock = QuboLock(info, sample_client)

    sample_client.get_device_shadow_v2 = AsyncMock(
        side_effect=[
            {"attributeValue": "unlocked", "timestamp": 1700000000},
            {"attributeValue": "88%"},
        ]
    )
    sample_client.generate_lock_otp = AsyncMock(return_value={"otp": "123456"})

    st = await lock.fetch_live_lock_state()
    assert st == "unlocked"
    assert lock.is_locked is False
    assert lock.last_lock_state_timestamp == 1700000000000
    sample_client.get_device_shadow_v2.assert_called_with(
        "lock-live", service_name="lockControl", attribute_name="lockState"
    )

    bat = await lock.fetch_live_battery()
    assert bat == 88
    assert lock.battery_percent == 88

    otp_resp = await lock.generate_guest_otp()
    assert otp_resp == {"otp": "123456"}
    sample_client.generate_lock_otp.assert_called_with("lock-live")

    await sample_client.close()


@pytest.mark.asyncio
async def test_lock_state_parsing_exact_and_unknown(sample_client):
    """Verify is_locked handles exact states, in-transit states, and unknown values."""
    info = DeviceModelInfo(uuid="lock-states", model="HLM01", deviceType="SmartDoorLock")

    for raw_state, expected in [
        ("locked", True),
        ("lock", True),
        ("LOCKED", True),
        ("unlocked", False),
        ("unlock", False),
        ("UNLOCKED", False),
        ("unlocking", None),
        ("locking", None),
        ("jammed", None),
        ("unknown", None),
        ("", None),
    ]:
        shadow = DeviceShadow(
            device_uuid="lock-states",
            reported={"lockState": raw_state},
        )
        lock = QuboLock(info, sample_client, shadow)
        assert lock.is_locked is expected, f"Failed for state '{raw_state}'"


@pytest.mark.asyncio
async def test_device_extended_api_delegates(sample_client):
    """Verify plug, purifier, and camera delegate to client methods."""
    plug_info = DeviceModelInfo(uuid="plug-01", model="HSP01", deviceType="SmartPlug")
    plug = QuboPlug(plug_info, sample_client)
    sample_client.get_plug_energy_history = AsyncMock(return_value={"totalKwh": 10.5})
    assert await plug.get_energy_history(period="month") == {"totalKwh": 10.5}
    sample_client.get_plug_energy_history.assert_called_with("plug-01", period="month")

    pur_info = DeviceModelInfo(
        uuid="pur-01", model="HPH01", deviceType="AirPurifier", unitUUID="unit-pur"
    )
    pur = QuboAirPurifier(pur_info, sample_client)
    sample_client.get_purifier_pm25_insights = AsyncMock(return_value={"avgPM25": 30})
    assert await pur.get_pm25_insights() == {"avgPM25": 30}
    sample_client.get_purifier_pm25_insights.assert_called_with("unit-pur", "pur-01")

    cam_info = DeviceModelInfo(
        uuid="cam-01", model="HCP01", deviceType="SmartCamera", unitUUID="unit-cam"
    )
    cam = QuboCamera(cam_info, sample_client)
    sample_client.get_device_events = AsyncMock(return_value=[{"id": "ev-1"}])
    sample_client.get_device_storage = AsyncMock(return_value={"status": "ok"})

    assert await cam.get_events(version="v3") == [{"id": "ev-1"}]
    sample_client.get_device_events.assert_called_with(
        "unit-cam", "cam-01", version="v3", start_time=None, end_time=None, limit=50
    )

    assert await cam.get_storage_info() == {"status": "ok"}
    sample_client.get_device_storage.assert_called_with("unit-cam", "cam-01")

    await sample_client.close()


@pytest.mark.asyncio
async def test_light_properties_and_controls(sample_client):
    """Test QuboLight state properties, setters, and Kelvin aliases."""
    info = DeviceModelInfo(
        uuid="light-01",
        deviceId="light-01",
        name="Living Room Bulb",
        model="HLB01",
        type="SmartBulb",
        unitUUID="u-light",
        entityUUID="e-light",
    )
    shadow = DeviceShadow(
        device_uuid="light-01",
        reported={
            "state": "ON",
            "brightness": 85,
            "color_temp": 3200,
            "rgb": [255, 140, 0],
        },
    )
    light = QuboLight(info, sample_client, shadow)
    assert light.is_on is True
    assert light.brightness == 85
    assert light.color_temp == 3200
    assert light.color_temp_kelvin == 3200
    assert light.rgb_color == (255, 140, 0)

    sample_client.send_command = AsyncMock(return_value={"status": "SUCCESS"})

    await light.turn_on(brightness=90, rgb=(0, 255, 0), color_temp=4000)
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={
            "state": "ON",
            "switch": True,
            "brightness": 90,
            "rgb": [0, 255, 0],
            "color_temp": 4000,
        },
    )

    await light.turn_off()
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={"state": "OFF", "switch": False},
    )

    await light.set_brightness(50)
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={"brightness": 50},
    )

    await light.set_rgb(10, 20, 30)
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={"rgb": [10, 20, 30]},
    )

    await light.set_color_temp(2700)
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={"color_temp": 2700},
    )

    await light.set_color_temp_kelvin(3000)
    sample_client.send_command.assert_called_with(
        unit_uuid="u-light",
        entity_uuid="e-light",
        device_uuid="light-01",
        command={"color_temp": 3000},
    )

    await sample_client.close()


def test_rtsp_stream_info_alias():
    """Verify RtspStreamInfo supports both stream_url and rtsp_url."""
    info1 = RtspStreamInfo(device_uuid="cam-1", stream_url="rtsps://host/live", is_supported=True)
    assert info1.stream_url == "rtsps://host/live"
    assert info1.rtsp_url == "rtsps://host/live"

    info2 = RtspStreamInfo.model_validate({"device_uuid": "cam-2", "rtsp_url": "rtsps://host/live2"})
    assert info2.stream_url == "rtsps://host/live2"
    assert info2.rtsp_url == "rtsps://host/live2"


@pytest.mark.asyncio
async def test_lock_state_in_transit_and_battery_edge_cases(sample_client):
    """Verify in-transit states return None and battery handles 0, decimals, and clamping."""
    info = DeviceModelInfo(uuid="lock-transit", model="HLM01", deviceType="SmartDoorLock")
    lock = QuboLock(info, sample_client)

    # In-transit states must return None, not True or False
    lock.shadow.reported["lockState"] = "unlocking"
    assert lock.is_locked is None

    lock.shadow.reported["lockState"] = "locking"
    assert lock.is_locked is None

    lock.shadow.reported["lockState"] = "locked"
    assert lock.is_locked is True

    # Battery reading of 0 must be preserved, not dropped
    sample_client.get_device_shadow_v2 = AsyncMock(
        side_effect=[
            {"attributeValue": 0},
            {"attributeValue": "87.5%"},
            {"attributeValue": 150},
            {"attributeValue": -10},
        ]
    )
    bat0 = await lock.fetch_live_battery()
    assert bat0 == 0
    assert lock.battery_percent == 0

    bat_dec = await lock.fetch_live_battery()
    assert bat_dec == 88
    assert lock.battery_percent == 88

    bat_over = await lock.fetch_live_battery()
    assert bat_over == 100

    bat_under = await lock.fetch_live_battery()
    assert bat_under == 0

    await sample_client.close()


def test_all_modules_have_docstrings():
    """Verify that every module under qubopy defines a non-empty module docstring."""
    assert qubopy.__doc__, "qubopy package root is missing a docstring"
    for info in pkgutil.walk_packages(qubopy.__path__, prefix="qubopy."):
        mod = importlib.import_module(info.name)
        assert mod.__doc__, f"Module {info.name} is missing a docstring"






