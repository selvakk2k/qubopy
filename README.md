# Qubo Python Client Library & BLE Enabler (`qubopy`)

[![PyPI version](https://badge.fury.io/py/qubopy.svg)](https://badge.fury.io/py/qubopy)
[![Python Version](https://img.shields.io/pypi/pyversions/qubopy.svg)](https://pypi.org/project/qubopy/)
[![Release](https://img.shields.io/github/v/release/selvakk2k/qubopy?style=flat-square)](https://github.com/selvakk2k/qubopy/releases)
[![AI-Assisted](https://img.shields.io/badge/AI%20Assisted-Antigravity%20%7C%20Claude-blueviolet?style=flat-square&logo=google)](https://github.com/selvakk2k)
[![AI Attribution](https://img.shields.io/badge/AI%20Attribution-AIA%20PAI%20Nc%20Hin-orange?style=flat-square)](https://aiattribution.github.io/interpret-attribution)

An asynchronous Python client library and local Bluetooth Low Energy (BLE) credential extraction utility for Qubo smart home devices.

---

## Table of Contents

- [Overview](#overview)
- [Hardware Compatibility Matrix](#hardware-compatibility-matrix)
- [Installation](#installation)
- [Authentication & Account Guidelines](#authentication--account-guidelines)
- [Quick Start](#quick-start)
  - [1. Cloud Appliance Control](#1-cloud-appliance-control)
  - [2. Smart Door Lock Control (Cloud Gateway & Local BLE)](#2-smart-door-lock-control-cloud-gateway--local-ble)
- [Command Line Interface (CLI)](#command-line-interface-cli)
- [IP Camera & Media Streaming Architecture](#ip-camera--media-streaming-architecture)
- [Local BLE Architecture for Smart Locks](#local-ble-architecture-for-smart-locks)
  - [GATT Services and Characteristics](#gatt-services-and-characteristics)
  - [Experimental ESPHome Configuration](#experimental-esphome-configuration)
- [Contributing & Testing](#contributing--testing)
- [Credits & License](#credits--license)

---

## Overview

The Qubo smart home ecosystem consists of two distinct communication models:

1. **Wi-Fi Appliances (Cloud Managed)**: Smart Plugs, Air Purifiers, Smart Bulbs, and Security Cameras connect outbound to Qubo cloud services over TLS REST and MQTT. `qubopy` interacts with Qubo's cloud REST gateway (`srvcapp.platform.quboworld.com`) to discover units, retrieve shadow states, and dispatch control commands.
2. **Bluetooth Smart Locks (Experimental Local BLE)**: Qubo smart door locks (`HLM`/`HLW` series) operate via Bluetooth Low Energy without an integrated Wi-Fi radio. The mobile app syncs offline authentication keys (`dbtauthkey`) and offline PIN seeds (`dbtoffkey`) from the cloud. `qubopy` extracts these cryptographic keys from the account for potential local integration with Home Assistant Bluetooth Proxies and ESPHome. *Note: BLE lock protocols were derived from static analysis of the official mobile app and remain untested on physical hardware.*

---

## Hardware Compatibility Matrix

| Series | Category | Example Models | Functions & Sensors | Integration Mode |
| :--- | :--- | :--- | :--- | :--- |
| `HSP` | Smart Plugs | `HSP01` (16A), `HSP02` (10A), `HSP10` | Switch, Voltage, Current, Active Power (W), Energy (kWh) | Cloud REST |
| `HPH` | Air Purifiers | `HPH01`–`HPH08` (Q200 to Q1000) | Fan Speed, Auto/Sleep Presets, PM2.5, Filter Life, Child Lock | Cloud REST |
| `HLB` | Smart Lighting | `HLB01`, `HLB10` | State, Brightness, RGB Color, White Temperature | Cloud REST |
| `HLM` / `HLW` | Door Locks | `HLM01`–`HLM10`, `HLR01`, `HLW01` | Lock/Unlock, Battery Level, Offline BLE Key Export | ⚠️ Experimental (Local BLE + Cloud Sync) |
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

## Authentication & Account Guidelines

> [!IMPORTANT]
> **Account Registration Restriction**: Qubo strictly restricts account authentication to the method used during registration.
> - If you created your Qubo account using a **mobile phone number**, you must authenticate using SMS OTP (`login-phone`).
> - If you created your Qubo account using an **email and password**, you must authenticate using email (`login`).
> - Attempting to use email and password credentials on an account registered with a phone number will be rejected by the cloud.

> [!NOTE]
> **Account Linkage Model**: While an email address is strictly bound to a single account (1-to-1), a phone number can be linked to multiple accounts. `qubopy` automatically detects and unpacks multi-account responses during phone verification.

> [!WARNING]
> **Mobile App Session Revocation**: When you sign in via `qubopy`, the active session is visible in the official Qubo mobile app under **Account -> Logged In Devices** with the label `Qubopy` (or your custom `--device-name`).
> Tapping **[Logout]** next to this entry in the mobile app immediately revokes the session on Qubo servers, requiring you to re-authenticate.

---

## Quick Start

### 1. Cloud Appliance Control

```python
import asyncio
from qubopy import QuboAuth, QuboClient
from qubopy.devices import QuboPlug

async def main():
    # Authenticate via email or phone OTP
    auth = QuboAuth()
    await auth.login_with_email("<email>", "<password>")

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

### 2. Smart Door Lock Control (Cloud Gateway & Local BLE)

Qubo smart door locks support two distinct integration strategies:

#### A. Cloud Gateway Unlock (Hardware Verified)
If you have an in-home Qubo gateway device (such as a Video Doorbell Pro or Smart Camera) paired in the same home unit, you can unlock directly via the cloud gateway bridge:

```python
import asyncio
from qubopy import QuboAuth, QuboClient
from qubopy.devices import QuboLock

async def main():
    auth = QuboAuth()
    await auth.login_with_email("<email>", "<password>")

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        locks = [d for d in devices if isinstance(d, QuboLock)]

        for lock in locks:
            # Unlock via paired in-home gateway bridge
            res = await lock.unlock()
            print(f"Unlocked {lock.name}: {res}")

asyncio.run(main())
```

#### B. Local BLE Offline Credentials (Experimental)

> [!CAUTION]
> **Untested / Experimental**: The BLE lock credential extraction and GATT definitions below were derived from reverse-engineering the official mobile application. They have **not been tested or verified on physical smart lock hardware**. Testing and contributions from community members with physical locks are welcome.

Extract offline cryptographic keys for experimental local use with Home Assistant Bluetooth Proxies or ESPHome:

```python
import asyncio
from qubopy import QuboAuth, QuboClient
from qubopy.devices import QuboLock

async def main():
    auth = QuboAuth()
    await auth.login_with_email("<email>", "<password>")

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        locks = [d for d in devices if isinstance(d, QuboLock)]

        for lock in locks:
            keys = await lock.get_ble_lock_keys()
            print("=== Qubo BLE Lock Credentials (Experimental) ===")
            print(f"Device Name: {keys.device_name}")
            print(f"Bluetooth MAC: {keys.mac_address}")
            print(f"Auth Key: {keys.auth_key}")
            print(f"Offline Key: {keys.offline_key}")
            print(f"Admin PIN: {keys.admin_pass}")

asyncio.run(main())
```

---

## Command Line Interface (CLI)

`qubopy` provides a command-line interface for authenticating, testing, and inspecting device parameters:

```bash
# Authenticate using email and password (default label: Qubopy)
python -m qubopy login --email <email> --password <password>

# Authenticate with a custom device label shown in the Qubo mobile app
python -m qubopy login --email <email> --password <password> --device-name <device_label>

# Authenticate using phone number and SMS OTP (interactive prompt)
python -m qubopy login-phone --phone <phone_number> --isd +91

# Verify SMS OTP in a separate step (if not completed interactively)
python -m qubopy verify-otp --otp <otp_code>

# List all units and paired devices
python -m qubopy list-devices

# Cloud unlock smart lock via paired in-home gateway
python -m qubopy unlock --device-id <lock_uuid>

# Export local BLE credentials for smart locks (experimental)
python -m qubopy export-ble-keys --device-id <device_uuid>
```

---

## IP Camera & Media Streaming Architecture

Qubo security cameras (`HCP` / `HCO` series) and video doorbells (`HCD` series) handle streaming sessions as follows:

* **Session Exclusivity**: Streaming URLs minted by Qubo cloud are single-consumer sessions (each URL serves one active stream session).
* **Local Network Streaming**: The mobile app does not rely on open LAN RTSP ports. Instead, it negotiates direct peer-to-peer (P2P) UDP connections encrypted with AES-128-GCM over RTP.
* **Downstream Integration**: `qubopy` extracts device identifiers, unit IDs, live tokens, and streaming endpoints so that media engines (such as `go2rtc` and Home Assistant) can connect without third-party tools.

---

## Local BLE Architecture for Smart Locks

> [!CAUTION]
> **Experimental & Hardware-Unverified**: All BLE lock definitions below were reverse-engineered from application binaries. They have not been validated against physical smart locks.

Qubo Bluetooth smart locks store offline parameters in the cloud. The parameters extracted from account metadata include:

* `dmac`: Physical Bluetooth MAC address.
* `dbtauthkey`: Cryptographic session key used during GATT handshake.
* `dbtoffkey`: Cryptographic seed for computing time-based offline passcodes.
* `dadminpass`: Master PIN code.

### GATT Services and Characteristics

* **Main GATT Service**: `0000fee0-0000-1000-8000-00805f9b34fb`
* **Auth / Write Characteristic**: `0000fee1-0000-1000-8000-00805f9b34fb`
* **Notify / State Characteristic**: `0000fee2-0000-1000-8000-00805f9b34fb`

### Experimental ESPHome Configuration

The following configuration demonstrates how an ESP32 board running ESPHome can listen to the lock's state characteristic and dispatch write commands:

```yaml
# Experimental ESPHome Configuration (Untested on Physical Lock Hardware)
# Requires an ESP32 board with Bluetooth Low Energy enabled

esp32_ble_tracker:

ble_client:
  - mac_address: "XX:XX:XX:XX:XX:XX"  # Replace with exported Bluetooth MAC (dmac)
    id: qubo_lock_ble

sensor:
  # Notify/State Characteristic for Lock Status & Battery Telemetry
  - platform: ble_client
    type: characteristic
    ble_client_id: qubo_lock_ble
    id: lock_state
    name: "Qubo Lock State"
    service_uuid: "0000fee0-0000-1000-8000-00805f9b34fb"
    characteristic_uuid: "0000fee2-0000-1000-8000-00805f9b34fb"
    notify: true

button:
  # Auth/Write Characteristic for Dispatching Local Handshake Packets
  - platform: template
    name: "Qubo Unlock (Experimental)"
    on_press:
      - ble_client.ble_write:
          id: qubo_lock_ble
          service_uuid: "0000fee0-0000-1000-8000-00805f9b34fb"
          characteristic_uuid: "0000fee1-0000-1000-8000-00805f9b34fb"
          # Payload requires AES handshake using exported dbtauthkey
          value: [0x00]
```

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
