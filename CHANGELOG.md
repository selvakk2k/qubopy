# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-10-17

### Added
- **Camera Stream Teardown API**: Added `LiveStreamUrl(str)` preserving `app_session_id` and `instance_id` metadata from `get_live_stream_url(...)`, added `stop_live_stream(...)` to `QuboClient` implementing `DELETE /stream-manager/api/v2/sp/{sp}/stream/unit/{unit}/device/{device}`, and added session tracking with `start_stream(...)` / `stop_stream(...)` to `QuboCamera`.
- **Live Mosquitto Test Suite**: Added real Mosquitto broker test harness in `tests/test_mqtt_live.py` to verify broker drop/reconnect, token rotation, auth failure termination, and subscription timing.
- **Mypy Type Checking in CI**: Integrated `mypy` with the `pydantic.mypy` plugin in `pyproject.toml` and GitHub Actions CI workflow.

### Fixed
- **MQTT Reconnection Loop**: Restart Paho network loop (`mqttc.loop_start()`) when reconnecting after socket closure, ensuring listener resumes receiving events after broker disconnects.
- **Thread-Safe Subscription Notification**: Dispatched `_subscribed_event.set()` and `.clear()` through `loop.call_soon_threadsafe(...)` from Paho's network loop thread, preventing `wait_subscribed()` from blocking for the full timeout.
- **Multi-Unit SUBACK Tracking**: Accurately track subscription completion across multiple unit topic subscriptions.
- **Model Instantiation Typing**: Harmonized `TokenPayload` and `DeviceModelInfo` instantiation keyword arguments in `qubopy.auth` and `qubopy.client` to standard Python attribute names.

> **Note**: Reconnect and auth-failure handling verified against a local broker; lock events untested.

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
