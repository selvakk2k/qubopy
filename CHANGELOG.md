# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-10-17

### Fixed
- **Command Write Path (`PUT`)**: Updated `QuboClient.send_command` and `update_shadow_attribute` from HTTP `POST` to `PUT`, matching the official Qubo Android app Retrofit specifications.
- **Plaintext Response Parsing**: Enhanced `QuboClient.request` to parse plaintext `"SUCCESS"` responses without raising `json.JSONDecodeError`.
- **Parameter Validation**: Removed `"default"` string coercion for missing `unit_uuid` and `entity_uuid`; explicit UUID validation is now enforced to prevent invalid backend requests.
- **Bulk Shadows Route**: Updated `QuboClient.get_all_shadows` to use HTTP `POST` with unit scoping support on `/units/{unit_uuid}/devices/shadow`.
- **Device Events Route**: Corrected `PATH_DEVICE_EVENTS` to point to `/control-monitor/api/v1/sp/{sp}/device/{device_uuid}/event`.
- **Session Refresh Lifecycle**: Invalidate expired session tokens on HTTP 400/401/403 refresh rejections to prevent infinite retry loops on stale tokens, and support `refresh_token` alias in refresh payloads.

## [0.1.3] - 2026-10-17

### Added
- **`QuboMqttListener` / `QuboMqttEvent`** (optional extra: `pip install "qubopy[mqtt]"`): Real-time events from `/monitor/{unit}/#` using user UUID and access token as broker credentials; automatic unit discovery or explicit `unit_uuids`; `add_event_listener(...)` with optional `device_uuid` and `service` filters; `seed_state()` from REST v2 shadow; `wait_subscribed()`; `on_auth_failure` callback; automatic reconnect with token refresh and bounded backoff; and sensitive key redaction in debug logs. Subscribes to `/monitor` only.
- **v2 Device Shadow Reads**: Added `QuboClient.get_device_shadow_v2(...)`; `QuboLock.fetch_live_lock_state` and `fetch_live_battery` (parsed against known lock states, timestamps normalized to milliseconds, battery clamped 0–100); and `QuboLock.last_lock_state_timestamp`.
- **Telemetry & Event Endpoints**: Added `get_device_events`, `get_ooi_events`, `get_lock_events`, `generate_lock_otp` / `QuboLock.generate_guest_otp`, `get_plug_energy_history` / `QuboPlug.get_energy_history`, `get_device_storage` / `QuboCamera.get_storage_info`, and `get_purifier_pm25_insights` / `QuboAirPurifier.get_pm25_insights`.
- **Camera Streaming**: Added `QuboClient.stop_live_stream` / `QuboCamera.stop_stream` implementing cloud stream session teardown via `DELETE /stream-manager/api/v2/...`, and `LiveStreamUrl` (a `str` subclass retaining `app_session_id` and `instance_id` without breaking standard string usage).
- **Experimental Local P2P Streaming**: Added `QuboClient.initiate_p2p_call` (marked unverified on physical hardware).
- **CLI Logging**: Added `-v` and `--debug` verbose logging flags to the CLI.
- **Testing & Verification**: Added real Mosquitto broker live test suite in `tests/test_mqtt_live.py` and integrated `mypy` with `pydantic.mypy` into GitHub Actions CI.

### Changed
- `QuboClient.get_live_stream_url` and `QuboCamera.start_stream` now return `LiveStreamUrl` instead of a plain `str` (subclasses `str` for 100% backward compatibility).
- `TokenPayload.mqtt_password` / `QuboAuth.mqtt_password`: Preserved if present in cloud login responses, but unverified on physical hardware and not used by `QuboMqttListener` (which authenticates using the account JWT access token).
- Internal model instantiations in `qubopy.auth` and `qubopy.client` now use standard Python field names instead of JSON aliases.

### Removed
- **`PATH_MQTT_CREDENTIALS`**: Removed from `const.py`. The endpoint pointed to the app's *remove MQTT connection* (`DELETE`) route rather than credentials, as the MQTT broker authenticates directly with the user UUID and JWT access token. Callers importing this constant must remove it.

### Fixed
- **MQTT Network Loop on Reconnect**: Ensured Paho's network loop restarts (`mqttc.loop_start()`) when reconnecting after socket closure.
- **Thread-Safe Event Loop Signaling**: Dispatched `_subscribed_event.set()` and `.clear()` via `loop.call_soon_threadsafe(...)` from Paho's network thread, preventing `wait_subscribed()` from blocking for the full timeout.
- **Multi-Unit SUBACK Tracking**: Accurately track subscription completion across multiple unit topic subscriptions.
- **Documentation**: Corrected MQTT topic hierarchies (`/monitor/{unit}/#` and `/control/{unit}/{device}/{service}`), clarified token-based authentication, noted broker rejection of `/config/...`, and added a Verification Status table.

> **Note**: Reconnect and auth-failure handling verified against a local Mosquitto broker. MQTT connect/auth/subscribe and camera events tested on a real Qubo camera. Lock events (`lockControl`) and live token-expiry behavior are untested.

## [0.1.2] - 2026-10-12

### Fixed
- **Profile Email Selection**: Fixed `--account-uuid` profile email selection in CLI and auth workflows.
- **Secret Masking**: Masked tokens in `qubopy tokens --json` by default unless `--show-secrets` is supplied.
- **Package Distribution**: Added `MANIFEST.in` to bundle `tests/conftest.py` in source distributions, and added sdist build/test verification step in CI.

## [0.1.1] - 2026-10-11

### Fixed
- **Packaging**: Corrected package data definitions and CLI entry points.
- **Documentation**: Updated README with session caching instructions.

## [0.1.0] - 2026-10-11

### Added
- Initial release of `qubopy`: asynchronous client library and local BLE enabler for Qubo smart home devices.
- Cloud REST client, device abstractions (Air Purifier, Camera, Light, Lock, Plug, Sensor), BLE lock key extraction, and MQTT event listener.
