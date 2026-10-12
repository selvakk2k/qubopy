"""Qubo asynchronous client for REST API communication and discovery."""

import json
import logging
from typing import Any

import aiohttp

from qubopy.auth import QuboAuth
from qubopy.const import (
    DEFAULT_BASE_URL,
    DEFAULT_SP_ID,
    PATH_GET_ALL_SHADOWS,
    PATH_GET_DEVICE_SHADOW,
    PATH_GET_DEVICES,
    PATH_RTSP_SUPPORT,
    PATH_SEND_COMMAND,
    PATH_UNIT_DEVICES,
    PATH_UNITS,
    PATH_UPDATE_SHADOW_ATTRIBUTE,
)
from qubopy.devices import QuboDevice, create_device
from qubopy.exceptions import (
    QuboAuthError,
    QuboCommandError,
    QuboConnectionError,
    QuboDeviceNotFoundError,
)
from qubopy.models import (
    DeviceModelInfo,
    DeviceShadow,
    Entity,
    RtspStreamInfo,
    Unit,
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
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute an authenticated request against the Qubo REST gateway."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = await self.auth.get_headers()
        session = await self._get_session()

        try:
            async with session.request(
                method, url, json=json_data, params=params, headers=headers
            ) as response:
                text = await response.text()
                if response.status in (401, 403):
                    raise QuboAuthError(
                        f"Authentication rejected by Qubo API (HTTP {response.status}): {text}"
                    )
                if response.status not in (200, 201, 204):
                    raise QuboCommandError(
                        f"Qubo API error (HTTP {response.status}) on {method} {url}: {text}"
                    )
                if not text or response.status == 204:
                    return {}
                return json.loads(text)
        except aiohttp.ClientError as err:
            raise QuboConnectionError(f"HTTP connection failed: {err}") from err
        except json.JSONDecodeError as err:
            raise QuboCommandError(f"Failed to parse server response as JSON: {err}") from err

    async def get_all_shadows(self) -> dict[str, DeviceShadow]:
        """Fetch all device shadow states in bulk."""
        path = PATH_GET_ALL_SHADOWS.format(sp=self.sp_id)
        try:
            resp = await self.request("GET", path)
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

    async def get_device_shadow(self, device_uuid: str) -> DeviceShadow:
        """Fetch real-time shadow state for an individual device."""
        path = PATH_GET_DEVICE_SHADOW.format(sp=self.sp_id, device_uuid=device_uuid)
        resp = await self.request("GET", path)
        state_obj = resp.get("state", {}) if isinstance(resp, dict) else {}
        reported = state_obj.get("reported", resp.get("reported", {}))
        desired = state_obj.get("desired", resp.get("desired", {}))
        return DeviceShadow(
            device_uuid=device_uuid,
            reported=reported if isinstance(reported, dict) else {},
            desired=desired if isinstance(desired, dict) else {},
            timestamp=resp.get("timestamp") if isinstance(resp, dict) else None,
            raw=resp if isinstance(resp, dict) else {},
        )

    async def get_units(self) -> list[dict[str, Any]]:
        """Fetch all physical units (homes/sites) associated with the account."""
        path = PATH_UNITS.format(sp=self.sp_id)
        try:
            resp = await self.request("GET", path)
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
            for d in raw_devs:
                if not isinstance(d, dict):
                    continue
                dev_uuid = d.get("deviceUUID") or d.get("deviceId") or d.get("uuid") or ""
                if not dev_uuid or dev_uuid in seen_uuids:
                    continue
                seen_uuids.add(dev_uuid)

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
                    name=d.get("deviceName", d.get("name", f"Qubo {dev_uuid[:6]}")),
                    model=d.get("deviceModel", d.get("model", "")),
                    type=d.get("deviceType", d.get("type", "")),
                    unitUUID=unit_uuid or d.get("unitUUID", ""),
                    entityUUID=d.get("entityUUID", d.get("entityId", "")),
                    isOnline=bool(d.get("isOnline", d.get("online", True))),
                    extraData=d.get("extraData", d),
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

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
