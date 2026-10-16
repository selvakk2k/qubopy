# Qubo Python Client Library & BLE Enabler (`qubopy`)

[![PyPI version](https://img.shields.io/pypi/v/qubopy?style=flat-square)](https://pypi.org/project/qubopy/)
[![Python Version](https://img.shields.io/pypi/pyversions/qubopy?style=flat-square)](https://pypi.org/project/qubopy/)
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
    - [Controls & Diagnostics](#a-controls--diagnostics)
    - [Video Streaming Pathways (RTSPS & P2P UDP)](#b-video-streaming-pathways)
    - [Downstream go2rtc Configuration](#c-downstream-go2rtc-configuration)
  - [6. Dashcams - HCA Series (Hardware Verified)](#6-dashcams-hca-series--hardware-verified)
  - [7. Smart Door Locks - HLM / HLW Series](#7-smart-door-locks-hlm--hlw-series)
  - [8. Security & Climate Sensors - HDS / HGS / HDT Series (API Modeled)](#8-security--climate-sensors-hds--hgs--hdt-series--api-modeled--untested)
- [Command Line Interface (CLI)](#command-line-interface-cli)
  - [Session & Token Management](#session--token-management)
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
| `HCA` | Dashcams | `HCA08B`, Smart Dashcam Pro | In-Car Wi-Fi AP Credentials, Parking Mode, Speed Warning | Cloud REST | `✅ Hardware Verified` |
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

`qubopy` supports two distinct authentication pathways provided by Qubo cloud services:

### 1. Email and Password (Continuous Session with Refresh Tokens)
* **Session Lifecycle**: Continuous. Qubo returns an `accessToken` along with a valid server-issued `refreshToken`.
* **Automatic Renewal**: `qubopy` proactively refreshes the access token before expiration using `POST /auth/refresh`.
* **Target Use Case**: Recommended for permanent Home Assistant integrations and continuous 24/7 cloud polling.

### 2. Phone Number and SMS OTP (1-Hour Session / Provisioning Extractor)
* **Session Lifecycle**: Exactly 1 hour (`exp: 3600s`). Qubo cloud endpoints do not issue a `refreshToken` over the phone verification route.
* **Account Linkage & Multi-Account Selection**: A single phone number can have multiple profile accounts attached. `qubopy` detects multiple profiles and allows interactive selection or targeted selection via `--profile-index` or `--account-uuid`.
* **Target Use Case**: Designed as a **local credential and provisioning extractor**:
  * Extracting offline BLE smart lock keys via `qubopy export-ble-keys` for 100% local ESPHome/BLE control without cloud dependence.
  * Exporting in-car Wi-Fi AP SSID and passwords via `qubopy dashcam-wifi` for direct dashcam connectivity.
  * Initial device discovery and stream testing.
* **Switching to Email for 24/7 Automation**: Accounts originally created via mobile phone in the Qubo mobile app are marked with `accountType: "MOBILE"`. If you require automated 24/7 cloud polling in Home Assistant without hourly SMS re-authentication, register a separate email-based Qubo account.

> [!IMPORTANT]
> **Email Account Registration Guidelines & Constraints**:
> - **Brand-New Email Address Required**: You **cannot** use an email address that was ever previously added or linked to any mobile phone account. It must be an email address that has **never been associated with any Qubo app or account**.
> - **Phone Number Re-use is Permitted**: When registering a new email account, the Qubo app will still prompt for a phone number for SMS verification during onboarding. You **can** safely provide the exact same mobile phone number that was used for your mobile account. Login will continue to work seamlessly with your email ID and password!
> - **Account Type Separation**: Qubo strictly routes authentication based on the registration method:
>   - Accounts created via **email** authenticate using `qubopy login --email <email>` (continuous session with automatic refresh tokens).
>   - Accounts created via **phone number** authenticate using `qubopy login-phone --phone <number>` (1-hour session without refresh tokens).
>   - Attempting to use email and password credentials on an account registered with a phone number will be rejected by the cloud.

> [!WARNING]
> **Mobile App Session Revocation**: When you sign in via `qubopy`, the active session is visible in the official Qubo mobile app under **Account -> Logged In Devices** with the label `Qubopy` (or your custom `--device-name`).
> Tapping **[Logout]** next to this entry in the mobile app immediately revokes the session on Qubo servers, requiring you to re-authenticate.

> [!NOTE]
> **Operating System File Permissions**: On Linux and macOS, session cache files (`~/.qubopy_session.json`, `~/.qubopy_otp_pending.json`) and device identifiers are created with POSIX `0o600` mode (read/write by owner only). The session cache stores active authentication tokens and the associated account email address. Because Windows NTFS does not enforce POSIX permission bits, Windows users should ensure these files remain within their private user profile directory (`%USERPROFILE%`).

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
    # Switch the plug relay on or off
    await plug.turn_on()
    # await plug.turn_off()

    # Fetch latest telemetry from cloud shadow
    await plug.refresh()
    print(f"Status      : {'ON' if plug.is_on else 'OFF'}")
    print(f"Power       : {plug.power_watts} W")
    print(f"Voltage     : {plug.voltage} V")
    print(f"Current     : {plug.current} A")
    print(f"Energy Meter: {plug.energy_kwh} kWh")

    # Query historical energy consumption ('hour', 'day', 'month', 'overall')
    history = await plug.get_energy_history(period="day")
    print(f"Energy History: {history}")
```

---

### 3. Air Purifiers (HPH Series) (`⚠️ API Modeled / Untested`)

*Note: Speed controls, presets, and sensor readings are modeled from APK application metadata. Community testing with physical air purifiers is welcome.*

```python
from qubopy.devices import QuboAirPurifier

async def operate_purifier(purifier: QuboAirPurifier):
    # Power controls
    await purifier.turn_on()
    # await purifier.turn_off()

    # Set fan speed (1 to 3) and preset mode ('auto', 'sleep', 'manual')
    await purifier.set_fan_speed(2)
    await purifier.set_mode("auto")

    # Lock physical buttons on the appliance
    await purifier.set_child_lock(True)

    # Read live status and sensor values
    await purifier.refresh()
    print(f"Running     : {purifier.is_on}")
    print(f"Fan Speed   : {purifier.fan_speed}")
    print(f"Mode        : {purifier.mode}")
    print(f"Child Lock  : {purifier.is_child_lock_on}")
    print(f"PM2.5       : {purifier.pm25} ug/m3")
    print(f"Filter Life : {purifier.filter_life_percent}%")

    # Daily PM2.5 particulate history
    insights = await purifier.get_pm25_insights()
    print(f"Daily PM2.5 Insights: {insights}")
```

---

### 4. Smart Lighting (HLB Series) (`⚠️ API Modeled / Untested`)

*Note: Lighting state, dimmer, and RGB/CCT attributes are modeled from APK application metadata. Community testing with physical smart bulbs is welcome.*

```python
from qubopy.devices import QuboLight

async def operate_light(light: QuboLight):
    # Turn on with custom brightness (0-100) and RGB color tuple
    await light.turn_on(brightness=80, rgb=(255, 140, 0))

    # Tune white color temperature (accepts set_color_temp or set_color_temp_kelvin)
    await light.set_color_temp_kelvin(3000)

    # Individual property setters
    await light.set_brightness(50)
    await light.set_rgb(0, 255, 128)
    # await light.turn_off()

    # Read current state
    await light.refresh()
    print(f"Status      : {'ON' if light.is_on else 'OFF'}")
    print(f"Brightness  : {light.brightness}%")
    print(f"Color Temp  : {light.color_temp_kelvin} K")
    print(f"RGB Color   : {light.rgb_color}")
```

---

### 5. Cameras & Doorbells (HCP / HCD Series) (`✅ Hardware Verified`)

Qubo security cameras (`HCP` / `HCO` series) and video doorbells (`HCD` series) provide motorized PTZ controls, privacy shutters, deterrent sirens, AI detection telemetry, and three distinct streaming mechanisms:
1. **Cloud Wowza RTSPS**: Remote, single-consumer streaming via Qubo cloud (`camera.start_stream()`).
2. **Local Peer-to-Peer (P2P) UDP Streaming**: Low-latency local network streaming secured with AES-128-GCM encryption (`camera.initiate_p2p_call()`).
3. **Firmware RTSP Capability Query**: Diagnostic check for camera RTSP support (`camera.get_rtsp_info()`).

#### A. Controls & Diagnostics

```python
from qubopy.devices import QuboCamera

async def operate_camera(camera: QuboCamera):
    # Privacy shutter and deterrent siren controls
    await camera.set_privacy_mode(True)
    await camera.set_siren(False)

    # PTZ motor control (pan, tilt) and motion tracking for 360 models
    await camera.pan_tilt(x=0, y=-50)
    await camera.set_motion_tracking(True)

    # Night vision mode ('true', 'false', 'auto')
    await camera.set_night_mode("auto")

    # Read live status, AI detections, and network diagnostics
    await camera.refresh()
    print(f"Privacy Mode    : {camera.is_privacy_mode_on}")
    print(f"Motion Detected : {camera.is_motion_detected}")
    print(f"Person Detected : {camera.is_person_detected}")
    print(f"PTZ Position    : {camera.pan_tilt_position}")
    print(f"LAN IP Address  : {camera.lan_ip_address}")
    print(f"Wi-Fi Signal    : {camera.wifi_rssi} dBm ({camera.wifi_ssid})")

    # Fetch event timeline ('v2' for metadata, 'v3' for direct clip download links)
    events = await camera.get_events(version="v2", limit=10)
    print(f"Recent events count: {len(events)}")

    # Inspect SD card storage status and capacity
    storage = await camera.get_storage_info()
    print(f"Storage Status: {storage.get('status')}")
    print(f"Free Storage  : {camera.sd_storage_free_mb} MB / {camera.sd_storage_total_mb} MB")
```

#### B. Video Streaming Pathways

##### 1. Cloud Wowza RTSPS Streaming (`camera.start_stream()`)

Cloud Wowza RTSPS provides remote video access without requiring direct LAN reachability or open inbound ports. Each stream session is authenticated with an ephemeral token:

```python
# Mint an authenticated cloud RTSPS streaming URL ('high' or 'low')
stream_url = await camera.start_stream(quality="high")
print(f"RTSPS Stream URL: {stream_url}")
# Format: rtsps://wowza.platform.quboworld.com:443/live/<device_id>?token=<ephemeral_token>
```

> [!NOTE]
> Cloud Wowza URLs are single-consumer sessions. Opening the stream in a media player or restreaming software terminates any active stream session using the same token.

##### 2. Local Peer-to-Peer (P2P) UDP Streaming (`camera.initiate_p2p_call()`)

Qubo cameras do not expose an unauthenticated LAN RTSP port. Instead, the camera uses a direct UDP streaming protocol negotiated via the Qubo cloud signaling gateway:

* **Signaling**: The client generates a 16-byte `aesKey` and 16-byte `aesIV`, then posts a local UDP candidate (`<local_ip>:<local_port>`) to `/stream-manager/api/v2/sp/{sp}/unit/{unit_uuid}/device/{device_uuid}/p2pCall`.
* **Transport**: The camera sends raw RTP packets over UDP directly to the client's listening IP and port.
* **Payload Types**: Video uses Dynamic PT `96` (H.264 elementary stream); two-way audio uses PT `97`.
* **Decryption**: RTP payload bytes are encrypted using AES-128-GCM with the negotiated session key and IV. The 16-byte GCM authentication tag is appended to each UDP packet.
* **ICE/STUN Handshake**: An initial ICE/STUN Binding Request (magic cookie `0x2112A442`) with username `0x70` ("check B") triggers immediate media transmission from the camera.

```python
# Negotiate local P2P session directly to your media receiver (e.g. Home Assistant or go2rtc server)
session = await camera.initiate_p2p_call(
    local_ip="192.168.1.50",  # IP address of receiver
    local_port=49700,         # Listening UDP port on receiver
    quality="high",           # "high" (1080p/2K) or "low" (360p)
)

print("P2P Session Initiated:")
print(f"  Session ID  : {session['session_id']}")
print(f"  AES Key Hex : {session['aes_key_hex']}")
print(f"  AES IV Hex  : {session['aes_iv_hex']}")
print(f"  Target UDP  : {session['local_ip']}:{session['local_port']}")
print(f"  Quality     : {session['quality']}")
```

##### 3. Diagnostic RTSP Capability Query (`camera.get_rtsp_info()`)

Queries the camera's static firmware RTSP configuration endpoint:

```python
stream_info = await camera.get_rtsp_info()
if stream_info.is_supported:
    print(f"Firmware RTSP URL : {stream_info.stream_url}")
    print(f"Username          : {stream_info.username}")
```

#### C. Downstream go2rtc Configuration

`go2rtc` can consume Qubo camera feeds for rebroadcasting into Home Assistant, WebRTC, and RTSP restreaming:

```yaml
# go2rtc.yaml
streams:
  # Option A: Cloud RTSPS Stream (single-consumer session)
  qubo_camera_cloud:
    - "rtsps://wowza.platform.quboworld.com:443/live/<device_uuid>?token=<session_token>#backchannel=0"

  # Option B: Local P2P via FFmpeg Pipe (UDP receiver daemon)
  qubo_camera_local:
    - "exec:ffmpeg -protocol_whitelist file,crypto,udp,rtp -i pipe:0 -c copy -f rtsp {output}"
```

---

### 6. Dashcams (HCA Series) (`✅ Hardware Verified`)

Query in-car Wi-Fi AP credentials, parking monitoring status, and overspeed alerts directly from the cloud shadow (even while the vehicle is parked and unpowered):

```python
from qubopy.devices import QuboDashcam

# Assuming 'dashcam' is an instance of QuboDashcam from get_all_devices()
async def inspect_dashcam(dashcam: QuboDashcam):
    # Configure dashcam settings remotely via cloud shadow
    await dashcam.set_parking_monitoring(True)
    await dashcam.set_overspeed_limit(100)  # km/h
    await dashcam.set_audio_recording(True)

    # Read status, Wi-Fi credentials, and telemetry
    await dashcam.refresh()
    print(f"Dashcam Name    : {dashcam.name} ({dashcam.model})")
    print(f"Serial Number   : {dashcam.serial_number}")
    print(f"In-Car Wi-Fi AP : {dashcam.wifi_ap_ssid}")
    print(f"WPA2 Password   : {dashcam.wifi_ap_password}")
    print(f"Loop Recording  : {dashcam.is_recording}")
    print(f"SD Card Status  : {dashcam.sd_card_status}")
    print(f"Parking Mode    : {'Enabled' if dashcam.is_parking_monitoring_on else 'Disabled'}")
    print(f"Audio Recording : {'Enabled' if dashcam.is_audio_recording_on else 'Disabled'}")
    print(f"Speed Warning   : {dashcam.overspeed_limit} {dashcam.speed_unit}")
```

---

### 7. Smart Door Locks (HLM / HLW Series)

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

    # Read live real-time lock state & battery level from v2 deviceshadow
    live_state = await lock.fetch_live_lock_state()
    live_battery = await lock.fetch_live_battery()
    print(f"Live Lock State : {live_state} (is_locked: {lock.is_locked})")
    print(f"Live Battery    : {live_battery}% (cached: {lock.battery_percent}%)")

    # Generate temporary guest OTP PIN
    otp = await lock.generate_guest_otp()
    print(f"Guest PIN OTP   : {otp.get('otp')}")
```

#### Method B: Local BLE Offline Credentials (`⚠️ Experimental`)

> [!CAUTION]
> **Untested / Experimental**: The BLE lock credential extraction and GATT definitions below were derived from reverse-engineering the official mobile application. They have **not been tested or verified on physical smart lock hardware**. Testing and contributions from community members with physical locks are welcome.

> [!WARNING]
> **Cryptographic Key Security**: The extracted Bluetooth authentication key (`dbtauthkey`), offline key seed (`dbtoffkey`), and master admin passcode grant physical authorization to actuate the lock bolt. Treat these exported credentials with the same confidentiality as physical keys. Never commit exported credentials to public source control or paste them into unredacted issue reports.

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

### 8. Security & Environmental Sensors (HDS / HGS / HDT Series) (`⚠️ API Modeled / Untested`)

*Note: Security sensor alarms and environmental readings are modeled from APK application metadata. Community testing with physical sensors is welcome.*

```python
from qubopy.devices import QuboSensor

async def inspect_sensor(sensor: QuboSensor):
    await sensor.refresh()
    print(f"Sensor Name: {sensor.name} ({sensor.model})")

    # Security & Alarm Sensors (HDS Contact, HGS Gas, HSA Smoke)
    if sensor.is_contact_open is not None:
        print(f"Door / Window Open : {sensor.is_contact_open}")
    if sensor.is_gas_alarm:
        print("Gas Leak Alarm     : ACTIVE")
    if sensor.is_smoke_alarm:
        print("Smoke Alarm        : ACTIVE")

    # Climate Sensors (HDT Temperature & Humidity)
    if sensor.temperature_celsius is not None:
        print(f"Temperature        : {sensor.temperature_celsius} °C")
    if sensor.humidity_percent is not None:
        print(f"Relative Humidity  : {sensor.humidity_percent} %")

    # Sensor battery telemetry
    print(f"Battery Level      : {sensor.battery_percent}%")
```

---

## Command Line Interface (CLI)

`qubopy` provides a command-line interface for authenticating, testing, and inspecting device parameters:

```bash
# Authenticate using email and password (recommended: prompted interactively or set QUBO_PASSWORD)
python -m qubopy login --email <email>

# Authenticate with inline password (caution: leaks to shell history; not recommended on shared machines)
python -m qubopy login --email <email> --password <password>

# Authenticate with a custom device label shown in the Qubo mobile app
python -m qubopy login --email <email> --device-name <device_label>

# Authenticate using phone number and SMS OTP (interactive prompt with profile selector)
python -m qubopy login-phone --phone <phone_number> --isd +91

# Verify SMS OTP in a separate step (select profile by index or account UUID)
python -m qubopy verify-otp --otp <otp_code>
python -m qubopy verify-otp --otp <otp_code> --profile-index 1
python -m qubopy verify-otp --otp <otp_code> --account-uuid <user_uuid>

# Verify active session tokens, status, and expiration (aliases: 'session', 'dump-tokens')
python -m qubopy tokens
python -m qubopy tokens --show-secrets
python -m qubopy tokens --json

# List all units and paired devices (alias: 'devices')
python -m qubopy devices
python -m qubopy list-devices

# Mint live Wowza RTSPS stream URL for cameras (can open in VLC or go2rtc)
python -m qubopy stream
python -m qubopy stream --device-id <camera_uuid> --quality high

# Fetch in-car Wi-Fi AP credentials (SSID and WPA2 password) for dashcam
python -m qubopy dashcam-wifi

# Export offline BLE credentials (MAC, auth key, offline key) for smart locks
python -m qubopy export-ble-keys
python -m qubopy export-ble-keys --device-id <lock_uuid>

# Cloud unlock smart lock via paired in-home gateway
python -m qubopy unlock --device-id <lock_uuid>

# Enable verbose debug logging for troubleshooting (works with any command)
python -m qubopy --debug devices
python -m qubopy -v login-phone --phone <phone_number>
```

### Session & Token Management

After authenticating via `login` or `login-phone`, `qubopy` securely saves active session credentials to:
* **Windows**: `%USERPROFILE%\.qubopy_session.json`
* **Linux / macOS**: `~/.qubopy_session.json`

#### 1. Inspect Active Session State
Run `qubopy tokens` (or alias `qubopy session`) to view session type, account UUID, validity duration, and remaining minutes:
```bash
qubopy tokens
```
Output:
```text
=== Qubo Active Session Tokens ===
User UUID     : 00000000-0000-0000-0000-000000000000
Session Type  : Email (Continuous / Refreshable)
Token Status  : Active (59m 44s remaining)
Expires At    : 2026-10-12 08:25:50 UTC
Refresh Token : Present
Session File  : /home/user/.qubopy_session.json
-----------------------------------
Access Token  : eyJhbGciOiJIUzI...REDACTED
Refresh Token : eyJhbGciOi...REDACTED

Tip: Pass '--show-secrets' for unmasked tokens, or '--json' for full JSON export (masked by default).
```

#### 2. Export Raw Tokens for External Tools
To display complete unmasked tokens:
```bash
qubopy tokens --show-secrets
```

To export the raw session dictionary as clean JSON (tokens are masked by default unless `--show-secrets` is also passed):
```bash
qubopy tokens --json
qubopy tokens --json --show-secrets
```

#### 3. Direct Filesystem Access
You can also inspect or copy the raw JSON session file directly from the terminal:
```bash
# On Linux and macOS
cat ~/.qubopy_session.json

# On Windows (PowerShell)
Get-Content ~\.qubopy_session.json
```

#### 4. Reusing Stored Sessions in Python
Automation scripts do not need to re-authenticate on every execution. You can initialize `QuboAuth` and `QuboClient` directly using the stored session file:
```python
import asyncio
import json
from pathlib import Path
from qubopy import QuboAuth, QuboClient

async def main() -> None:
    # Read saved credentials
    session_path = Path.home() / ".qubopy_session.json"
    session_data = json.loads(session_path.read_text(encoding="utf-8"))

    # Initialize auth with saved tokens
    auth = QuboAuth()
    auth.set_tokens(
        access_token=session_data["accessToken"],
        refresh_token=session_data.get("refreshToken"),
        user_uuid=session_data.get("uuid", ""),
    )

    # Initialize client without re-authenticating
    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        print(f"Discovered {len(devices)} device(s)")

if __name__ == "__main__":
    asyncio.run(main())
```

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

#### Python Example: Fetching Dynamic MQTT Credentials

```python
import asyncio
from qubopy import QuboAuth, QuboClient

async def main():
    auth = QuboAuth()
    await auth.login_with_email("<email>", "<password>")

    async with QuboClient(auth) as client:
        devices = await client.get_all_devices()
        if devices:
            dev = devices[0]
            # Fetch dynamic MQTT broker credentials for the device
            mqtt_creds = await dev.get_mqtt_credentials()
            print("Dynamic MQTT Credentials:")
            print(f"  Broker Server : {mqtt_creds.get('serverUrl')}")
            print(f"  Username      : {mqtt_creds.get('username')}")
            print(f"  Password      : {mqtt_creds.get('password')}")
            print(f"  Client ID     : {mqtt_creds.get('clientId')}")

asyncio.run(main())
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

### Disclaimer
`qubopy` is an independent, open-source project and is not affiliated with, endorsed by, or sponsored by Hero Electronix Pvt. Ltd. or Qubo. All trademarks, service marks, and brand names are property of their respective owners. Use of cloud APIs is subject to Qubo's Terms of Service.

### Author & Contributors
* **Architecture & Lead Engineering**: [@selvakk2k](https://github.com/selvakk2k)
* **Code Implementation & Engineering**: **Antigravity** (Google DeepMind)
* **Code Review & Pre-Release Auditing**: **Claude** (Anthropic)

Licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
