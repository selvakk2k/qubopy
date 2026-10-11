# Qubo Python Client Library & BLE Enabler (`qubopy`)

[![PyPI version](https://badge.fury.io/py/qubopy.svg)](https://badge.fury.io/py/qubopy)
[![Python Version](https://img.shields.io/pypi/pyversions/qubopy.svg)](https://pypi.org/project/qubopy/)
[![Release](https://img.shields.io/github/v/release/selvakk2k/qubopy?style=flat-square)](https://github.com/selvakk2k/qubopy/releases)
[![AI-Assisted](https://img.shields.io/badge/AI%20Assisted-Antigravity%20%7C%20Claude-blueviolet?style=flat-square&logo=google)](https://github.com/selvakk2k)
[![AI Attribution](https://img.shields.io/badge/AI%20Attribution-AIA%20PAI%20Nc%20Hin-orange?style=flat-square)](https://aiattribution.github.io/interpret-attribution)

An asynchronous Python client library and local Bluetooth Low Energy (BLE) credential extraction utility for Qubo smart home devices and Deftun smart locks.

---

## Table of Contents

- [Overview](#overview)
- [Hardware Compatibility Matrix](#hardware-compatibility-matrix)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [1. Cloud Appliance Control](#1-cloud-appliance-control)
  - [2. Exporting BLE Smart Lock Credentials](#2-exporting-ble-smart-lock-credentials)
- [Command Line Interface (CLI)](#command-line-interface-cli)
- [Local BLE Architecture for Smart Locks](#local-ble-architecture-for-smart-locks)
- [API Architecture](#api-architecture)
- [Contributing & Testing](#contributing--testing)
- [Credits & License](#credits--license)

---

## Overview

The Qubo smart home ecosystem consists of two distinct communication models:

1. **Wi-Fi Appliances (Cloud Managed)**: Smart Plugs, Air Purifiers, Smart Bulbs, and Security Cameras connect outbound to Qubo cloud services over TLS REST and MQTT. `qubopy` interacts with Qubo's cloud REST gateway (`srvcapp.platform.quboworld.com`) to discover units, retrieve shadow states, and dispatch control commands.
2. **Bluetooth Smart Locks (100% Local BLE Control)**: Qubo smart door locks (`HLM`/`HLW` series) operate via Bluetooth Low Energy without an integrated Wi-Fi radio. The mobile app syncs offline authentication keys (`dbtauthkey`) and offline PIN seeds (`dbtoffkey`) from the cloud. `qubopy` extracts these cryptographic keys directly from the account, allowing local integration with Home Assistant Bluetooth Proxies and ESPHome without requiring active internet access for lock operations.

---

## Hardware Compatibility Matrix

| Series | Category | Example Models | Functions & Sensors | Integration Mode |
| :--- | :--- | :--- | :--- | :--- |
| `HSP` | Smart Plugs | `HSP01` (16A), `HSP02` (10A), `HSP10` | Switch, Voltage, Current, Active Power (W), Energy (kWh) | Cloud REST |
| `HPH` | Air Purifiers | `HPH01`–`HPH08` (Q200 to Q1000) | Fan Speed, Auto/Sleep Presets, PM2.5, Filter Life, Child Lock | Cloud REST |
| `HLB` | Smart Lighting | `HLB01`, `HLB10` | State, Brightness, RGB Color, White Temperature | Cloud REST |
| `HLM` / `HLW` | Door Locks | `HLM01`–`HLM10`, `HLR01`, `HLW01` | Lock/Unlock, Battery Level, Offline BLE Key Export | Local BLE + Cloud Sync |
| `HCP` / `HCO` | Cameras | `HCP01`–`HCP19`, `HCO04`–`HCO07` | RTSP Stream Query, Privacy Mask, Siren, Motion Status | Cloud REST + Local RTSP |
| `HCD` | Doorbells | `HCD01`, `HCD04` | Ring Event, Chime, RTSP Stream | Cloud REST + Local RTSP |
| `HDS` / `HGS` | Security | `HDS01` (Contact), `HGS01` (Gas), `HSA01` (Smoke) | Binary Alarms, Battery Telemetry | Cloud REST |
| `HDT` | Climate | `HDT01` | Temperature (°C), Humidity (%) | Cloud REST |

---

## Installation

Install `qubopy` via `pip`:

```bash
pip install qubopy
```

---

## Quick Start

### 1. Cloud Appliance Control

```python
import asyncio
from qubopy import QuboAuth, QuboClient
from qubopy.devices import QuboPlug

async def main():
    # Authenticate via email or phone
    auth = QuboAuth()
    await auth.login_with_email("user@example.com", "your_password")

    # Connect client
    async with QuboClient(auth) as client:
        # Discover units and devices
        devices = await client.get_all_devices()
        print(f"Discovered {len(devices)} devices")

        for device in devices:
            print(f"- {device.name} ({device.model}) -> {device.device_id}")

            # Control smart plugs
            if isinstance(device, QuboPlug):
                await device.turn_on()
                shadow = await device.refresh()
                print(f"  Power: {device.power_watts} W, Voltage: {device.voltage} V")

asyncio.run(main())
```

### 2. Exporting BLE Smart Lock Credentials

Extract the offline cryptographic keys for use in Home Assistant or ESPHome:

```python
import asyncio
from qubopy import QuboAuth, QuboClient
from qubopy.devices import QuboLock

async def main():
    auth = QuboAuth()
    await auth.login_with_email("user@example.com", "your_password")

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        locks = [d for d in devices if isinstance(d, QuboLock)]

        for lock in locks:
            keys = await lock.get_ble_lock_keys()
            print("=== Qubo BLE Lock Credentials ===")
            print(f"Device Name: {keys.device_name}")
            print(f"Bluetooth MAC: {keys.mac_address}")
            print(f"Auth Key: {keys.auth_key}")
            print(f"Offline Key: {keys.offline_key}")
            print(f"Admin PIN: {keys.admin_pass}")

asyncio.run(main())
```

---

## Command Line Interface (CLI)

`qubopy` includes a command-line interface for testing authentication and inspecting device parameters:

```bash
# Authenticate using email and password
python -m qubopy login --email user@example.com --password "secret"

# Authenticate using phone number and OTP
python -m qubopy login-phone --phone 9876543210 --isd +91
python -m qubopy verify-otp --phone 9876543210 --otp 1234

# List all units and paired devices
python -m qubopy list-devices

# Export local BLE credentials for smart locks
python -m qubopy export-ble-keys --device-id <device_uuid>
```

---

## Local BLE Architecture for Smart Locks

Qubo Bluetooth smart locks are manufactured by Deftun (hardware architecture `P01`). The lock parameters stored in the cloud include:

* `dmac`: Physical Bluetooth MAC address.
* `dbtauthkey`: Cryptographic session key used during GATT handshake.
* `dbtoffkey`: Cryptographic seed for computing time-based offline passcodes.
* `dadminpass`: Master PIN code.

### GATT Services and Characteristics

* **Main GATT Service**: `0000fee0-0000-1000-8000-00805f9b34fb`
* **Auth / Write Characteristic**: `0000fee1-0000-1000-8000-00805f9b34fb`
* **Notify / State Characteristic**: `0000fee2-0000-1000-8000-00805f9b34fb`

Once keys are exported via `qubopy`, an ESP32 or local Bluetooth controller can establish a direct local connection without connecting to Qubo cloud servers.

---

## Contributing & Testing

Run unit tests locally with `pytest`:

```bash
pytest tests/ -v
```

Lint with `ruff`:

```bash
ruff check .
```

---

## Credits & License

### Author & Contributors
* **Architecture & Lead Engineering**: [@selvakk2k](https://github.com/selvakk2k)
* **Code Implementation & Engineering**: **Antigravity** (Google DeepMind)
* **Code Review & Pre-Release Auditing**: **Claude** (Anthropic)

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
