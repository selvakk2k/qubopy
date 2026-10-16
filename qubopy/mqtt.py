"""Real-time cloud MQTT listener and event dispatcher for Qubo devices."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qubopy.const import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from qubopy.exceptions import QuboAuthError

if TYPE_CHECKING:
    from qubopy.auth import QuboAuth
    from qubopy.client import QuboClient
    from qubopy.devices.base import QuboDevice

_LOGGER = logging.getLogger(__name__)

# Sensitive payload keys redacted from debug logging
SENSITIVE_KEYS = {
    "aeskey",
    "aesiv",
    "aes_key",
    "aes_iv",
    "offerdata",
    "password",
    "accesstoken",
    "access_token",
    "refreshtoken",
    "refresh_token",
    "token",
    "otp",
}


def _redact_payload(data: Any) -> Any:
    """Recursively redact sensitive cryptographic keys and tokens from payloads."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                redacted[k] = "<REDACTED>"
            else:
                redacted[k] = _redact_payload(v)
        return redacted
    if isinstance(data, list):
        return [_redact_payload(item) for item in data]
    return data


@dataclass
class QuboMqttEvent:
    """Normalized real-time event received from the Qubo MQTT broker."""

    topic: str
    unit_uuid: str
    device_uuid: str
    service: str
    event_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    operation_state: str | None = None
    timestamp: int | None = None
    src_device_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class QuboMqttListener:
    """Asynchronous MQTT subscriber for real-time Qubo device telemetry.

    Subscribes strictly to `/monitor/{unit_uuid}/#` by default to avoid
    exposing sensitive command payloads (such as WebRTC streaming keys)
    relayed on the `/control` channel.
    """

    def __init__(
        self,
        auth_or_client: QuboAuth | QuboClient,
        unit_uuid: str | None = None,
        client_id: str | None = None,
        broker_host: str = MQTT_BROKER_HOST,
        broker_port: int = MQTT_BROKER_PORT,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Initialize the Qubo MQTT listener.

        Args:
            auth_or_client: Active QuboAuth or QuboClient instance.
            unit_uuid: Qubo home unit UUID. Auto-discovered if client is provided.
            client_id: Custom MQTT client ID. Defaults to a randomized ID to prevent
                disconnecting the user's mobile app session.
            broker_host: Qubo MQTT broker hostname.
            broker_port: Qubo MQTT broker TLS port.
            loop: Running asyncio event loop.
        """
        # Distinguish client vs auth
        if hasattr(auth_or_client, "auth"):
            self._client: QuboClient | None = auth_or_client  # type: ignore[assignment]
            self._auth: QuboAuth = auth_or_client.auth
        else:
            self._client = None
            self._auth = auth_or_client  # type: ignore[assignment]

        self._unit_uuid = unit_uuid
        self._client_id = client_id or f"qubopy_{uuid.uuid4().hex[:8]}"
        self._broker_host = broker_host
        self._broker_port = broker_port
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

        self._mqttc: Any | None = None
        self._is_running = False
        self._listeners: list[
            tuple[
                Callable[[QuboMqttEvent], Coroutine[Any, Any, None] | None],
                str | None,
                str | None,
            ]
        ] = []

    @property
    def is_running(self) -> bool:
        """Return True if the MQTT client loop is currently running."""
        return self._is_running

    @property
    def client_id(self) -> str:
        """Return the active MQTT client ID."""
        return self._client_id

    @property
    def unit_uuid(self) -> str | None:
        """Return the target unit UUID."""
        return self._unit_uuid

    def add_event_listener(
        self,
        callback: Callable[[QuboMqttEvent], Coroutine[Any, Any, None] | None],
        device_uuid: str | None = None,
        service: str | None = None,
    ) -> Callable[[], None]:
        """Register a callback for incoming MQTT telemetry events.

        Args:
            callback: Async coroutine function or standard synchronous function.
            device_uuid: Optional filter to receive events only from this device UUID.
            service: Optional filter to receive events only from this service
                (e.g. 'panTiltControl').

        Returns:
            An unsubscribe function that removes the registered listener when invoked.
        """
        item = (callback, device_uuid, service)
        self._listeners.append(item)

        def unsubscribe() -> None:
            if item in self._listeners:
                self._listeners.remove(item)

        return unsubscribe

    async def seed_state(self) -> list[QuboDevice]:
        """Query REST v2 shadow states at startup to establish baseline entity state.

        Returns:
            List of all initialized QuboDevice instances with fresh reported state.
        """
        if self._client is None:
            raise RuntimeError(
                "State seeding requires a QuboClient instance, but only QuboAuth was provided."
            )
        return await self._client.get_all_devices()

    async def start(self) -> None:
        """Connect to the Qubo MQTT broker and start processing incoming telemetry."""
        if self._is_running:
            return

        try:
            import paho.mqtt.client as mqtt
        except ImportError as err:
            raise ImportError(
                "paho-mqtt is required to use QuboMqttListener. "
                "Install it with: pip install 'qubopy[mqtt]'"
            ) from err

        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        # Auto-discover unit_uuid if not supplied
        if not self._unit_uuid:
            if self._client is not None:
                units = await self._client.get_units()
                if units:
                    first = units[0]
                    self._unit_uuid = (
                        first.get("unitUUID") or first.get("uuid") or first.get("unitId")
                    )
            if not self._unit_uuid:
                raise ValueError(
                    "unit_uuid must be explicitly provided or discoverable via QuboClient."
                )

        token = await self._auth.get_valid_access_token()
        user_uuid = self._auth.user_uuid
        if not user_uuid:
            raise QuboAuthError("Cannot authenticate MQTT session: user_uuid is missing.")

        # Instantiate Paho MQTT Client (API version 2)
        mqttc = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            clean_session=True,
        )
        mqttc.username_pw_set(username=user_uuid, password=token)
        mqttc.tls_set_context(ssl.create_default_context())

        topic = f"/monitor/{self._unit_uuid}/#"

        def on_connect(
            client: Any,
            userdata: Any,
            flags: Any,
            rc: Any,
            properties: Any = None,
        ) -> None:
            is_success = (
                (rc == 0) if isinstance(rc, int) else (not getattr(rc, "is_failure", True))
            )
            if is_success:
                _LOGGER.info(
                    "Connected to Qubo MQTT broker (%s). Subscribing to %s",
                    self._broker_host,
                    topic,
                )
                client.subscribe(topic, qos=0)
            else:
                _LOGGER.error("Qubo MQTT connection rejected by broker: rc=%s", rc)

        def on_message(client: Any, userdata: Any, msg: Any) -> None:
            self._handle_raw_message(msg.topic, msg.payload)

        def on_disconnect(
            client: Any,
            userdata: Any,
            flags: Any,
            rc: Any,
            properties: Any = None,
        ) -> None:
            _LOGGER.debug("Disconnected from Qubo MQTT broker: rc=%s", rc)

        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.on_disconnect = on_disconnect

        self._mqttc = mqttc

        # Connect on executor to avoid blocking the asyncio event loop
        await self._loop.run_in_executor(
            None,
            mqttc.connect,
            self._broker_host,
            self._broker_port,
            60,
        )
        mqttc.loop_start()
        self._is_running = True

    async def stop(self) -> None:
        """Disconnect from the MQTT broker and stop the background network thread."""
        if not self._is_running or self._mqttc is None:
            return

        mqttc = self._mqttc
        self._mqttc = None
        self._is_running = False

        if self._loop is not None:
            await self._loop.run_in_executor(None, mqttc.disconnect)
            await self._loop.run_in_executor(None, mqttc.loop_stop)
        else:
            mqttc.disconnect()
            mqttc.loop_stop()

    def _handle_raw_message(self, topic: str, raw_payload: bytes) -> None:
        """Process incoming raw message bytes from Paho thread."""
        try:
            payload_str = raw_payload.decode("utf-8")
            data = json.loads(payload_str)
        except Exception as err:
            _LOGGER.warning("Could not decode MQTT JSON packet on %s: %s", topic, err)
            return

        redacted = _redact_payload(data)
        _LOGGER.debug("Qubo MQTT Telemetry on %s: %s", topic, redacted)

        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

        events = self._parse_events(topic, data)
        for ev in events:
            if loop and loop.is_running():
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop is loop:
                        loop.create_task(self._dispatch_event(ev))
                    else:
                        asyncio.run_coroutine_threadsafe(self._dispatch_event(ev), loop)
                except RuntimeError:
                    asyncio.run_coroutine_threadsafe(self._dispatch_event(ev), loop)

    def _parse_events(self, topic: str, payload: dict[str, Any]) -> list[QuboMqttEvent]:
        """Parse raw wire payload into normalized QuboMqttEvent instances."""
        parts = topic.strip("/").split("/")
        # Expected topic format: monitor/{unit_uuid}/{device_uuid}/{service}
        unit_from_topic = parts[1] if len(parts) > 1 else (self._unit_uuid or "")
        dev_from_topic = parts[2] if len(parts) > 2 else ""
        service_from_topic = parts[3] if len(parts) > 3 else ""

        devices = payload.get("devices") if isinstance(payload.get("devices"), dict) else payload

        dev_uuid = str(devices.get("deviceUUID") or dev_from_topic)
        unit_uuid = str(devices.get("unitUUID") or unit_from_topic)
        src_device_id = devices.get("srcDeviceId")
        timestamp = devices.get("timestamp")
        op_state = devices.get("operationState")

        services = devices.get("services")
        results: list[QuboMqttEvent] = []

        if isinstance(services, dict):
            for s_name, s_data in services.items():
                if not isinstance(s_data, dict):
                    continue
                events_dict = s_data.get("events")
                if isinstance(events_dict, dict):
                    for e_name, e_val in events_dict.items():
                        params: dict[str, Any] = {}
                        if isinstance(e_val, dict):
                            if "parameters" in e_val and isinstance(e_val["parameters"], dict):
                                params = e_val["parameters"]
                            else:
                                params = {k: v for k, v in e_val.items() if k != "parameters"}
                        results.append(
                            QuboMqttEvent(
                                topic=topic,
                                unit_uuid=unit_uuid,
                                device_uuid=dev_uuid,
                                service=s_name,
                                event_name=e_name,
                                parameters=params,
                                operation_state=op_state,
                                timestamp=timestamp,
                                src_device_id=src_device_id,
                                raw_payload=payload,
                            )
                        )

        # Fallback for heartbeat or events without nested services
        if not results:
            results.append(
                QuboMqttEvent(
                    topic=topic,
                    unit_uuid=unit_uuid,
                    device_uuid=dev_uuid,
                    service=service_from_topic or "generic",
                    event_name=None,
                    parameters={},
                    operation_state=op_state,
                    timestamp=timestamp,
                    src_device_id=src_device_id,
                    raw_payload=payload,
                )
            )

        return results

    async def _dispatch_event(self, event: QuboMqttEvent) -> None:
        """Dispatch a normalized event to registered callbacks."""
        for callback, device_filter, service_filter in list(self._listeners):
            if device_filter and device_filter != event.device_uuid:
                continue
            if service_filter and service_filter != event.service:
                continue
            try:
                res = callback(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as err:
                _LOGGER.exception("Exception in Qubo MQTT event listener callback: %s", err)

    async def __aenter__(self) -> QuboMqttListener:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()
