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
- [Installation & CLI Access](#installation--cli-access)
  - [1. From PyPI (Recommended)](#1-from-pypi-recommended)
  - [2. From Source or GitHub Release](#2-from-source-or-github-release)
- [Authentication & Account Guidelines](#authentication--account-guidelines)
- [Quick Start](#quick-start)
  - [1. Authentication & Client Setup](#1-authentication--client-setup)
  - [2. Smart Plugs (HSP Series)](#2-smart-plugs-hsp-series)
  - [3. Air Purifiers (HPH Series)](#3-air-purifiers-hph-series)
  - [4. Smart Lighting (HLB Series)](#4-smart-lighting-hlb-series)
  - [5. Cameras & Doorbells (HCP / HCD Series)](#5-cameras--doorbells-hcp--hcd-series)
  - [6. Smart Door Locks (HLM / HLW Series)](#6-smart-door-locks-hlm--hlw-series)
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
2. **Bluetooth Smart Locks (Dual-Path Control)**: Qubo smart door locks (`HLM`/`HLW` series) operate via Bluetooth Low Energy without an integrated Wi-Fi radio. They can be actuated remotely through an in-home Qubo gateway bridge (Video Doorbell Pro or Smart Camera) or integrated locally by extracting offline cryptographic credentials (`dbtauthkey`) for ESP32 Bluetooth Proxies.

---

## Hardware Compatibility Matrix

| Series | Category | Example Models | Functions & Sensors | Integration Mode |
| :--- | :--- | :--- | :--- | :--- |
| `HSP` | Smart Plugs | `HSP01` (16A), `HSP02` (10A), `HSP10` | Switch, Voltage, Current, Active Power (W), Energy (kWh) | Cloud REST |
| `HPH` | Air Purifiers | `HPH01`–`HPH08` (Q200 to Q1000) | Fan Speed, Auto/Sleep Presets, PM2.5, Filter Life, Child Lock | Cloud REST |
| `HLB` | Smart Lighting | `HLB01`, `HLB10` | State, Brightness, RGB Color, White Temperature | Cloud REST |
| `HLM` / `HLW` | Door Locks | `HLM01`–`HLM10`, `HLR01`, `HLW01` | Lock/Unlock, Battery Level, Offline BLE Key Export | Cloud Gateway (✅ Hardware Verified) / Local BLE (⚠️ Experimental) |
| `HCP` / `HCO` | Cameras | `HCP01`–`HCP19`, `HCO04`–`HCO07` | RTSP Stream Query, Privacy Mask, Siren, Motion Status | Cloud REST + Local RTSP |
| `HCD` | Doorbells | `HCD01`, `HCD04` | Ring Event, Chime, RTSP Stream | Cloud REST + Local RTSP |
| `HDS` / `HGS` | Security | `HDS01` (Contact), `HGS01` (Gas), `HSA01` (Smoke) | Binary Alarms, Battery Telemetry | Cloud REST |
| `HDT` | Climate | `HDT01` | Temperature (°C), Humidity (%) | Cloud REST |

---

## Installation & CLI Access

### 1. From PyPI (Recommended)

Install the library directly using `pip`:

```bash
pip install qubopy
```

Once installed, the CLI is available as both a direct executable and a Python module:

```bash
# Using the console entry point
qubopy --help

# Using the Python module runner
python -m qubopy --help
```

### 2. From Source or GitHub Release

If building from source or testing a GitHub release archive:

```bash
# Clone the repository
git clone https://github.com/selvakk2k/qubopy.git
cd qubopy

# Install in editable mode
pip install -e .

# Run the CLI
python -m qubopy --help
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

### 1. Authentication & Client Setup

Authenticate using either your email and password or phone SMS OTP, then initialize the client to discover all devices:

```python
import asyncio
from qubopy import QuboAuth, QuboClient

async def main():
    auth = QuboAuth()

    # Option A: Email login
    await auth.login_with_email("<email>", "<password>")

    # Option B: Phone SMS OTP login
    # res = await auth.request_phone_otp("<phone_number>", isd_code="+91")
    # await auth.verify_phone_otp("<phone_number>", "<otp_code>", session_uuid=res["uuid"])

    async with QuboClient(auth) as client:
        # Discover all homes and paired devices
        devices = await client.get_all_devices()
        print(f"Discovered {len(devices)} device(s):")
        for dev in devices:
            print(f"- {dev.name} ({dev.model}) [{dev.device_id}]")

asyncio.run(main())
```

---

### 2. Smart Plugs (HSP Series)

Control smart plugs and monitor active electrical metrics:

```python
from qubopy.devices import QuboPlug

# Assuming 'device' is an instance of QuboPlug from get_all_devices()
async def operate_plug(plug: QuboPlug):
    # Toggle power state
    await plug.turn_on()
    # await plug.turn_off()

    # Fetch latest telemetry
    await plug.refresh()
    print(f"Status : {'ON' if plug.is_on else 'OFF'}")
    print(f"Power  : {plug.power_watts} W")
    print(f"Voltage: {plug.voltage} V")
    print(f"Current: {plug.current_amps} A")
```

---

### 3. Air Purifiers (HPH Series)

Control fan speeds, switch preset modes, and inspect air quality:

```python
from qubopy.devices import QuboAirPurifier

async def operate_purifier(purifier: QuboAirPurifier):
    await purifier.turn_on()

    # Set fan speed (1 to 3) or preset mode ('auto', 'sleep', 'manual')
    await purifier.set_fan_speed(2)
    await purifier.set_mode("auto")

    # Read sensor values
    await purifier.refresh()
    print(f"PM2.5       : {purifier.pm25} ug/m3")
    print(f"Filter Life : {purifier.filter_life_percent}%")
```

---

### 4. Smart Lighting (HLB Series)

Control power, adjust brightness, change RGB colors, and tune color temperature:

```python
from qubopy.devices import QuboLight

async def operate_light(light: QuboLight):
    # Turn on with custom brightness and color
    await light.turn_on(brightness=80, rgb=(255, 140, 0))

    # Tune white color temperature
    await light.set_color_temp_kelvin(3000)

    # Turn off
    # await light.turn_off()
```

---

### 5. Cameras & Doorbells (HCP / HCD Series)

Query RTSP stream credentials, toggle privacy shutters, and sound deterrent sirens:

```python
from qubopy.devices import QuboCamera

async def operate_camera(camera: QuboCamera):
    # Query streaming endpoint details
    stream_info = await camera.get_rtsp_info()
    if stream_info.is_supported:
        print(f"RTSP Host : {stream_info.rtsp_url}")
        print(f"Username  : {stream_info.username}")

    # Toggle privacy shutter mode
    await camera.set_privacy_mode(True)

    # Deterrent siren control
    # await camera.set_siren(True)
```

---

### 6. Smart Door Locks (HLM / HLW Series)

Qubo smart door locks support two distinct integration strategies:

#### Method A: Cloud Gateway Unlock (Hardware Verified)
If you have an in-home Qubo gateway device (such as a Video Doorbell Pro or Smart Camera) paired in the same home unit, unlock directly through the cloud gateway bridge:

```python
from qubopy.devices import QuboLock

async def unlock_door(lock: QuboLock):
    # Unlocks via paired in-home gateway bridge
    result = await lock.unlock()
    print(f"Unlock result: {result}")
```

#### Method B: Local BLE Offline Credentials (Experimental)

> [!CAUTION]
> **Untested / Experimental**: The BLE lock credential extraction and GATT definitions below were derived from reverse-engineering the official mobile application. They have **not been tested or verified on physical smart lock hardware**. Testing and contributions from community members with physical locks are welcome.

Extract offline cryptographic keys for experimental local use with Home Assistant Bluetooth Proxies or ESPHome:

```python
from qubopy.devices import QuboLock

async def export_lock_ble(lock: QuboLock):
    keys = await lock.get_ble_lock_keys()
    print("=== Qubo BLE Lock Credentials (Experimental) ===")
    print(f"Device Name: {keys.device_name}")
    print(f"Bluetooth MAC: {keys.mac_address}")
    print(f"Auth Key: {keys.auth_key}")
    print(f"Offline Key: {keys.offline_key}")
    print(f"Admin PIN: {keys.admin_pass}")
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
