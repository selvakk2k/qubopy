"""Unit tests for QuboMqttListener and QuboMqttEvent."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.exceptions import QuboAuthError, QuboConnectionError
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
def _create_mock_mqtt_client(on_connect_rc: int = 0) -> MagicMock:
    """Create a mock Paho client that triggers on_connect during connect."""
    mock_client = MagicMock()

    def _mock_connect(*args: Any, **kwargs: Any) -> int:
        if mock_client.on_connect:
            mock_client.on_connect(mock_client, None, {}, on_connect_rc)
        return 0

    mock_client.connect.side_effect = _mock_connect
    return mock_client


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

    mock_mqtt_client = _create_mock_mqtt_client(on_connect_rc=0)
    with patch("paho.mqtt.client.Client", return_value=mock_mqtt_client):
        await listener.start()

        assert listener.is_running is True
        mock_mqtt_client.username_pw_set.assert_called_once_with(
            username="user-uuid-999", password="valid_jwt_token"
        )
        mock_mqtt_client.tls_set_context.assert_called_once()
        mock_mqtt_client.connect.assert_called_once()
        mock_mqtt_client.loop_start.assert_called_once()
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
    mock_mqtt_client = _create_mock_mqtt_client(on_connect_rc=0)
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
    with pytest.raises(ValueError, match=r"unit_uuid.*must be explicitly provided"):
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
            "services": {"lockControl": {"events": {"stateChanged": {"lockState": "locked"}}}},
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

    mock_client = _create_mock_mqtt_client(on_connect_rc=0)
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        async with listener as active:
            assert active.is_running is True
        assert listener.is_running is False


@pytest.mark.asyncio
async def test_mqtt_packet_defense_malformed_json_matrix() -> None:
    """Verify listener handles non-dict, scalar, null, and non-conforming JSON payloads safely."""
    auth = QuboAuth()
    listener = QuboMqttListener(auth, unit_uuid="unit-1")

    received_events: list[QuboMqttEvent] = []
    listener.add_event_listener(lambda ev: received_events.append(ev))

    malformed_samples = [
        b"[1, 2, 3]",
        b'"just a string"',
        b"12345",
        b"true",
        b"null",
        b"not json at all {{{",
        b'{"devices": []}',
        b'{"devices": "not_a_dict"}',
        b'{"devices": {"services": []}}',
        b'{"devices": {"services": {"panTiltControl": "not_a_dict"}}}',
        b'{"devices": {"services": {"panTiltControl": {"events": []}}}}',
        b'{"devices": {"services": {"panTiltControl": {"events": {"stateChanged": "bad"}}}}}',
        b'{"devices": {"services": {"panTiltControl": {"events": {"stateChanged": {"pos": 1}}}}}}',
    ]

    for payload in malformed_samples:
        # Must not raise or crash the handler
        listener._handle_raw_message("/monitor/unit-1/dev-1/panTiltControl", payload)

    await asyncio.sleep(0.05)

    # Now verify that subsequent valid packets are still processed normally
    valid_payload = {
        "devices": {
            "deviceUUID": "dev-1",
            "services": {"panTiltControl": {"events": {"stateChanged": {"pos": "10,20"}}}},
        }
    }
    listener._handle_raw_message(
        "/monitor/unit-1/dev-1/panTiltControl",
        json.dumps(valid_payload).encode("utf-8"),
    )
    await asyncio.sleep(0.05)

    assert len(received_events) >= 1
    assert received_events[-1].parameters["pos"] == "10,20"


@pytest.mark.asyncio
async def test_mqtt_start_connection_rejections() -> None:
    """Verify start() handles auth refusal and socket connection refusal."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="token")  # type: ignore[method-assign]

    # rc=5 (not authorized) -> QuboAuthError
    listener_auth_fail = QuboMqttListener(auth, unit_uuid="unit-1")
    mock_auth_fail = _create_mock_mqtt_client(on_connect_rc=5)
    with (
        patch("paho.mqtt.client.Client", return_value=mock_auth_fail),
        pytest.raises(QuboAuthError, match="rejected credentials"),
    ):
        await listener_auth_fail.start(connect_timeout=1.0)
    assert listener_auth_fail.is_running is False

    # rc=1 (unacceptable protocol) -> QuboConnectionError
    listener_conn_fail = QuboMqttListener(auth, unit_uuid="unit-1")
    mock_conn_fail = _create_mock_mqtt_client(on_connect_rc=1)
    with (
        patch("paho.mqtt.client.Client", return_value=mock_conn_fail),
        pytest.raises(QuboConnectionError, match="rejected connection"),
    ):
        await listener_conn_fail.start(connect_timeout=1.0)
    assert listener_conn_fail.is_running is False


@pytest.mark.asyncio
async def test_mqtt_start_connection_timeout() -> None:
    """Verify start() raises QuboConnectionError and resets state if CONNACK is not received."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-1")
    mock_client = MagicMock()  # Never calls on_connect

    with (
        patch("paho.mqtt.client.Client", return_value=mock_client),
        pytest.raises(QuboConnectionError, match="Timed out waiting"),
    ):
        await listener.start(connect_timeout=0.05)

    assert listener.is_running is False


@pytest.mark.asyncio
async def test_mqtt_reconnect_token_renewal_success() -> None:
    """Verify token is renewed on reconnect after unexpected disconnect."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="initial_token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="initial_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-1")
    mock_client = _create_mock_mqtt_client(on_connect_rc=0)

    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()
        assert listener.is_running is True

        # Mock renewed token for reconnect
        auth.get_valid_access_token = AsyncMock(return_value="renewed_token")  # type: ignore[method-assign]

        _real_sleep = asyncio.sleep

        async def _mock_sleep(delay: float) -> None:
            await _real_sleep(0)

        with patch("qubopy.mqtt.asyncio.sleep", side_effect=_mock_sleep):
            on_disconnect = mock_client.on_disconnect
            on_disconnect(mock_client, None, {}, 7)  # rc != 0

            for _ in range(10):
                await _real_sleep(0.01)
                if listener._reconnect_task and listener._reconnect_task.done():
                    break
                if listener._reconnect_task:
                    await listener._reconnect_task
                    break

            mock_client.username_pw_set.assert_called_with(
                username="user-1", password="renewed_token"
            )
            mock_client.reconnect.assert_called_once()

        await listener.stop()


@pytest.mark.asyncio
async def test_mqtt_reconnect_mobile_phone_otp_expired_token() -> None:
    """Verify expired token on mobile phone OTP account halts retries and fires on_auth_failure."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="initial_token", user_uuid="user-phone")
    auth.get_valid_access_token = AsyncMock(return_value="initial_token")  # type: ignore[method-assign]

    auth_failure_called = asyncio.Event()

    async def on_auth_failure() -> None:
        auth_failure_called.set()

    listener = QuboMqttListener(auth, unit_uuid="unit-1", on_auth_failure=on_auth_failure)
    mock_client = _create_mock_mqtt_client(on_connect_rc=0)

    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()

        # Token is expired and has no refresh token (mobile phone OTP account)
        auth.get_valid_access_token = AsyncMock(  # type: ignore[method-assign]
            side_effect=QuboAuthError("Session expired; please log in again")
        )

        _real_sleep = asyncio.sleep

        async def _mock_sleep(delay: float) -> None:
            await _real_sleep(0)

        with patch("qubopy.mqtt.asyncio.sleep", side_effect=_mock_sleep):
            on_disconnect = mock_client.on_disconnect
            on_disconnect(mock_client, None, {}, 7)

            for _ in range(10):
                await _real_sleep(0.01)
                if listener._reconnect_task and listener._reconnect_task.done():
                    break
                if listener._reconnect_task:
                    await listener._reconnect_task
                    break

        assert listener.is_running is False
        assert auth_failure_called.is_set()
        mock_client.reconnect.assert_not_called()
        mock_client.disconnect.assert_called_once()
        mock_client.loop_stop.assert_called_once()

        await listener.stop()


@pytest.mark.asyncio
async def test_mqtt_reconnect_broker_rejected_credentials() -> None:
    """Verify broker credential rejection on reconnect halts listener and invokes
    on_auth_failure.
    """
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="initial_token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="initial_token")  # type: ignore[method-assign]

    auth_failure_called = asyncio.Event()

    async def on_auth_failure() -> None:
        auth_failure_called.set()

    listener = QuboMqttListener(auth, unit_uuid="unit-1", on_auth_failure=on_auth_failure)
    mock_client = _create_mock_mqtt_client(on_connect_rc=0)

    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()
        assert listener.is_running is True

        # Now simulate broker rejecting reconnect with rc=135 (Not authorized)
        on_connect = mock_client.on_connect
        on_connect(mock_client, None, {}, 135)

        # Allow loop tasks to execute
        await asyncio.sleep(0.05)

        assert listener.is_running is False
        assert auth_failure_called.is_set()
        mock_client.disconnect.assert_called()
        mock_client.loop_stop.assert_called()


@pytest.mark.asyncio
async def test_real_paho_mqtt_client_initialization() -> None:
    """Verify real paho.mqtt.client.Client instantiates with reconnect_on_failure=False."""
    import paho.mqtt.client as mqtt

    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="test_token", user_uuid="user-real-paho")
    auth.get_valid_access_token = AsyncMock(return_value="test_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-real", client_id="real_client_id")

    connected_args = []

    def fake_connect(self_c: Any, host: str, port: int, keepalive: int = 60) -> int:
        connected_args.append((host, port, keepalive))
        if self_c.on_connect:
            self_c.on_connect(self_c, None, {}, 0)
        return 0

    with (
        patch.object(mqtt.Client, "connect", fake_connect),
        patch.object(mqtt.Client, "loop_start"),
        patch.object(mqtt.Client, "loop_stop"),
        patch.object(mqtt.Client, "disconnect"),
        patch.object(mqtt.Client, "subscribe"),
    ):
        await listener.start()

        assert listener.is_running is True
        assert listener._mqttc is not None
        assert isinstance(listener._mqttc, mqtt.Client)
        # Verify paho internal auto-reconnect is explicitly disabled
        assert getattr(listener._mqttc, "_reconnect_on_failure", None) is False

        await listener.stop()
        assert listener.is_running is False


@pytest.mark.asyncio
async def test_real_paho_reason_codes_in_callbacks() -> None:
    """Verify handling of real paho.mqtt.reasoncodes.ReasonCode objects in callbacks."""
    import paho.mqtt.client as mqtt
    from paho.mqtt.reasoncodes import ReasonCode

    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="test_token", user_uuid="user-123")
    auth.get_valid_access_token = AsyncMock(return_value="test_token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-test")
    mock_client = MagicMock()

    # Success CONNACK ReasonCode
    rc_success = ReasonCode(mqtt.PacketTypes.CONNACK, "Success")

    def _mock_connect(*args: Any, **kwargs: Any) -> int:
        if mock_client.on_connect:
            mock_client.on_connect(mock_client, None, {}, rc_success)
        return 0

    mock_client.connect.side_effect = _mock_connect

    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()
        assert listener.is_running is True

        # Test real SUBACK ReasonCode Granted QoS 0
        rc_sub_ok = ReasonCode(mqtt.PacketTypes.SUBACK, "Granted QoS 0")
        mock_client.on_subscribe(mock_client, None, 1, [rc_sub_ok])
        assert listener.subscribed is True

        # Test real SUBACK ReasonCode Unspecified error
        rc_sub_err = ReasonCode(mqtt.PacketTypes.SUBACK, "Unspecified error")
        mock_client.on_subscribe(mock_client, None, 2, [rc_sub_err])
        assert listener.subscribed is False

        await listener.stop()

    # Rejection ReasonCode Not authorized on start raises QuboAuthError
    listener_fail = QuboMqttListener(auth, unit_uuid="unit-test")
    rc_auth_fail = ReasonCode(mqtt.PacketTypes.CONNACK, "Not authorized")

    def _mock_connect_fail(*args: Any, **kwargs: Any) -> int:
        if mock_client.on_connect:
            mock_client.on_connect(mock_client, None, {}, rc_auth_fail)
        return 0

    mock_client.connect.side_effect = _mock_connect_fail
    with (
        patch("paho.mqtt.client.Client", return_value=mock_client),
        pytest.raises(QuboAuthError, match="rejected credentials"),
    ):
        await listener_fail.start(connect_timeout=1.0)


@pytest.mark.asyncio
async def test_mqtt_multi_unit_subscription() -> None:
    """Verify listener subscribes to monitor topics for all specified units."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuids=["unit-alpha", "unit-beta"])
    assert listener.unit_uuids == ["unit-alpha", "unit-beta"]
    assert listener.unit_uuid == "unit-alpha"

    mock_client = _create_mock_mqtt_client(on_connect_rc=0)
    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()

        assert mock_client.subscribe.call_count == 2
        mock_client.subscribe.assert_any_call("/monitor/unit-alpha/#", qos=0)
        mock_client.subscribe.assert_any_call("/monitor/unit-beta/#", qos=0)

        await listener.stop()


@pytest.mark.asyncio
async def test_mqtt_suback_failure_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Verify SUBACK failure logs a warning and leaves subscribed False."""
    auth = QuboAuth()
    auth._tokens = TokenPayload(access_token="token", user_uuid="user-1")
    auth.get_valid_access_token = AsyncMock(return_value="token")  # type: ignore[method-assign]

    listener = QuboMqttListener(auth, unit_uuid="unit-1")
    mock_client = _create_mock_mqtt_client(on_connect_rc=0)

    with patch("paho.mqtt.client.Client", return_value=mock_client):
        await listener.start()

        # Simulate on_subscribe with failure reason code 128
        on_sub = mock_client.on_subscribe
        on_sub(mock_client, None, 1, [128])

        assert listener.subscribed is False
        assert "subscription refused" in caplog.text

        # Simulate on_subscribe with success (QoS 0)
        on_sub(mock_client, None, 2, [0])
        assert listener.subscribed is True

        await listener.stop()


def test_mqtt_repr_privacy() -> None:
    """Verify repr(QuboMqttEvent) excludes raw_payload to protect privacy."""
    event = QuboMqttEvent(
        topic="/monitor/u/d/s",
        unit_uuid="u",
        device_uuid="d",
        service="s",
        event_name="e",
        parameters={"public": "value"},
        raw_payload={"secret": "super_secret_payload"},
    )
    repr_str = repr(event)
    assert "public" in repr_str
    assert "super_secret_payload" not in repr_str
    assert "raw_payload" not in repr_str
