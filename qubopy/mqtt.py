"""Real-time cloud MQTT listener and event dispatcher for Qubo devices."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qubopy.const import MQTT_BROKER_HOST, MQTT_BROKER_PORT
from qubopy.exceptions import QuboAuthError, QuboConnectionError
from qubopy.models import extract_unit_uuid

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
    "offerresponse",
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
    raw_payload: dict[str, Any] = field(default_factory=dict, repr=False)


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
        unit_uuids: Sequence[str] | None = None,
        client_id: str | None = None,
        broker_host: str = MQTT_BROKER_HOST,
        broker_port: int = MQTT_BROKER_PORT,
        loop: asyncio.AbstractEventLoop | None = None,
        on_auth_failure: Callable[[], Coroutine[Any, Any, None] | None] | None = None,
    ) -> None:
        """Initialize the Qubo MQTT listener.

        Args:
            auth_or_client: Active QuboAuth or QuboClient instance.
            unit_uuid: Single Qubo home unit UUID.
            unit_uuids: Sequence of home unit UUIDs to subscribe to simultaneously.
            client_id: Custom MQTT client ID. Defaults to a randomized ID to prevent
                disconnecting the user's mobile app session.
            broker_host: Qubo MQTT broker hostname.
            broker_port: Qubo MQTT broker TLS port.
            loop: Running asyncio event loop.
            on_auth_failure: Optional sync or async callback invoked when token
                renewal fails on reconnect (e.g. expired 1-hour mobile OTP tokens).
        """
        # Distinguish client vs auth
        if hasattr(auth_or_client, "auth"):
            self._client: QuboClient | None = auth_or_client  # type: ignore[assignment]
            self._auth: QuboAuth = auth_or_client.auth
        else:
            self._client = None
            self._auth = auth_or_client  # type: ignore[assignment]

        if unit_uuids is not None:
            self._unit_uuids: list[str] = list(unit_uuids)
        elif unit_uuid is not None:
            self._unit_uuids = [unit_uuid]
        else:
            self._unit_uuids = []

        self._client_id = client_id or f"qubopy_{uuid.uuid4().hex[:8]}"
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._on_auth_failure = on_auth_failure

        self._loop: asyncio.AbstractEventLoop | None = loop
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

        self._mqttc: Any | None = None
        self._is_running = False
        self._stopping = False
        self._subscribed = False
        self._subscribed_event: asyncio.Event = asyncio.Event()
        self._subscribed_mids: set[int] = set()
        self._connect_future: asyncio.Future[bool] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

        self._listeners: list[
            tuple[
                Callable[[QuboMqttEvent], Coroutine[Any, Any, None] | None],
                str | None,
                str | None,
            ]
        ] = []

    @property
    def is_running(self) -> bool:
        """Return True if the MQTT client loop is currently active."""
        return self._is_running

    @property
    def subscribed(self) -> bool:
        """Return True if the broker has confirmed subscription to monitor topics."""
        return self._subscribed

    async def wait_subscribed(self, timeout: float = 5.0) -> bool:
        """Wait until the broker confirms subscription to monitor topics.

        Args:
            timeout: Seconds to wait for broker SUBACK.

        Returns:
            True if subscription was confirmed, False if timed out.
        """
        try:
            await asyncio.wait_for(self._subscribed_event.wait(), timeout=timeout)
            return True
        except (TimeoutError, asyncio.TimeoutError):
            return False

    @property
    def client_id(self) -> str:
        """Return the active MQTT client ID."""
        return self._client_id

    @property
    def unit_uuid(self) -> str | None:
        """Return primary unit UUID."""
        return self._unit_uuids[0] if self._unit_uuids else None

    @property
    def unit_uuids(self) -> list[str]:
        """Return all subscribed unit UUIDs."""
        return list(self._unit_uuids)

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

    async def start(self, connect_timeout: float = 15.0) -> None:
        """Connect to the Qubo MQTT broker and wait for CONNACK validation.

        Note:
            Returns once CONNACK is validated, before SUBACK arrives. Use
            `await listener.wait_subscribed()` to wait for broker subscription confirmation.

        Args:
            connect_timeout: Seconds to wait for broker CONNACK before raising
                QuboConnectionError.
        """
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
        loop = self._loop

        # Auto-discover units if not supplied
        if not self._unit_uuids:
            if self._client is not None:
                units = await self._client.get_units()
                discovered: list[tuple[str, str]] = []
                for u in units:
                    uid = extract_unit_uuid(u)
                    name = (
                        u.get("name", "Home")
                        if isinstance(u, dict)
                        else getattr(u, "name", "Home")
                    )
                    if uid:
                        discovered.append((uid, str(name)))
                if len(discovered) > 1:
                    _LOGGER.warning(
                        "Found %d units on Qubo account. Subscribing to default unit '%s' (%s). "
                        "Pass 'unit_uuids' to listen across all units.",
                        len(discovered),
                        discovered[0][1],
                        discovered[0][0],
                    )
                if discovered:
                    self._unit_uuids = [discovered[0][0]]

            if not self._unit_uuids:
                raise ValueError(
                    "unit_uuid or unit_uuids must be explicitly provided or "
                    "discoverable via QuboClient."
                )

        token = await self._auth.get_valid_access_token()
        user_uuid = self._auth.user_uuid
        if not user_uuid:
            raise QuboAuthError("Cannot authenticate MQTT session: user_uuid is missing.")

        self._stopping = False
        self._subscribed = False
        self._subscribed_event.clear()

        # Instantiate Paho MQTT Client (API version 2)
        try:
            mqttc = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self._client_id,
                clean_session=True,
                reconnect_on_failure=False,
            )
        except TypeError:
            mqttc = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self._client_id,
                clean_session=True,
            )
            if hasattr(mqttc, "_reconnect_on_failure"):
                mqttc._reconnect_on_failure = False

        mqttc.suppress_exceptions = True
        mqttc.username_pw_set(username=user_uuid, password=token)
        mqttc.tls_set_context(ssl.create_default_context())

        self._connect_future = loop.create_future()

        def on_connect(
            client: Any,
            userdata: Any,
            flags: Any,
            rc: Any,
            properties: Any = None,
        ) -> None:
            code = getattr(rc, "value", rc) if not isinstance(rc, int) else rc
            is_success = (
                (code == 0) if isinstance(code, int) else (not getattr(rc, "is_failure", True))
            )

            if is_success:
                _LOGGER.info(
                    "Connected to Qubo MQTT broker (%s). Subscribing to monitor topics...",
                    self._broker_host,
                )
                self._subscribed_mids.clear()
                self._subscribed = False
                if loop.is_running():
                    loop.call_soon_threadsafe(self._subscribed_event.clear)
                else:
                    self._subscribed_event.clear()
                for u in self._unit_uuids:
                    client.subscribe(f"/monitor/{u}/#", qos=0)

                if self._connect_future and not self._connect_future.done():
                    loop.call_soon_threadsafe(self._connect_future.set_result, True)
            else:
                _LOGGER.error("Qubo MQTT connection rejected by broker: rc=%s", rc)
                if loop.is_running():
                    loop.call_soon_threadsafe(self._subscribed_event.clear)
                else:
                    self._subscribed_event.clear()
                if self._connect_future and not self._connect_future.done():
                    if code in (4, 5, 134, 135):
                        err: Exception = QuboAuthError(
                            f"MQTT broker rejected credentials (rc={rc})"
                        )
                    else:
                        err = QuboConnectionError(f"MQTT broker rejected connection (rc={rc})")
                    loop.call_soon_threadsafe(self._connect_future.set_exception, err)
                elif code in (4, 5, 134, 135):
                    # Broker rejected credentials on reconnect (e.g. revoked/expired token)
                    _LOGGER.error(
                        "MQTT credentials rejected on reconnect (rc=%s). Stopping listener.",
                        rc,
                    )
                    self._is_running = False
                    if loop.is_running():
                        loop.call_soon_threadsafe(
                            lambda: loop.create_task(self._handle_auth_failure())
                        )

        def on_subscribe(
            client: Any,
            userdata: Any,
            mid: int,
            reason_code_list: Any,
            properties: Any = None,
        ) -> None:
            has_failure = False
            for r in reason_code_list:
                code = getattr(r, "value", r) if not isinstance(r, int) else r
                is_failure = getattr(
                    r, "is_failure", code >= 128 if isinstance(code, int) else False
                )
                if is_failure:
                    has_failure = True
                    _LOGGER.warning("MQTT subscription refused by broker for MID %s: %s", mid, r)
            if has_failure:
                self._subscribed_mids.clear()
                self._subscribed = False
                if loop.is_running():
                    loop.call_soon_threadsafe(self._subscribed_event.clear)
                else:
                    self._subscribed_event.clear()
            else:
                self._subscribed_mids.add(mid)
                self._subscribed = len(self._subscribed_mids) >= len(self._unit_uuids)
                if self._subscribed:
                    if loop.is_running():
                        loop.call_soon_threadsafe(self._subscribed_event.set)
                    else:
                        self._subscribed_event.set()

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
            self._subscribed = False
            self._subscribed_mids.clear()
            if loop.is_running():
                loop.call_soon_threadsafe(self._subscribed_event.clear)
            else:
                self._subscribed_event.clear()
            if not self._stopping and self._is_running and loop.is_running():
                loop.call_soon_threadsafe(self._start_reconnect_task)

        mqttc.on_connect = on_connect
        mqttc.on_subscribe = on_subscribe
        mqttc.on_message = on_message
        mqttc.on_disconnect = on_disconnect

        self._mqttc = mqttc

        # Connect on executor to avoid blocking the asyncio event loop
        await loop.run_in_executor(
            None,
            mqttc.connect,
            self._broker_host,
            self._broker_port,
            60,
        )
        mqttc.loop_start()

        # Await broker acceptance
        try:
            await asyncio.wait_for(self._connect_future, timeout=connect_timeout)
            self._is_running = True
        except (TimeoutError, asyncio.TimeoutError) as err:
            await self.stop()
            raise QuboConnectionError(
                f"Timed out waiting for Qubo MQTT broker connection ({connect_timeout}s)"
            ) from err
        except Exception:
            await self.stop()
            raise

    async def _handle_auth_failure(self) -> None:
        """Handle fatal authentication failure (expired token or rejected credentials)."""
        await self.stop()
        if self._on_auth_failure:
            try:
                res = self._on_auth_failure()
                if asyncio.iscoroutine(res):
                    await res
            except Exception as cb_err:
                _LOGGER.exception("Exception in on_auth_failure callback: %s", cb_err)

    def _start_reconnect_task(self) -> None:
        """Schedule background reconnection task on the event loop."""
        loop = self._loop
        if (
            not self._stopping
            and self._is_running
            and (self._reconnect_task is None or self._reconnect_task.done())
            and loop is not None
            and loop.is_running()
        ):
            self._reconnect_task = loop.create_task(self._reconnect_worker())

    @staticmethod
    def _reconnect_sync(mqttc: Any) -> None:
        """Synchronously stop the loop thread, reconnect socket, and restart the loop thread."""
        mqttc.loop_stop()
        mqttc.reconnect()
        mqttc.loop_start()

    async def _reconnect_worker(self) -> None:
        """Handle bounded exponential reconnection and token renewal."""
        attempt = 0
        while self._is_running and not self._stopping:
            attempt += 1
            delay = min(60.0, 1.0 * (2 ** (attempt - 1)))
            _LOGGER.info("MQTT reconnect attempt %d scheduled in %.1fs...", attempt, delay)
            await asyncio.sleep(delay)
            if not self._is_running or self._stopping:
                break

            # Attempt token renewal
            try:
                fresh_token = await self._auth.get_valid_access_token()
            except QuboAuthError as auth_err:
                _LOGGER.error(
                    "MQTT reconnect halted: access token expired and cannot be refreshed "
                    "automatically (%s). Interactive login required.",
                    auth_err,
                )
                await self._handle_auth_failure()
                break
            except Exception as err:
                _LOGGER.warning("Error renewing access token for reconnect: %s", err)
                continue

            user_uuid = self._auth.user_uuid
            if not user_uuid or not self._mqttc:
                break

            self._mqttc.username_pw_set(username=user_uuid, password=fresh_token)
            loop = self._loop
            try:
                if loop is not None and loop.is_running():
                    await loop.run_in_executor(None, self._reconnect_sync, self._mqttc)
                else:
                    self._reconnect_sync(self._mqttc)
                _LOGGER.info("MQTT reconnect command dispatched to broker.")
                break
            except Exception as rec_err:
                _LOGGER.warning("MQTT reconnect socket error (attempt %d): %s", attempt, rec_err)

    async def stop(self) -> None:
        """Disconnect from the MQTT broker and stop background tasks."""
        self._stopping = True
        self._is_running = False
        self._subscribed = False
        self._subscribed_event.clear()
        self._subscribed_mids.clear()

        current_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            pass

        if (
            self._reconnect_task
            and not self._reconnect_task.done()
            and self._reconnect_task is not current_task
        ):
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._mqttc is not None:
            mqttc = self._mqttc
            self._mqttc = None

            loop = self._loop
            if loop is not None and loop.is_running():
                await loop.run_in_executor(None, mqttc.disconnect)
                await loop.run_in_executor(None, mqttc.loop_stop)
            else:
                mqttc.disconnect()
                mqttc.loop_stop()

        self._stopping = False

    def _handle_raw_message(self, topic: str, raw_payload: bytes) -> None:
        """Process incoming raw message bytes from Paho thread."""
        try:
            try:
                payload_str = raw_payload.decode("utf-8")
                data = json.loads(payload_str)
            except Exception as decode_err:
                _LOGGER.warning("Could not decode MQTT JSON packet on %s: %s", topic, decode_err)
                return

            if not isinstance(data, dict):
                _LOGGER.warning(
                    "Ignoring non-dict MQTT JSON packet on %s (type=%s)",
                    topic,
                    type(data).__name__,
                )
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
        except Exception as err:
            _LOGGER.exception("Unexpected error processing MQTT packet on %s: %s", topic, err)

    def _parse_events(self, topic: str, payload: dict[str, Any]) -> list[QuboMqttEvent]:
        """Parse raw wire payload into normalized QuboMqttEvent instances."""
        if not isinstance(payload, dict):
            return []

        parts = topic.strip("/").split("/")
        # Expected topic format: monitor/{unit_uuid}/{device_uuid}/{service}
        unit_from_topic = parts[1] if len(parts) > 1 else (self.unit_uuid or "")
        dev_from_topic = parts[2] if len(parts) > 2 else ""
        service_from_topic = parts[3] if len(parts) > 3 else ""

        devices_raw = payload.get("devices")
        devices = devices_raw if isinstance(devices_raw, dict) else payload

        dev_uuid = (
            str(devices.get("deviceUUID") or dev_from_topic)
            if isinstance(devices, dict)
            else dev_from_topic
        )
        unit_uuid = (
            str(devices.get("unitUUID") or unit_from_topic)
            if isinstance(devices, dict)
            else unit_from_topic
        )
        src_device_id = devices.get("srcDeviceId") if isinstance(devices, dict) else None
        timestamp = devices.get("timestamp") if isinstance(devices, dict) else None
        op_state = devices.get("operationState") if isinstance(devices, dict) else None

        services = devices.get("services") if isinstance(devices, dict) else None
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
                                service=str(s_name),
                                event_name=str(e_name),
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
