"""Pydantic data models for qubopy."""

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class TokenPayload(BaseModel):
    """Authentication token and session payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    access_token: str = Field(alias="accessToken", repr=False)
    refresh_token: str | None = Field(default=None, alias="refreshToken", repr=False)
    user_uuid: str = Field(alias="uuid")
    token_type: str = Field(default="accessToken", alias="tokenType")
    mqtt_password: str | None = Field(default=None, alias="mqttPassword", repr=False)
    expires_at: float | None = None


class Unit(BaseModel):
    """A physical home or site container."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    uuid: str
    name: str = "Home"
    entities: list[dict[str, Any]] = Field(default_factory=list)


def extract_unit_uuid(unit: Any) -> str | None:
    """Extract unit UUID from a unit dictionary or Unit model.

    Tries 'unitUUID', 'uuid', and 'unitId'. Note: these key variations are
    unit-tested against reverse-engineered schemas, but have not been
    verified against physical multi-unit responses. Users should supply
    'unit_uuid' explicitly if auto-discovery fails.
    """
    if isinstance(unit, Unit):
        return unit.uuid or None
    if isinstance(unit, dict):
        uid = unit.get("unitUUID") or unit.get("uuid") or unit.get("unitId")
        return str(uid) if uid else None
    return None


class Entity(BaseModel):
    """A room, sub-group, or hub boundary within a unit."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    uuid: str
    name: str = "Room"
    unit_uuid: str = ""
    entity_type: str = Field(default="", alias="type")
    devices: list[dict[str, Any]] = Field(default_factory=list)


class DeviceModelInfo(BaseModel):
    """Raw device descriptor returned from discovery."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    uuid: str = Field(default="", validation_alias=AliasChoices("uuid", "deviceUUID"))
    device_id: str = Field(
        default="", validation_alias=AliasChoices("deviceId", "deviceUUID", "uuid")
    )
    name: str = Field(default="Qubo Device", validation_alias=AliasChoices("name", "deviceName"))
    model: str = Field(
        default="", validation_alias=AliasChoices("model", "deviceModel", "aModelNo")
    )
    device_type: str = Field(default="", validation_alias=AliasChoices("type", "deviceType"))
    unit_uuid: str = Field(default="", validation_alias=AliasChoices("unitUUID", "unit_uuid"))
    entity_uuid: str = Field(default="", validation_alias=AliasChoices("entityUUID", "entity_uuid"))
    is_online: bool = Field(default=True, validation_alias=AliasChoices("isOnline", "online"))
    extra_data: dict[str, Any] = Field(
        default_factory=dict, validation_alias=AliasChoices("extraData", "extra_data")
    )

    @field_validator("extra_data", mode="before")
    @classmethod
    def _coerce_extra_data(cls, val: Any) -> dict[str, Any]:
        if val is None or not isinstance(val, dict):
            return {}
        return val


class DeviceShadow(BaseModel):
    """Device shadow state containing live telemetry and attributes."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    device_uuid: str = ""
    reported: dict[str, Any] = Field(default_factory=dict)
    desired: dict[str, Any] = Field(default_factory=dict)
    timestamp: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BleLockCredentials(BaseModel):
    """Local Bluetooth Low Energy cryptographic keys extracted from P01DeviceBean."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    device_uuid: str
    device_name: str
    mac_address: str = Field(description="Physical Bluetooth MAC address (dmac)")
    auth_key: str = Field(
        repr=False, description="Secret BLE handshake authentication key (dbtauthkey)"
    )
    offline_key: str = Field(repr=False, description="Offline PIN calculation seed (dbtoffkey)")
    offline_key_flag: str | None = Field(default=None, description="Offline key active flag")
    admin_pass: str | None = Field(
        default=None, repr=False, description="Master administrator passcode"
    )
    admin_flag: str | None = Field(default=None, description="Administrator active flag")
    bluetooth_name: str | None = Field(default=None, description="Advertised BLE name (dbtname)")
    battery_level: int | None = Field(default=None, description="Battery percentage (0-100)")
    is_open: bool | None = Field(default=None, description="Lock state from bean")


class RtspStreamInfo(BaseModel):
    """Camera RTSP stream capability and endpoint details."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    device_uuid: str
    is_supported: bool = False
    stream_url: str | None = Field(
        default=None, validation_alias=AliasChoices("stream_url", "rtsp_url", "rtspUrl")
    )
    auth_required: bool = False
    username: str | None = None
    password: str | None = Field(default=None, repr=False)

    @property
    def rtsp_url(self) -> str | None:
        """Alias for stream_url."""
        return self.stream_url
