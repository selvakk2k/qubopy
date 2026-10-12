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
  - [1. Authentication & Client Setup (Hardware Verified)](#1-authentication--client-setup--hardware-verified)
  - [2. Smart Plugs - HSP Series (API Modeled)](#2-smart-plugs-hsp-series--api-modeled--untested)
  - [3. Air Purifiers - HPH Series (API Modeled)](#3-air-purifiers-hph-series--api-modeled--untested)
  - [4. Smart Lighting - HLB Series (API Modeled)](#4-smart-lighting-hlb-series--api-modeled--untested)
  - [5. Cameras & Doorbells - HCP / HCD Series (Hardware Verified)](#5-cameras--doorbells-hcp--hcd-series--hardware-verified)
  - [6. Smart Door Locks - HLM / HLW Series](#6-smart-door-locks-hlm--hlw-series)
- [Command Line Interface (CLI)](#command-line-interface-cli)
- [IP Camera & Media Streaming Architecture](#ip-camera--media-streaming-architecture)
- [Cloud MQTT Broker & Real-Time Telemetry](#cloud-mqtt-broker--real-time-telemetry)
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

| Series | Category | Example Models | Functions & Sensors | Integration Mode | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | Cloud Session | N/A | Email + Password, Phone SMS OTP | Cloud REST (`/user/login?system=CS`, `/phone/verify`) | `✅ Hardware Verified` |
| `HCP` / `HCO` | Cameras | `HCP01`–`HCP19`, `HCO04`–`HCO07` | RTSP Stream Query, Privacy Mask, Siren, Motion Status | Cloud REST + Local RTSP / P2P | `✅ Hardware Verified` |
| `HCD` | Doorbells | `HCD01`, `HCD04` | Ring Event, Chime, RTSP Stream / LAN P2P | Cloud REST + Local RTSP / P2P | `✅ Hardware Verified` |
| `HLM` / `HLW` | Door Locks | `HLM01`–`HLM10`, `HLR01`, `HLW01` | Remote Unlock, Battery Level, Offline BLE Key Export | Cloud Gateway / Local BLE | Gateway: `✅ Hardware Verified`<br>BLE: `⚠️ Experimental` |
| `HSP` | Smart Plugs | `HSP01` (16A), `HSP02` (10A), `HSP10` | Switch, Voltage, Current, Active Power (W), Energy (kWh) | Cloud REST | `⚠️ API Modeled` |
| `HPH` | Air Purifiers | `HPH01`–`HPH08` (Q200 to Q1000) | Fan Speed, Auto/Sleep Presets, PM2.5, Filter Life, Child Lock | Cloud REST | `⚠️ API Modeled` |
| `HLB` | Smart Lighting | `HLB01`, `HLB10` | State, Brightness, RGB Color, White Temperature | Cloud REST | `⚠️ API Modeled` |
| `HDS` / `HGS` | Security | `HDS01` (Contact), `HGS01` (Gas), `HSA01` (Smoke) | Binary Alarms, Battery Telemetry | Cloud REST | `⚠️ API Modeled` |
| `HDT` | Climate | `HDT01` | Temperature (°C), Humidity (%) | Cloud REST | `⚠️ API Modeled` |

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

### 1. Authentication & Client Setup (`✅ Hardware Verified`)

Authenticate using either your email and password or phone SMS OTP. Developers can pass an optional `device_attribute` parameter to set the friendly device label shown in the official Qubo mobile app:

#### Method A: Email and Password Login

```python
import asyncio
from qubopy import QuboAuth, QuboClient

async def main():
    auth = QuboAuth()
    await auth.login_with_email(
        "<email>",
        "<password>",
        device_attribute="Home Assistant",  # Optional: custom label in Qubo app (default: "Qubopy")
    )

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        for dev in devices:
            print(f"- {dev.name} ({dev.model}) [{dev.device_id}]")

asyncio.run(main())
```

#### Method B: Phone SMS OTP Login

```python
import asyncio
from qubopy import QuboAuth, QuboClient

async def main():
    auth = QuboAuth()
    res = await auth.request_phone_otp(
        "<phone_number>",
        isd_code="+91",
        device_attribute="Home Assistant",
    )
    await auth.verify_phone_otp(
        "<phone_number>",
        "<otp_code>",
        session_uuid=res["uuid"],
    )

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        for dev in devices:
            print(f"- {dev.name} ({dev.model}) [{dev.device_id}]")

asyncio.run(main())
```

---

### 2. Smart Plugs (HSP Series) (`⚠️ API Modeled / Untested`)

*Note: Telemetry fields and power controls are modeled from APK application metadata. Community testing with physical smart plugs is welcome.*

```python
from qubopy.devices import QuboPlug

# Assuming 'plug' is an instance of QuboPlug from get_all_devices()
async def operate_plug(plug: QuboPlug):
    # Toggle power state (or use plug.turn_off())
    await plug.turn_on()

    # Fetch latest telemetry
    await plug.refresh()
    print(f"Status : {'ON' if plug.is_on else 'OFF'}")
    print(f"Power  : {plug.power_watts} W")
    print(f"Voltage: {plug.voltage} V")
    print(f"Current: {plug.current_amps} A")
```

---

### 3. Air Purifiers (HPH Series) (`⚠️ API Modeled / Untested`)

*Note: Speed controls, presets, and sensor readings are modeled from APK application metadata. Community testing with physical air purifiers is welcome.*

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

### 4. Smart Lighting (HLB Series) (`⚠️ API Modeled / Untested`)

*Note: Lighting state, dimmer, and RGB/CCT attributes are modeled from APK application metadata. Community testing with physical smart bulbs is welcome.*

```python
from qubopy.devices import QuboLight

async def operate_light(light: QuboLight):
    # Turn on with custom brightness and color
    await light.turn_on(brightness=80, rgb=(255, 140, 0))

    # Tune white color temperature
    await light.set_color_temp_kelvin(3000)
```

---

### 5. Cameras & Doorbells (HCP / HCD Series) (`✅ Hardware Verified`)

Query RTSP stream credentials, toggle privacy shutters, and sound deterrent sirens. Cloud RTSP URL minting and LAN P2P H.264 stream decryption are verified on physical hardware:

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
```

---

### 6. Smart Door Locks (HLM / HLW Series)

Qubo smart door locks support two distinct integration strategies:

#### Method A: Cloud Gateway Unlock (`✅ Hardware Verified`)
Actuates the lock via an in-home Qubo gateway bridge (such as a Video Doorbell Pro or Smart Camera). Verified on physical hardware with live bolt movement:

```python
from qubopy.devices import QuboLock

async def unlock_door(lock: QuboLock):
    # Check if an in-home RF/BLE gateway bridge is active
    if lock.is_gateway_accessible:
        print(f"Paired gateway ID: {lock.gateway_id}")
        result = await lock.unlock()
        print(f"Unlock result: {result}")
    else:
        print("Lock is in standalone Bluetooth mode; use local BLE key export.")
```

#### Method B: Local BLE Offline Credentials (`⚠️ Experimental`)

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

# List all units and paired devices (displays Lock (Gateway) vs Lock (BLE Only))
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

## Cloud MQTT Broker & Real-Time Telemetry

In addition to REST-based control, the Qubo ecosystem operates a cloud MQTT broker for real-time telemetry streaming and sub-second push notifications.

### 1. Broker Connection Parameters

* **Host**: `mqtt.platform.quboworld.com`
* **Port**: `8883`
* **Protocol**: TLS / SSL (`ssl://`)
* **Transport**: TCP over TLS with standard server certificate verification

### 2. Dynamic Credential Provisioning

The MQTT broker does not use static passwords. Clients provision dynamic MQTT credentials by calling the authenticated REST endpoint:

```http
GET /unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/agent/device/mqtt/unit/{unit_uuid}/device/{device_uuid}
```

The response provides the dynamic broker credentials:

```json
{
  "username": "<user_uuid>",
  "password": "<dynamic_mqtt_session_secret>",
  "clientId": "<client_or_device_uuid>",
  "serverUrl": "ssl://mqtt.platform.quboworld.com:8883"
}
```

### 3. Topic Hierarchy & Subscriptions

Once authenticated over TLS, clients subscribe to specific event streams:

| Stream Type | Topic Pattern | Description |
| :--- | :--- | :--- |
| **User Push Events** | `/users/{user_uuid}/events` | Real-time push events for doorbell presses, motion detection, and security alarms. |
| **Device Telemetry** | `units/{unit_uuid}/devices/{device_uuid}/status` | Live attribute reports including plug power (W), air purifier PM2.5, and sensor metrics. |
| **Command Channel** | `units/{unit_uuid}/devices/{device_uuid}/command` | Asynchronous command publication channel for cloud-relayed actuation. |

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
