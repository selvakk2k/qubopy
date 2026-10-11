# Project Handover: Qubo Python Client Library & BLE Enabler (`qubopy`)

This document serves as the primary technical context, protocol reference, and architectural briefing for any developer or AI coding agent working on the `qubopy` repository in Antigravity IDE.

---

## Table of Contents

- [1. Executive Summary & Ecosystem Architecture](#1-executive-summary--ecosystem-architecture)
- [2. Reverse-Engineering Provenance & Native C++ Architecture](#2-reverse-engineering-provenance--native-c-architecture)
- [3. Cloud REST API Specification](#3-cloud-rest-api-specification)
  - [3.1 Host & Core Constants](#31-host--core-constants)
  - [3.2 Authentication Endpoints](#32-authentication-endpoints)
  - [3.3 Discovery & Device Hierarchy](#33-discovery--device-hierarchy)
  - [3.4 Device Control & Attribute Updates](#34-device-control--attribute-updates)
  - [3.5 Camera RTSP & Media Endpoints](#35-camera-rtsp--media-endpoints)
  - [3.6 Real-Time MQTT Broker Mechanics](#36-real-time-mqtt-broker-mechanics)
- [4. Bluetooth Low Energy Protocol & Smart Lock Driver](#4-bluetooth-low-energy-protocol--smart-lock-driver)
  - [4.1 OEM Driver Architecture](#41-oem-driver-architecture)
  - [4.2 Core Key Structure (`P01DeviceBean`)](#42-core-key-structure-p01devicebean)
  - [4.3 100% Local BLE Integration Workflow](#43-100-local-ble-integration-workflow)
  - [4.4 GATT Service & Characteristic UUIDs](#44-gatt-service--characteristic-uuids)
- [5. Complete Hardware Catalog & Model Matrix](#5-complete-hardware-catalog--model-matrix)
- [6. Architecture of the `qubopy` Library](#6-architecture-of-the-qubopy-library)
- [7. Implementation Roadmap & Milestones](#7-implementation-roadmap--milestones)
- [8. Attribution and License](#8-attribution-and-license)

---

## 1. Executive Summary & Ecosystem Architecture

* **Repository Goal**: Build a clean, asynchronous Python client library (`qubopy`) providing both cloud control for Qubo Wi-Fi appliances and local cryptographic key extraction for Qubo Bluetooth smart locks.
* **Dual Nature of the Ecosystem**:
  1. **Wi-Fi Appliances (Cloud Only)**: Qubo smart plugs, air purifiers, smart bulbs, and Wi-Fi cameras connect outbound to Qubo's AWS infrastructure over TLS MQTT and REST. They do not expose an open local HTTP/CoAP server on the local LAN. Control is handled via cloud API, exactly like the Indian-market Panasonic MirAIe AC platform.
  2. **Smart Door Locks (100% Locally Controlled via BLE)**: Qubo Bluetooth smart locks (`HLM` series) are pure Bluetooth Low Energy peripherals without Wi-Fi radios. The mobile app communicates with the lock directly over Bluetooth GATT. The cloud is only used to store and sync the cryptographic authentication keys (`dbtauthkey`) and offline keys (`dbtoffkey`).
* **The `qubo-local-control` Misconception**:
  Community projects that claim "local" Wi-Fi control operate by using local DNS overrides (Pi-hole/router) to redirect `mqtt.platform.quboworld.com:8883` to a local Mosquitto broker with self-signed TLS certificates. While this works because the firmware does not strictly enforce CA chain verification, it has severe limitations:
  - It breaks the official Qubo mobile app (the app shows devices as permanently offline).
  - It cannot work across remote locations (e.g., remote security cameras).
  - It does not support Bluetooth locks.
  - It requires invasive network modifications.
  The `qubopy` library focuses on clean, official cloud REST/MQTT communication for Wi-Fi devices, alongside direct BLE key extraction for local lock control.

---

## 2. Reverse-Engineering Provenance & Native C++ Architecture

The technical specifications in this document were extracted directly from the official Qubo Android package:
* **Package Name**: `com.hero.iot`
* **Version**: `3.3.2` (Version Code: `702`)
* **Target SDK**: Android 14 (`SDK 35`), Min SDK: `SDK 26`
* **Source Archive**: `D:\antigravity\Qubo_3.3.2_APKPure.xapk`

### Why Standard Decompilation Stalled
Previous community attempts to reverse-engineer Qubo using tools like JADX or Ghidra hit roadblocks because the application delegates all networking and authentication to native compiled C++ libraries:
* `libcore-mobile.so`: Implements `Mobile_userManager`, `DeviceManager`, `ControlMonitor`, and command dispatch.
* `libcore-rest.so`: Implements REST client routines using a customized `libcurl` and `RestClient::Connection`.
* `libjni-mobile.so` / `libjni-main.so`: JNI boundary mapping Java stubs to native C++ implementations.
* `libpaho-mqtt3as.so` / `libpaho-mqttpp3.so`: Eclipse Paho MQTT C/C++ client over TLS.
* `libdevice-commons.so`: Core schema declaration engine and shadow state serialization.

Standard Java decompilers only surface empty native declarations:
```java
public native boolean userEmailLogin(UserDto userDto);
```

By disassembling the ARM64 binaries and tracing symbol tables, we verified that:
* **There is no asymmetric payload encryption or custom hashing on passwords.**
* The login payload is standard JSON sent over HTTPS.
* The fixed Service Provider ID (`sp`) constant embedded across all native libraries is:
  ```text
  d10e4bfb0153496e8e8bb955f7ebe413
  ```

---

## 3. Cloud REST API Specification

### 3.1 Host & Core Constants

* **Primary Base URL**: `https://srvcapp.platform.quboworld.com:443`
* **MQTT Broker Host**: `mqtt.platform.quboworld.com:8883` (Port 8883, TLS)
* **STUN/TURN Host**: `stun6.platform.quboworld.com:5349`
* **Fixed Service Provider ID (`sp`)**: `d10e4bfb0153496e8e8bb955f7ebe413`

### 3.2 Authentication Endpoints

#### A. Email & Password Login
* **Method**: `POST`
* **URL**: `https://srvcapp.platform.quboworld.com:443/sms/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/user/emailprofile/login`
* **Headers**:
  ```http
  Content-Type: application/json
  ```
* **Payload**:
  ```json
  {
    "email": "user@example.com",
    "password": "plain_text_password"
  }
  ```
* **Response**: Returns JSON containing:
  * `accessToken`: JWT bearer token.
  * `refreshToken`: Long-lived token for session renewal.
  * `uuid`: The user's account UUID.
  * Linked `units` (homes/sites).

#### B. Phone & OTP Login (Alternative)
* **Request OTP**:
  - `POST /sms/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/user/phone/login`
  - Body: `{"phone": "98XXXXXXXX", "isdCode": "+91"}`
* **Verify OTP**:
  - `POST /sms/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/user/phone/verify`
  - Body: `{"phone": "98XXXXXXXX", "otp": "1234"}`

#### C. Session Refresh
* **Method**: `POST`
* **URL**: `https://srvcapp.platform.quboworld.com:443/sms/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/users/{user_uuid}/auth/refresh`
* **Headers**:
  ```http
  Content-Type: application/json
  Authorization: Bearer <accessToken>
  refreshToken: <refreshToken>
  ```

#### D. Standard Authenticated Headers
Every subsequent API request must provide:
```http
Content-Type: application/json
Authorization: Bearer <accessToken>
Token-Type: accessToken
User-UUID: <user_uuid>
Subscriber-Key: <accessToken>
```

---

### 3.3 Discovery & Device Hierarchy

Qubo organizes homes into a three-tier hierarchy:
1. **Unit (`unitUUID`)**: Represents a physical location (home or apartment).
2. **Entity (`entityUUID`) / Gateway**: Represents a hub or physical room boundary.
3. **Device (`deviceUUID`)**: The physical appliance.

#### Enumerate Devices
* **Method**: `GET`
* **URL**: `https://srvcapp.platform.quboworld.com:443/unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/units/{unitUUID}/entities/{entityUUID}/devices/self`

#### Fetch All Device Shadows (Current State)
* **Method**: `GET`
* **URL**: `https://srvcapp.platform.quboworld.com:443/unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/devices/shadow`

#### Fetch Single Device Shadow
* **Method**: `GET`
* **URL**: `https://srvcapp.platform.quboworld.com:443/unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/devices/{deviceUUID}/deviceshadow`

---

### 3.4 Device Control & Attribute Updates

#### A. Command Dispatch
* **Method**: `POST`
* **URL**: `https://srvcapp.platform.quboworld.com:443/unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/units/{unitUUID}/entities/{entityUUID}/devices/{deviceUUID}/command`

#### B. Direct Shadow Attribute Update
* **Method**: `POST`
* **URL**: `https://srvcapp.platform.quboworld.com:443/unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/units/{unitUUID}/entities/{entityUUID}/devices/{deviceUUID}/shadow/attribute`

---

### 3.5 Camera RTSP & Media Endpoints

* **Query Local RTSP Support & URL**:
  - `GET /unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/units/{unitUUID}/devices/rtsp/support`
  - Returns whether RTSP streaming can be activated directly for a given camera (`HCP`/`HCO` series).
* **Remote P2P / WebRTC Credentials**:
  - `GET /stream-manager/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/unit/{unitUUID}/devices/pp2p/credentials`
* **Initialize Remote Stream**:
  - `POST /stream-manager/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/stream/unit/{unitUUID}/device/{deviceUUID}`

---

### 3.6 Real-Time MQTT Broker Mechanics

* **Broker**: `mqtt.platform.quboworld.com:8883` (TLS)
* **Fetch Dynamic MQTT Password**:
  - `GET /unit-entity-management/api/v1/sp/d10e4bfb0153496e8e8bb955f7ebe413/agent/device/mqtt/unit/{unitUUID}/device/{deviceUUID}`
* **Topic Conventions**:
  - Outgoing commands: `units/{unitUUID}/devices/{deviceUUID}/command`
  - Incoming telemetry: `units/{unitUUID}/devices/{deviceUUID}/status`
  - Heartbeat monitor: `/monitor/{unitUUID}/{deviceUUID}/heartbeat`
  - User event stream: subscribed per user UUID.

---

## 4. Bluetooth Low Energy Protocol & Smart Lock Driver

### 4.1 OEM Driver Architecture

Qubo Bluetooth smart locks are manufactured by Deftun (hardware revision `P01`). The mobile app controls them through:
* Java package: `com.hero.deftunlocklib`
* Synchronization service: `com.hero.iot.services.DeftunLockSyncService`

### 4.2 Core Key Structure (`P01DeviceBean`)

Inside `com.hero.deftunlocklib.bean.P01DeviceBean`, the following fields govern local BLE security:

```java
public class P01DeviceBean {
    public String dmac;           // Physical Bluetooth MAC address
    public String dbtauthkey;     // Secret BLE Authentication Key
    public String dbtoffkey;      // Offline PIN calculation key
    public String dbtoffkeyflag;  // Offline key active flag
    public String dadminpass;     // Administrator password
    public String dadminflag;     // Administrator flag
    public String dbtname;        // Advertised Bluetooth name
    public int dpower;            // Battery percentage (0-100)
    public boolean isOpen;        // Current lock/unlock status
    public boolean isConnect;     // Live connection state
}
```

### 4.3 100% Local BLE Integration Workflow

1. The user logs in via `qubopy` using their Qubo account credentials.
2. `qubopy` queries the lock record from the cloud and exports:
   - `dmac`: Bluetooth MAC.
   - `dbtauthkey`: Cryptographic auth handshake key.
   - `dbtoffkey`: Offline passcode seed.
   - `dadminpass`: Admin PIN.
3. The developer or user configures a local BLE client (Home Assistant Bluetooth integration or ESPHome BLE Proxy):
   - The ESP32 scans for `dmac`.
   - Performs GATT connection and exchanges `dbtauthkey`.
   - Sends the unlock GATT characteristic payload locally without any internet dependency.

### 4.4 GATT Service & Characteristic UUIDs

The `deftunlocklib` binary declares the following primary GATT service UUIDs:
* Main Service: `0000fee0-0000-1000-8000-00805f9b34fb`
* Auth / Write Characteristic: `0000fee1-0000-1000-8000-00805f9b34fb`
* Notify / State Characteristic: `0000fee2-0000-1000-8000-00805f9b34fb`
* Vendor Auxiliary Services: `0000a00a`, `0000b002`, `0000b003`, `0000ff00`, `9A04F079-9840-4286-AB92-E65BE0885F95`

---

## 5. Complete Hardware Catalog & Model Matrix

The APK manifest (`assets/supportedDevice.json`) supports the following model families:

| Prefix | Family | Product Examples | Key Functions & Sensors |
| :--- | :--- | :--- | :--- |
| `HSP` | Smart Plugs | `HSP01` (16A), `HSP02` (10A), `HSP10` | Switch, Voltage, Current, Active Power (W), Daily/Monthly Energy (kWh) |
| `HPH` | Air Purifiers | `HPH01`–`HPH08` (Q200, Q300, Q400, Q450, Q600, Q1000) | Fan Speed, Preset Modes (Auto/Sleep), PM2.5, Filter Life Hours, Child Lock |
| `HLB` | Smart Lighting | `HLB01`, `HLB10` | Brightness, RGB Color, White Temperature, Scene Presets |
| `HLM` / `HLW` | Door Locks | `HLM01`–`HLM10`, `HLR01`, `HLW01` | Lock/Unlock, Local BLE Key Extraction, Battery Level, OTP Passcode Generator |
| `HCP` / `HCO` | IP Cameras | `HCP01`–`HCP19`, `HCO04`–`HCO07`, `HCM01`, `HCI01` | Motion Detect, Person Detect, Privacy Mask, Siren Switch, RTSP Stream Query |
| `HCD` | Doorbells | `HCD01`, `HCD04` (Video Doorbell Pro) | Doorbell Ring Sensor, Chime Control, RTSP Stream, BLE Hub Proxy |
| `HDS` / `HGS` | Security Sensors | `HDS01` (Door/Window), `HGS01` (Gas Leak), `HSA01` (Smoke) | Contact Binary Sensor, Gas Leak Alarm, Smoke Alarm |
| `HDT` | Climate Sensors | `HDT01` | Temperature (°C), Humidity (%) |

---

## 6. Architecture of the `qubopy` Library

The library should be organized as follows:

```text
qubopy/
├── pyproject.toml
├── README.md
├── qubopy/
│   ├── __init__.py          # Version, main client export
│   ├── __main__.py          # CLI entry point
│   ├── auth.py              # QuboAuth: Login, OTP, JWT refresh
│   ├── client.py            # QuboClient: Discovery, REST dispatcher
│   ├── const.py             # Base URLs, sp UUID, headers
│   ├── exceptions.py        # QuboAuthError, QuboConnectionError, etc.
│   ├── models.py            # Pydantic schemas for Unit, Entity, Device, Shadow
│   └── devices/
│       ├── __init__.py      # Device factory
│       ├── base.py          # QuboDevice base class
│       ├── plug.py          # QuboPlug (HSP)
│       ├── purifier.py      # QuboAirPurifier (HPH)
│       ├── light.py         # QuboLight (HLB)
│       ├── lock.py          # QuboLock (HLM, BLE key export)
│       ├── camera.py        # QuboCamera (HCP, RTSP query)
│       └── sensor.py        # QuboSensor (HDS, HGS, HDT)
```

---

## 7. Implementation Roadmap & Milestones

1. **Phase 1: Project Scaffolding & Packaging**
   - Configure `pyproject.toml` with `aiohttp` and `pydantic`.
   - Establish GitHub actions for linting (`ruff`) and testing (`pytest`).
2. **Phase 2: Authentication Engine (`auth.py`)**
   - Implement `email_login(email, password)`.
   - Implement `phone_login(phone, isd)` and `phone_verify(phone, otp)`.
   - Implement proactive token expiration tracking and `refresh_token()`.
3. **Phase 3: Device Discovery & Models (`client.py`, `models.py`)**
   - Implement `get_units()`, `get_entities()`, and `get_devices()`.
   - Implement device shadow polling.
4. **Phase 4: Device Control & BLE Extraction**
   - Implement command payloads for plugs, lights, purifiers, and cameras.
   - Implement `get_ble_lock_keys(device_uuid)` extracting `P01DeviceBean` values.
5. **Phase 5: CLI Utility (`__main__.py`)**
   - CLI commands: `qubopy login`, `qubopy list-devices`, `qubopy export-ble-keys`.

---

## 8. Attribution and License

* **Project**: Qubo Python Client Library & BLE Enabler (`qubopy`)
* **License**: MIT License
* **Attribution**: Based on protocol discovery and reverse engineering of the Qubo Android platform (`com.hero.iot`). Designed for open interoperability with Home Assistant, ESPHome, and open-source smart home software.
