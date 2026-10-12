"""Tests for typed device abstractions."""

from unittest.mock import AsyncMock
import pytest

from qubopy.devices import (
    QuboAirPurifier,
    QuboCamera,
    QuboDashcam,
    QuboLight,
    QuboLock,
    QuboPlug,
    QuboSensor,
    create_device,
)
from qubopy.devices.base import _as_bool, _first_not_none
from qubopy.models import DeviceModelInfo, DeviceShadow


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




