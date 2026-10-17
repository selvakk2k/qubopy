"""Table-driven test suite pinning core HTTP routes and methods against Android APK constants.

References:
- ObotApi.java (com.hero.iot.data.network.ObotApi)
- libcore-main.so strings
"""

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qubopy import QuboClient

# Pinned verified routes table
# Each row: (operation, method, path, coroutine_factory, app_constant)
ROUTE_SPECS = [
    (
        "send command",
        "PUT",
        "/unit-entity-management/api/v1/sp/9999/units/u1/entities/e1/devices/d1/command",
        lambda c: c.send_command("u1", "e1", "d1", {"cameraFunction": {"state": "enable"}}),
        "UPDATE_SHADOW_COMMAND_ATTRIBUTE",
    ),
    (
        "bulk shadows",
        "POST",
        "/unit-entity-management/api/v1/sp/9999/devices/shadow",
        lambda c: c.get_all_shadows(),
        "GET_DEVICE_SHADOW",
    ),
    (
        "device events",
        "GET",
        "/control-monitor/api/v1/sp/9999/device/d1/event",
        lambda c: c.get_device_events("u1", "d1"),
        "GET_LOCK_EVENTS_FROM_CLOUD",
    ),
    (
        "generate OTP",
        "POST",
        "/roi-manager/api/v1/sp/9999/device/d1/lock/pin/otp",
        lambda c: c.generate_lock_otp("d1"),
        "GENERATE_OTP",
    ),
    (
        "lock/battery shadow",
        "GET",
        "/unit-entity-management/api/v2/sp/9999/devices/d1/deviceshadow",
        lambda c: c.get_device_shadow_v2("d1"),
        "(v2 shadow - verified via downstream integration)",
    ),
    (
        "stop stream",
        "DELETE",
        "/stream-manager/api/v2/sp/9999/stream/unit/u1/device/d1",
        lambda c: c.stop_live_stream("u1", "d1", "sess-1"),
        "STREAM_URL",
    ),
    # UNVERIFIED routes (retained and pinned against current library behavior)
    (
        "update shadow attribute",
        "PUT",
        "/unit-entity-management/api/v1/sp/9999/units/u1/entities/e1/devices/d1/shadow/attribute",
        lambda c: c.update_shadow_attribute("u1", "e1", "d1", {"privacyMode": "disable"}),
        "UNVERIFIED: native libcore-main.so route; PUT inferred from /command",
    ),
    (
        "revoke lock otp",
        "DELETE",
        "/roi-manager/api/v1/sp/9999/device/d1/lock/pin/otp",
        lambda c: c.revoke_lock_otp("d1", otp="123456"),
        "UNVERIFIED: route not present in Android app; behavior unknown",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,expected_method,expected_path,coro_factory,app_constant",
    ROUTE_SPECS,
    ids=[r[0] for r in ROUTE_SPECS],
)
async def test_pinned_route_schemas(
    sample_client: QuboClient,
    operation: str,
    expected_method: str,
    expected_path: str,
    coro_factory: Callable[[QuboClient], Coroutine[Any, Any, Any]],
    app_constant: str,
):
    """Assert exact HTTP method and path produced by client against app constants."""
    sample_client.sp_id = "9999"
    with patch.object(sample_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {}
        await coro_factory(sample_client)

        assert mock_req.call_count == 1, f"Expected 1 call for {operation} ({app_constant})"
        called_method, called_path = mock_req.call_args[0][0], mock_req.call_args[0][1]

        assert called_method == expected_method, (
            f"Method mismatch for {operation} ({app_constant}): "
            f"expected {expected_method}, got {called_method}"
        )
        assert called_path == expected_path, (
            f"Path mismatch for {operation} ({app_constant}): "
            f"expected {expected_path}, got {called_path}"
        )

    await sample_client.close()
