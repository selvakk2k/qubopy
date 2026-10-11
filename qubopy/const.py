"""Constants and fixed definitions for qubopy."""

# Cloud REST Gateway
DEFAULT_BASE_URL: str = "https://srvcapp.platform.quboworld.com:443"

# Fixed Service Provider UUID extracted from native C++ binaries (libcore-rest.so)
DEFAULT_SP_ID: str = "d10e4bfb0153496e8e8bb955f7ebe413"

# Official Android Application Package Identifier
DEFAULT_APP_ID: str = "com.hero.iot"

# Default Device Identifier for Qubo backend session display
DEFAULT_DEVICE_ATTRIBUTE: str = "HomeAssistant_qubopy"

# Cloud Infrastructure Hosts
MQTT_BROKER_HOST: str = "mqtt.platform.quboworld.com"
MQTT_BROKER_PORT: int = 8883
STUN_SERVER_HOST: str = "stun6.platform.quboworld.com"
STUN_SERVER_PORT: int = 5349

# REST API Paths
PATH_LOGIN_EMAIL: str = "/sms/api/v1/sp/{sp}/user/login?system=CS"
PATH_LOGIN_PHONE_REQUEST: str = "/sms/api/v1/sp/{sp}/user/phone/login"
PATH_LOGIN_PHONE_VERIFY: str = "/sms/api/v1/sp/{sp}/user/phone/verify"
PATH_AUTH_REFRESH: str = "/sms/api/v1/sp/{sp}/users/{user_uuid}/auth/refresh"

# Discovery & Hierarchy Paths
PATH_GET_DEVICES: str = (
    "/unit-entity-management/api/v1/sp/{sp}/units/{unit_uuid}/entities/{entity_uuid}/devices/self"
)
PATH_GET_ALL_SHADOWS: str = "/unit-entity-management/api/v1/sp/{sp}/devices/shadow"
PATH_GET_DEVICE_SHADOW: str = (
    "/unit-entity-management/api/v1/sp/{sp}/devices/{device_uuid}/deviceshadow"
)

# Control Paths
PATH_SEND_COMMAND: str = (
    "/unit-entity-management/api/v1/sp/{sp}/units/{unit_uuid}/entities/{entity_uuid}/devices/{device_uuid}/command"
)
PATH_UPDATE_SHADOW_ATTRIBUTE: str = (
    "/unit-entity-management/api/v1/sp/{sp}/units/{unit_uuid}/entities/{entity_uuid}/devices/{device_uuid}/shadow/attribute"
)

# Media & Camera Paths
PATH_RTSP_SUPPORT: str = (
    "/unit-entity-management/api/v1/sp/{sp}/units/{unit_uuid}/devices/rtsp/support"
)
PATH_P2P_CREDENTIALS: str = (
    "/stream-manager/api/v1/sp/{sp}/unit/{unit_uuid}/devices/pp2p/credentials"
)
PATH_START_STREAM: str = (
    "/stream-manager/api/v1/sp/{sp}/stream/unit/{unit_uuid}/device/{device_uuid}"
)

# Dynamic MQTT Password Path
PATH_MQTT_CREDENTIALS: str = (
    "/unit-entity-management/api/v1/sp/{sp}/agent/device/mqtt/unit/{unit_uuid}/device/{device_uuid}"
)

# Hardware Family Model Prefixes
PREFIX_SMART_PLUG: tuple[str, ...] = ("HSP",)
PREFIX_AIR_PURIFIER: tuple[str, ...] = ("HPH",)
PREFIX_SMART_LIGHT: tuple[str, ...] = ("HLB",)
PREFIX_SMART_LOCK: tuple[str, ...] = ("HLM", "HLW", "HLR")
PREFIX_CAMERA: tuple[str, ...] = ("HCP", "HCO", "HCM", "HCI")
PREFIX_DOORBELL: tuple[str, ...] = ("HCD",)
PREFIX_SECURITY_SENSOR: tuple[str, ...] = ("HDS", "HGS", "HSA")
PREFIX_CLIMATE_SENSOR: tuple[str, ...] = ("HDT",)

# Deftun BLE Lock GATT UUIDs (P01 hardware revision)
GATT_SERVICE_LOCK: str = "0000fee0-0000-1000-8000-00805f9b34fb"
GATT_CHAR_LOCK_WRITE: str = "0000fee1-0000-1000-8000-00805f9b34fb"
GATT_CHAR_LOCK_NOTIFY: str = "0000fee2-0000-1000-8000-00805f9b34fb"
