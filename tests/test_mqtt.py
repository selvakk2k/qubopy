"""Unit tests for QuboMqttListener and QuboMqttEvent."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.exceptions import QuboAuthError
from qubopy.models import TokenPayload
from qubopy.mqtt import QuboMqttEvent, QuboMqttListener, _redact_payload


def test_redact_payload_masks_sensitive_keys() -> None:
    """Verify recursive redaction of sensitive credentials and crypto keys."""
    sample = {
        "deviceUUID": "dev-123",
        "services": {
            "p2pStreaming": {
                "commands": {
                    "startP2pCall": {
                        "parameters": {
                            "aesKey": "SECRET_KEY_123",
                            "aesIV": "SECRET_IV_456",
                            "offerData": "host: 192.168.0.1",
                            "mediaStreams": "both",
                        }
                    }
                }
            }
        },
        "tokens": {
            "accessToken": "jwt-token-abc",
            "refreshToken": "jwt-refresh-xyz",
            "otp": "123456",
        },
        "items": [
            {"password": "mypassword", "valid": True},
        ],
    }
    redacted = _redact_payload(sample)

    assert redacted["deviceUUID"] == "dev-123"
    params = redacted["services"]["p2pStreaming"]["commands"]["startP2pCall"]["parameters"]
    assert params["aesKey"] == "<REDACTED>"
    assert params["aesIV"] == "<REDACTED>"
    assert params["offerData"] == "<REDACTED>"
    assert params["mediaStreams"] == "both"

    assert redacted["tokens"]["accessToken"] == "<REDACTED>"
    assert redacted["tokens"]["refreshToken"] == "<REDACTED>"
    assert redacted["tokens"]["otp"] == "<REDACTED>"
    assert redacted["items"][0]["password"] == "<REDACTED>"
    assert redacted["items"][0]["valid"] is True


def test_qubo_mqtt_event_defaults() -> None:
    """Test QuboMqttEvent dataclass structure and defaults."""
    ev = QuboMqttEvent(
        topic="/monitor/u1/d1/panTiltControl",
        unit_uuid="u1",
        device_uuid="d1",
        service="panTiltControl",
        event_name="stateChanged",
        parameters={"pos": "0,-181"},
        operation_state=None,
        timestamp=1792155665762,
        src_device_id="MPC_24:14:07:XX:XX:XX",
    )
    assert ev.topic == "/monitor/u1/d1/panTiltControl"
    assert ev.event_name == "stateChanged"
    assert ev.parameters["pos"] == "0,-181"
    assert ev.timestamp == 1792155665762
    assert ev.src_device_id == "MPC_24:14:07:XX:XX:XX"


@pytest.mark.asyncio
async def test_mqtt_listener_initialization_with_auth_and_client() -> None:
    """Test listener initialization with either QuboAuth or QuboClient."""
    auth = QuboAuth()
    listener_auth = QuboMqttListener(auth, unit_uuid="unit-123", client_id="test_client")
    assert listener_auth.unit_uuid == "unit-123"
    assert listener_auth.client_id == "test_client"
    assert listener_auth.is_running is False

    client = QuboClient(auth)
    listener_client = QuboMqttListener(client)
    assert listener_client.client_id.startswith("qubopy_")
    assert listener_client.unit_uuid is None


@pytest.mark.asyncio
async def test_mqtt_listener_start_and_connect() -> None:
    """Test successful start, credential configuration, and broker subscription."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(
        access_token="valid_jwt_token",
        user_uuid="user-uuid-999",
    )
    auth.get_valid_access_token = AsyncMock(return_value="valid_jwt_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-abc", client_id="custom_client_id")

    mock_mqtt_client = MagicMock()
    with patch("paho.mqtt.client.Client", return_value=mock_mqtt_client):
        await listener.start()

        assert listener.is_running is True
        mock_mqtt_client.username_pw_set.assert_called_once_with(
            username="user-uuid-999", password="valid_jwt_token"
        )
        mock_mqtt_client.tls_set_context.assert_called_once()
        mock_mqtt_client.connect.assert_called_once()
        mock_mqtt_client.loop_start.assert_called_once()

        # Simulate on_connect callback
        on_connect_cb = mock_mqtt_client.on_connect
        mock_mqtt_client.subscribe.reset_mock()
        on_connect_cb(mock_mqtt_client, None, {}, 0)
        mock_mqtt_client.subscribe.assert_called_once_with("/monitor/unit-abc/#", qos=0)

        # Stop
        await listener.stop()
        assert listener.is_running is False
        mock_mqtt_client.disconnect.assert_called_once()
        mock_mqtt_client.loop_stop.assert_called_once()


@pytest.mark.asyncio
async def test_mqtt_listener_auto_discovers_unit_uuid() -> None:
    """Verify listener automatically retrieves unit_uuid from QuboClient."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="jwt_token", user_uuid="user-123")
    auth.get_valid_access_token = AsyncMock(return_value="jwt_token")  # type: ignore[method-assign]

    client = QuboClient(auth)
    client.get_units = AsyncMock(return_value=[{"unitUUID": "auto-unit-456", "name": "Home"}])  # type: ignore[method-assign]

    listener = QuboMqttListener(client)
    mock_mqtt_client = MagicMock()
    with patch("paho.mqtt.client.Client", return_value=mock_mqtt_client):
        await listener.start()
        assert listener.unit_uuid == "auto-unit-456"
        await listener.stop()


@pytest.mark.asyncio
async def test_mqtt_listener_missing_unit_uuid_raises() -> None:
    """Verify ValueError is raised when unit_uuid cannot be resolved."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="jwt_token", user_uuid="user-123")
    auth.get_valid_access_token = AsyncMock(return_value="jwt_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth)  # No unit_uuid, no client
    with pytest.raises(ValueError, match="unit_uuid must be explicitly provided"):
        await listener.start()


@pytest.mark.asyncio
async def test_mqtt_listener_missing_user_uuid_raises() -> None:
    """Verify QuboAuthError is raised when user_uuid is missing."""
    auth = QuboAuth()
    auth.get_valid_access_token = AsyncMock(return_value="jwt_token")  # type: ignore[method-assign]
    # user_uuid is None

    listener = QuboMqttListener(auth, unit_uuid="unit-123")
    with pytest.raises(QuboAuthError, match="user_uuid is missing"):
        await listener.start()


@pytest.mark.asyncio
async def test_mqtt_listener_missing_paho_mqtt_raises() -> None:
    """Verify informative ImportError if paho-mqtt is not installed."""
    auth = QuboAuth()
    listener = QuboMqttListener(auth, unit_uuid="unit-123")
    with (
        patch.dict("sys.modules", {"paho.mqtt.client": None}),
        pytest.raises(ImportError, match="pip install 'qubopy\\[mqtt\\]'"),
    ):
        await listener.start()


@pytest.mark.asyncio
async def test_mqtt_listener_message_parsing_and_callbacks() -> None:
    """Verify parsing of incoming JSON telemetry and callback invocation."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="jwt_token", user_uuid="user-123")
    auth.get_valid_access_token = AsyncMock(return_value="jwt_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-46a")
    received_events: list[QuboMqttEvent] = []

    def on_event(ev: QuboMqttEvent) -> None:
        received_events.append(ev)

    unsubscribe = listener.add_event_listener(on_event)

    # Sample hardware packet 1: panTiltControl
    packet_data = {
        "devices": {
            "deviceUUID": "cam-device-01",
            "entityUUID": "ent-01",
            "services": {
                "panTiltControl": {
                    "events": {
                        "stateChanged": {
                            "horizontalVerticalPostion": "0,-181",
                            "stateChangeEventDefaultPriority": "medium",
                        }
                    },
                    "instanceId": "0",
                }
            },
            "srcDeviceId": "MPC_24:14:07:77:85:EB",
            "timestamp": 1792155665762,
            "unitUUID": "unit-46a",
        }
    }

    mock_msg = MagicMock()
    mock_msg.topic = "/monitor/unit-46a/cam-device-01/panTiltControl"
    mock_msg.payload = json.dumps(packet_data).encode("utf-8")

    # Ingest message
    listener._handle_raw_message(mock_msg.topic, mock_msg.payload)

    # Allow event loop microtasks to run
    await asyncio.sleep(0.05)

    assert len(received_events) == 1
    ev = received_events[0]
    assert ev.device_uuid == "cam-device-01"
    assert ev.service == "panTiltControl"
    assert ev.event_name == "stateChanged"
    assert ev.parameters["horizontalVerticalPostion"] == "0,-181"
    assert ev.src_device_id == "MPC_24:14:07:77:85:EB"

    # Test unsubscribe
    unsubscribe()
    listener._handle_raw_message(mock_msg.topic, mock_msg.payload)
    await asyncio.sleep(0.05)
    assert len(received_events) == 1  # No new event received


@pytest.mark.asyncio
async def test_mqtt_listener_filters_and_async_callback() -> None:
    """Verify device and service filtering with async callback coroutine."""
    auth = QuboAuth()
    listener = QuboMqttListener(auth, unit_uuid="unit-1")

    filtered_events: list[QuboMqttEvent] = []

    async def async_cb(ev: QuboMqttEvent) -> None:
        await asyncio.sleep(0.01)
        filtered_events.append(ev)

    listener.add_event_listener(async_cb, device_uuid="target-dev", service="lockControl")

    # Message matching device and service
    matching_payload = {
        "devices": {
            "deviceUUID": "target-dev",
            "services": {
                "lockControl": {
                    "events": {
                        "stateChanged": {
                            "lockState": "unlocked",
                        }
                    }
                }
            },
        }
    }
    listener._handle_raw_message(
        "/monitor/unit-1/target-dev/lockControl",
        json.dumps(matching_payload).encode("utf-8"),
    )

    # Message with different device
    diff_dev_payload = {
        "devices": {
            "deviceUUID": "other-dev",
            "services": {
                "lockControl": {
                    "events": {"stateChanged": {"lockState": "locked"}}
                }
            },
        }
    }
    listener._handle_raw_message(
        "/monitor/unit-1/other-dev/lockControl",
        json.dumps(diff_dev_payload).encode("utf-8"),
    )

    await asyncio.sleep(0.05)
    assert len(filtered_events) == 1
    assert filtered_events[0].device_uuid == "target-dev"
    assert filtered_events[0].parameters["lockState"] == "unlocked"


@pytest.mark.asyncio
async def test_mqtt_listener_heartbeat_packet() -> None:
    """Verify parsing of device / mobile heartbeat packet."""
    auth = QuboAuth()
    listener = QuboMqttListener(auth, unit_uuid="unit-1")

    events: list[QuboMqttEvent] = []
    listener.add_event_listener(lambda ev: events.append(ev))

    heartbeat_payload = {
        "devices": {
            "deviceUUID": "mob-01",
            "operationState": "online",
            "timestamp": 1792155641265,
        }
    }
    listener._handle_raw_message(
        "/monitor/unit-1/mob-01/heartbeat",
        json.dumps(heartbeat_payload).encode("utf-8"),
    )
    await asyncio.sleep(0.05)

    assert len(events) == 1
    assert events[0].service == "heartbeat"
    assert events[0].operation_state == "online"
    assert events[0].timestamp == 1792155641265


@pytest.mark.asyncio
async def test_mqtt_listener_seed_state() -> None:
    """Verify state seeding delegates to QuboClient.get_all_devices."""
    auth = QuboAuth()
    client = QuboClient(auth)
    mock_dev = MagicMock()
    client.get_all_devices = AsyncMock(return_value=[mock_dev])  # type: ignore[method-assign]

    listener = QuboMqttListener(client)
    seeded = await listener.seed_state()
    assert seeded == [mock_dev]
    client.get_all_devices.assert_called_once()

    # Seed without client raises RuntimeError
    auth_only_listener = QuboMqttListener(auth)
    with pytest.raises(RuntimeError, match="State seeding requires a QuboClient instance"):
        await auth_only_listener.seed_state()


@pytest.mark.asyncio
async def test_mqtt_listener_context_manager() -> None:
    """Verify async context manager calls start() and stop()."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-1")

    mock_client = MagicMock()
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        async with listener as active:
            assert active.is_running is True
        assert listener.is_running is False
