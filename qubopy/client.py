"""Qubo asynchronous client for REST API communication and discovery."""

import json
import logging
import os
import uuid
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from qubopy.auth import QuboAuth
from qubopy.const import (
    DEFAULT_BASE_URL,
    DEFAULT_SP_ID,
    PATH_DEVICE_EVENTS,
    PATH_DEVICE_STORAGE,
    PATH_GET_ALL_SHADOWS,
    PATH_GET_DEVICE_SHADOW,
    PATH_GET_DEVICE_SHADOW_V2,
    PATH_GET_DEVICES,
    PATH_LOCK_EVENTS,
    PATH_LOCK_OTP,
    PATH_OOI_EVENTS,
    PATH_P2P_CALL,
    PATH_PLUG_ENERGY_DAY,
    PATH_PLUG_ENERGY_HOUR,
    PATH_PLUG_ENERGY_MONTH,
    PATH_PLUG_ENERGY_OVERALL,
    PATH_PURIFIER_PM25_INSIGHT,
    PATH_RTSP_SUPPORT,
    PATH_SEND_COMMAND,
    PATH_START_STREAM,
    PATH_UNIT_DEVICES,
    PATH_UNITS,
    PATH_UPDATE_SHADOW_ATTRIBUTE,
)
from qubopy.devices import QuboDevice, create_device, is_gateway_device
from qubopy.exceptions import (
    QuboAuthError,
    QuboCommandError,
    QuboConnectionError,
)
from qubopy.models import (
    DeviceModelInfo,
    DeviceShadow,
    RtspStreamInfo,
)

_LOGGER = logging.getLogger(__name__)


class QuboClient:
    """Async client interface for Qubo Cloud REST APIs."""

    def __init__(
        self,
        auth: QuboAuth,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.auth = auth
        self.base_url = auth.base_url or DEFAULT_BASE_URL
        self.sp_id = auth.sp_id or DEFAULT_SP_ID
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return active aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            self._owns_session = True
        return self._session

    async def request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry: bool = False,
    ) -> Any:
        """Execute an authenticated request against the Qubo REST gateway."""
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc:
            base_parsed = urlsplit(self.base_url)
            if (
                "@" in (parsed.netloc or "")
                or parsed.scheme != base_parsed.scheme
                or parsed.netloc != base_parsed.netloc
            ):
                raise ValueError(
                    f"Invalid request URL: target host ({parsed.netloc}) "
                    f"must match base_url ({base_parsed.netloc})"
                )
            url = path
        else:
            clean_path = path if path.startswith("/") else f"/{path}"
            url = f"{self.base_url}{clean_path}"

        headers = await self.auth.get_headers()
        session = await self._get_session()

        auth_header = headers.get("Authorization", "")
        used_token = auth_header.removeprefix("Bearer ").strip() or (
            self.auth.tokens.access_token if self.auth.tokens else None
        )

        should_refresh = False
        try:
            async with session.request(
                method, url, json=json_data, params=params, headers=headers
            ) as response:
                text = await response.text()
                if (
                    response.status == 401
                    and not retry
                    and self.auth.tokens
                    and self.auth.tokens.refresh_token
                ):
                    should_refresh = True
                elif response.status in (401, 403):
                    _LOGGER.debug(
                        "Authentication rejected response (HTTP %s): %s",
                        response.status,
                        text[:200],
                    )
                    raise QuboAuthError(
                        f"Authentication rejected by Qubo API (HTTP {response.status})"
                    )
                elif response.status not in (200, 201, 204):
                    _LOGGER.debug(
                        "API error response (HTTP %s): %s", response.status, text[:200]
                    )
                    raise QuboCommandError(
                        f"Qubo API error (HTTP {response.status}) on {method} {url}"
                    )
                elif not text or response.status == 204:
                    return {}
                else:
                    return json.loads(text)
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"HTTP connection failed: {err}") from err
        except json.JSONDecodeError as err:
            raise QuboCommandError(f"Failed to parse server response as JSON: {err}") from err

        if should_refresh:
            _LOGGER.info("Received 401 from Qubo API; attempting token refresh...")
            try:
                await self.auth.refresh_session(failed_token=used_token)
            except Exception as refresh_err:
                raise QuboAuthError(
                    f"Token refresh failed after HTTP 401: {refresh_err}"
                ) from refresh_err

            return await self.request(
                method,
                path,
                json_data=json_data,
                params=params,
                retry=True,
            )

    async def get_all_shadows(self) -> dict[str, DeviceShadow]:
        """Fetch all device shadow states in bulk."""
        path = PATH_GET_ALL_SHADOWS.format(sp=self.sp_id)
        try:
            resp = await self.request("GET", path)
        except QuboAuthError:
            raise
        except Exception as err:
            _LOGGER.warning("Could not fetch bulk shadows: %s", err)
            return {}

        shadows: dict[str, DeviceShadow] = {}
        items = resp if isinstance(resp, list) else resp.get("data", resp.get("devices", []))
        if isinstance(items, list):
            for item in items:
                dev_id = item.get("deviceUUID") or item.get("uuid") or item.get("deviceId")
                if dev_id:
                    state_obj = item.get("state", {})
                    reported = state_obj.get("reported", item.get("reported", {}))
                    desired = state_obj.get("desired", item.get("desired", {}))
                    shadows[str(dev_id)] = DeviceShadow(
                        device_uuid=str(dev_id),
                        reported=reported if isinstance(reported, dict) else {},
                        desired=desired if isinstance(desired, dict) else {},
                        timestamp=item.get("timestamp"),
                        raw=item,
                    )
        elif isinstance(resp, dict):
            # Check if resp is directly a map of {deviceId: shadow}
            for dev_id, val in resp.items():
                if isinstance(val, dict):
                    state_obj = val.get("state", {})
                    reported = state_obj.get("reported", val.get("reported", {}))
                    desired = state_obj.get("desired", val.get("desired", {}))
                    shadows[str(dev_id)] = DeviceShadow(
                        device_uuid=str(dev_id),
                        reported=reported if isinstance(reported, dict) else {},
                        desired=desired if isinstance(desired, dict) else {},
                        timestamp=val.get("timestamp"),
                        raw=val,
                    )
        return shadows

    @staticmethod
    def _parse_shadow_payload(device_uuid: str, resp: Any) -> DeviceShadow:
        """Parse raw shadow payload supporting both services array and legacy dicts."""
        if not isinstance(resp, dict):
            return DeviceShadow(device_uuid=device_uuid)

        reported: dict[str, Any] = {}
        desired: dict[str, Any] = {}

        # 1. Parse services array if present (primary Qubo IoT hardware format)
        services = resp.get("services")
        if isinstance(services, list):
            for s in services:
                if not isinstance(s, dict):
                    continue
                svc_name = s.get("service")
                raw_attrs = s.get("attributes") or {}
                svc_dict: dict[str, Any] = {}
                for k, v in raw_attrs.items():
                    val = v.get("value") if isinstance(v, dict) else v
                    if val is not None:
                        svc_dict[k] = val
                        reported[f"{svc_name}_{k}"] = val
                if svc_name:
                    reported[svc_name] = svc_dict

            # Map camera properties
            cam_func = reported.get("cameraFunction", {})
            if "state" in cam_func:
                reported["camera_enabled"] = cam_func["state"] == "enable"
                reported["privacy_mode"] = cam_func["state"] == "disable"

            night = reported.get("nightModeControl", {})
            if "nightMode" in night:
                reported["night_mode"] = night["nightMode"]

            ptz = reported.get("panTiltControl", {})
            if "horizontalVerticalPostion" in ptz:
                reported["ptz_position"] = ptz["horizontalVerticalPostion"]

            tracking = reported.get("motionTracking", {})
            if "enabled" in tracking:
                reported["motion_tracking"] = str(tracking["enabled"]).lower() in (
                    "true",
                    "enable",
                )

            wifi = reported.get("wifiSettings", {})
            if "ipAddress" in wifi:
                reported["ip_address"] = wifi["ipAddress"]
            if "signalStrength" in wifi:
                reported["signal_strength"] = wifi["signalStrength"]
            if "SSIDName" in wifi:
                reported["wifi_ssid"] = wifi["SSIDName"]

            diag = reported.get("systemDiagnosis", {})
            if "sdCardStatus" in diag:
                reported["sd_card_status"] = diag["sdCardStatus"]
            if "totalExternalStorage" in diag:
                reported["sd_total_storage"] = diag["totalExternalStorage"]
            if "availableExternalStorage" in diag:
                reported["sd_available_storage"] = diag["availableExternalStorage"]

            # Map dashcam properties
            dash_wifi = reported.get("dashcamWifiSettings", {})
            if "wifiName" in dash_wifi:
                reported["dashcam_wifi_name"] = dash_wifi["wifiName"]
            if "wifiPassword" in dash_wifi:
                reported["dashcam_wifi_password"] = dash_wifi["wifiPassword"]

            parking = reported.get("parkingConfig", {})
            if "state" in parking:
                reported["parking_mode"] = parking["state"] == "enable"

            gps = reported.get("dashcamGpsConfig", {})
            if "overSpeedLimits" in gps:
                reported["overspeed_limit"] = gps["overSpeedLimits"]
            if "speedUnit" in gps:
                reported["speed_unit"] = gps["speedUnit"]

            rec = reported.get("dashcamRecordingConfig", {})
            if "audioTrack" in rec:
                reported["audio_recording"] = rec["audioTrack"] == "enable"

        # 2. Parse legacy state dict if present
        state_obj = resp.get("state", {})
        if isinstance(state_obj, dict):
            rep = state_obj.get("reported", resp.get("reported", {}))
            des = state_obj.get("desired", resp.get("desired", {}))
            if isinstance(rep, dict):
                reported.update(rep)
            if isinstance(des, dict):
                desired.update(des)

        return DeviceShadow(
            device_uuid=device_uuid,
            reported=reported,
            desired=desired,
            timestamp=resp.get("timestamp"),
            raw=resp,
        )

    async def get_device_shadow(
        self,
        device_uuid: str,
        unit_uuid: str = "",
        entity_uuid: str = "",
    ) -> DeviceShadow:
        """Fetch real-time shadow state for an individual device."""
        path = PATH_GET_DEVICE_SHADOW.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid or "default",
            entity_uuid=entity_uuid or "default",
            device_uuid=device_uuid,
        )
        resp = await self.request("GET", path)
        return self._parse_shadow_payload(device_uuid, resp)

    async def get_device_shadow_v2(
        self,
        device_uuid: str,
        service_name: str | None = None,
        attribute_name: str | None = None,
    ) -> dict[str, Any]:
        """Fetch v2 targeted device shadow or specific service/attribute."""
        path = PATH_GET_DEVICE_SHADOW_V2.format(
            sp=self.sp_id,
            device_uuid=device_uuid,
        )
        params: dict[str, str] = {}
        if service_name:
            params["serviceName"] = service_name
        if attribute_name:
            params["attributeName"] = attribute_name
        resp = await self.request("GET", path, params=params or None)
        return resp if isinstance(resp, dict) else {"raw": resp}

    async def get_device_events(
        self,
        unit_uuid: str,
        device_uuid: str,
        version: str = "v2",
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch camera/doorbell timeline events.

        Pass version='v3' if account subscription has cloud clip download entitlements.
        """
        v_str = version.lower()
        if v_str not in ("v2", "v3"):
            raise ValueError(
                f"Unsupported device events version '{version}'. Expected 'v2' or 'v3'."
            )
        path = PATH_DEVICE_EVENTS.format(
            v=v_str,
            sp=self.sp_id,
            unit_uuid=unit_uuid,
            device_uuid=device_uuid,
        )
        params: dict[str, Any] = {"limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        resp = await self.request("GET", path, params=params)
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp.get("events") or resp.get("data") or [resp]
        return []

    async def get_ooi_events(
        self,
        unit_uuid: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch Object of Interest (OOI) camera detection events from control-monitor."""
        path = PATH_OOI_EVENTS.format(sp=self.sp_id, unit_uuid=unit_uuid)
        params: dict[str, Any] = {"limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        resp = await self.request("GET", path, params=params)
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp.get("events") or resp.get("data") or [resp]
        return []

    async def get_lock_events(
        self,
        device_uuid: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch lock operation audit events from control-monitor."""
        path = PATH_LOCK_EVENTS.format(sp=self.sp_id, device_uuid=device_uuid)
        params: dict[str, Any] = {"limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        resp = await self.request("GET", path, params=params)
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp.get("events") or resp.get("data") or [resp]
        return []

    async def generate_lock_otp(self, device_uuid: str) -> dict[str, Any]:
        """Generate a temporary one-time keypad guest PIN for a smart lock."""
        path = PATH_LOCK_OTP.format(sp=self.sp_id, device_uuid=device_uuid)
        resp = await self.request("POST", path)
        return resp if isinstance(resp, dict) else {"raw": resp}

    async def get_plug_energy_history(
        self,
        device_uuid: str,
        period: str = "day",
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Fetch historical energy metering for smart plugs (hour, day, month, overall)."""
        mapping = {
            "hour": PATH_PLUG_ENERGY_HOUR,
            "day": PATH_PLUG_ENERGY_DAY,
            "month": PATH_PLUG_ENERGY_MONTH,
            "overall": PATH_PLUG_ENERGY_OVERALL,
        }
        period_clean = period.lower()
        if period_clean not in mapping:
            supported = list(mapping.keys())
            raise ValueError(
                f"Unsupported energy history period '{period}'. Expected one of: {supported}"
            )
        path = mapping[period_clean].format(sp=self.sp_id, device_uuid=device_uuid)
        return await self.request("GET", path)

    async def get_device_storage(
        self, unit_uuid: str, device_uuid: str
    ) -> dict[str, Any]:
        """Fetch SD card capacity, status, and partition diagnostics."""
        path = PATH_DEVICE_STORAGE.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid,
            device_uuid=device_uuid,
        )
        resp = await self.request("GET", path)
        return resp if isinstance(resp, dict) else {"raw": resp}

    async def get_purifier_pm25_insights(
        self,
        unit_uuid: str,
        device_uuid: str,
    ) -> dict[str, Any]:
        """Fetch daily PM2.5 particulate history for air purifiers."""
        path = PATH_PURIFIER_PM25_INSIGHT.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid,
            device_uuid=device_uuid,
        )
        resp = await self.request("GET", path)
        return resp if isinstance(resp, dict) else {"raw": resp}

    async def get_units(self) -> list[dict[str, Any]]:
        """Fetch all physical units (homes/sites) associated with the account."""
        path = PATH_UNITS.format(sp=self.sp_id)
        try:
            resp = await self.request("GET", path)
        except QuboAuthError:
            raise
        except Exception as err:
            _LOGGER.warning("Could not fetch units: %s", err)
            return []

        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            items = resp.get("data", resp.get("units", []))
            if isinstance(items, list):
                return items
            return [resp]
        return []

    async def get_devices_for_unit(self, unit_uuid: str) -> list[dict[str, Any]]:
        """Fetch all devices registered under a specific home unit."""
        path = PATH_UNIT_DEVICES.format(sp=self.sp_id, unit_uuid=unit_uuid)
        try:
            resp = await self.request("GET", path)
        except QuboAuthError:
            raise
        except Exception as err:
            _LOGGER.warning("Could not fetch devices for unit %s: %s", unit_uuid, err)
            return []

        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            items = resp.get("data", resp.get("devices", []))
            if isinstance(items, list):
                return items
            return [resp]
        return []

    async def get_devices_for_entity(
        self, unit_uuid: str, entity_uuid: str
    ) -> list[DeviceModelInfo]:
        """Fetch device descriptors for a specific unit and entity."""
        path = PATH_GET_DEVICES.format(
            sp=self.sp_id, unit_uuid=unit_uuid, entity_uuid=entity_uuid
        )
        resp = await self.request("GET", path)
        devices: list[DeviceModelInfo] = []
        items = resp if isinstance(resp, list) else resp.get("data", resp.get("devices", []))
        if isinstance(items, list):
            for d in items:
                if isinstance(d, dict):
                    # Ensure unit and entity UUIDs are propagated
                    d.setdefault("unitUUID", unit_uuid)
                    d.setdefault("entityUUID", entity_uuid)
                    devices.append(DeviceModelInfo.model_validate(d))
        return devices

    async def get_camera_rtsp_support(
        self, unit_uuid: str, device_uuid: str
    ) -> RtspStreamInfo:
        """Query RTSP stream capability and URL for a security camera."""
        path = PATH_RTSP_SUPPORT.format(sp=self.sp_id, unit_uuid=unit_uuid)
        try:
            resp = await self.request("GET", path, params={"deviceId": device_uuid})
            is_supported = bool(resp.get("supported") or resp.get("isSupported"))
            stream_url = resp.get("rtspUrl") or resp.get("url") or resp.get("streamUrl")
            return RtspStreamInfo(
                device_uuid=device_uuid,
                is_supported=is_supported,
                stream_url=stream_url,
                auth_required=bool(resp.get("authRequired")),
                username=resp.get("username"),
                password=resp.get("password"),
            )
        except Exception as err:
            _LOGGER.debug("RTSP query not supported or failed for %s: %s", device_uuid, err)
            return RtspStreamInfo(device_uuid=device_uuid, is_supported=False)

    async def get_live_stream_url(
        self,
        unit_uuid: str,
        device_uuid: str,
        device_type: str = "ptzeCamera",
        quality: str = "high",
        user_app_id: str | None = None,
    ) -> str:
        """Mint a live single-consumer Wowza RTSPS stream URL from Qubo Cloud."""
        app_id = user_app_id or self.auth.device_id
        path = PATH_START_STREAM.format(
            sp=self.sp_id, unit_uuid=unit_uuid, device_uuid=device_uuid
        )
        params = {
            "timestamp": "NOW",
            "type": quality,
            "streamSourceCamera": "primary",
            "deviceType": device_type or "ptzeCamera",
        }
        resp = await self.request(
            "POST", path, json_data={"userAppID": app_id}, params=params
        )
        stream_url = resp.get("streamURL") or ""
        return str(stream_url)

    async def initiate_p2p_call(
        self,
        unit_uuid: str,
        device_uuid: str,
        local_ip: str,
        local_port: int = 49700,
        quality: str = "high",
        aes_key: bytes | None = None,
        aes_iv: bytes | None = None,
    ) -> dict[str, Any]:
        """Initiate a direct local P2P streaming session with a camera or doorbell (Experimental).

        Dispatches signaling offer with session keys and candidate IP:port.
        Note: Exact inbound packet payload framing and encryption format are unverified
        on physical hardware.
        """
        key = aes_key or os.urandom(16)
        iv = aes_iv or os.urandom(16)
        session_id = str(uuid.uuid4())
        quality_val = quality if quality in ("high", "low", "medium", "auto") else "high"

        offer = json.dumps([
            {
                "host": f"{local_ip}:{local_port}",
                "protocol": "UDP",
                "srflx_0": f"{local_ip}:{local_port}",
            }
        ])

        payload = {
            "aesIV": iv.hex().upper(),
            "aesKey": key.hex().upper(),
            "mediaStreams": "both",
            "mobileUUID": self.auth.tokens.user_uuid if self.auth.tokens else "",
            "offerData": offer,
            "protocols": "udp",
            "pttEnabled": "false",
            "sessionId": session_id,
            "sourceType": "live",
            "srcDeviceId": self.auth.device_id,
            "streamSourceQuality": quality_val,
        }

        path = PATH_P2P_CALL.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid,
            device_uuid=device_uuid,
        )
        resp = await self.request("POST", path, json_data=payload)
        return {
            "session_id": session_id,
            "aes_key": key,
            "aes_iv": iv,
            "aes_key_hex": key.hex().upper(),
            "aes_iv_hex": iv.hex().upper(),
            "local_ip": local_ip,
            "local_port": local_port,
            "quality": quality_val,
            "response": resp,
        }

    async def send_command(
        self,
        unit_uuid: str,
        entity_uuid: str,
        device_uuid: str,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch an operational command to a device."""
        path = PATH_SEND_COMMAND.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid or "default",
            entity_uuid=entity_uuid or "default",
            device_uuid=device_uuid,
        )
        return await self.request("POST", path, json_data=command)

    async def unlock_lock_via_gateway(
        self,
        unit_uuid: str,
        entity_uuid: str,
        gateway_uuid: str,
    ) -> dict[str, Any]:
        """Dispatch cloud unlock command to the in-home gateway device."""
        path = PATH_SEND_COMMAND.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid or "default",
            entity_uuid=entity_uuid or "default",
            device_uuid=gateway_uuid,
        )
        payload = {
            "topic": f"/control/{unit_uuid}/{gateway_uuid}/lockControl",
            "payload": {
                "devices": {
                    "deviceUUID": gateway_uuid,
                    "services": {
                        "lockControl": {
                            "commands": {
                                "lockUnlock": {
                                    "instanceId": 0,
                                    "parameters": {"control": "unlock"},
                                }
                            }
                        }
                    },
                }
            },
        }
        return await self.request("PUT", path, json_data=payload)

    async def update_shadow_attribute(
        self,
        unit_uuid: str,
        entity_uuid: str,
        device_uuid: str,
        attributes: dict[str, Any],
    ) -> dict[str, Any]:
        """Update desired shadow attribute directly."""
        path = PATH_UPDATE_SHADOW_ATTRIBUTE.format(
            sp=self.sp_id,
            unit_uuid=unit_uuid or "default",
            entity_uuid=entity_uuid or "default",
            device_uuid=device_uuid,
        )
        return await self.request("POST", path, json_data=attributes)

    async def get_all_devices(self) -> list[QuboDevice]:
        """Discover and instantiate all paired devices across the account."""
        devices: list[QuboDevice] = []
        seen_uuids: set[str] = set()

        units = await self.get_units()
        for unit in units:
            unit_uuid = unit.get("unitUUID") or unit.get("uuid") or unit.get("unitId") or ""
            raw_devs = await self.get_devices_for_unit(unit_uuid) if unit_uuid else []

            # 1. Identify any active gateway devices in this unit
            unit_gateways: list[str] = []
            for d in raw_devs:
                if isinstance(d, dict) and is_gateway_device(d):
                    gw_id = d.get("deviceUUID") or d.get("deviceId") or d.get("uuid")
                    if gw_id:
                        unit_gateways.append(str(gw_id))

            # 2. Instantiate devices, auto-associating sibling gateway to locks
            for d in raw_devs:
                if not isinstance(d, dict):
                    continue
                dev_uuid = d.get("deviceUUID") or d.get("deviceId") or d.get("uuid") or ""
                if not dev_uuid or dev_uuid in seen_uuids:
                    continue
                seen_uuids.add(dev_uuid)

                # Copy extraData and bind gateway if lock lacks one
                extra_raw = d.get("extraData")
                extra = dict(extra_raw) if isinstance(extra_raw, dict) else dict(d)
                dev_type = d.get("deviceType") or d.get("type") or ""
                dev_model = d.get("deviceModel") or d.get("model") or d.get("aModelNo") or ""
                dev_name = d.get("deviceName") or d.get("name") or f"Qubo {dev_uuid[:6]}"
                dev_type_str = dev_type.upper()
                dev_model_str = dev_model.upper()
                is_lock = "LOCK" in dev_type_str or any(
                    dev_model_str.startswith(p) for p in ("HLM", "HLW", "HLR")
                )
                if (
                    is_lock
                    and unit_gateways
                    and not extra.get("gatewayUUID")
                    and not extra.get("gatewayId")
                ):
                    if len(unit_gateways) > 1:
                        _LOGGER.info(
                            "Multiple gateways found in unit %s (%s); auto-binding lock %s "
                            "to first gateway %s",
                            unit_uuid,
                            unit_gateways,
                            dev_uuid,
                            unit_gateways[0],
                        )
                    extra["gatewayUUID"] = unit_gateways[0]

                # Parse shadow if embedded in device descriptor
                shadow_obj = None
                raw_shadow = d.get("state") or d.get("shadow") or d.get("deviceShadow")
                if isinstance(raw_shadow, dict):
                    state_obj = raw_shadow.get("state", raw_shadow)
                    reported = state_obj.get("reported", raw_shadow.get("reported", {}))
                    desired = state_obj.get("desired", raw_shadow.get("desired", {}))
                    shadow_obj = DeviceShadow(
                        device_uuid=dev_uuid,
                        reported=reported if isinstance(reported, dict) else {},
                        desired=desired if isinstance(desired, dict) else {},
                        timestamp=d.get("timestamp") or raw_shadow.get("timestamp"),
                        raw=raw_shadow,
                    )

                dev_info = DeviceModelInfo(
                    uuid=dev_uuid,
                    deviceId=dev_uuid,
                    name=dev_name,
                    model=dev_model,
                    type=dev_type,
                    unitUUID=unit_uuid or d.get("unitUUID", ""),
                    entityUUID=d.get("entityUUID", d.get("entityId", "")),
                    isOnline=bool(d.get("isOnline", d.get("online", True))),
                    extraData=extra,
                )
                devices.append(create_device(dev_info, self, shadow_obj))

        return devices

    async def close(self) -> None:
        """Close HTTP connections."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        await self.auth.close()

    async def __aenter__(self) -> "QuboClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
