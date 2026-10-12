"""Command Line Interface for qubopy."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from qubopy.auth import QuboAuth
from qubopy.client import QuboClient
from qubopy.const import DEFAULT_DEVICE_ATTRIBUTE
from qubopy.devices.camera import QuboCamera
from qubopy.devices.dashcam import QuboDashcam
from qubopy.devices.lock import QuboLock
from qubopy.exceptions import QuboError

TOKEN_FILE = Path.home() / ".qubopy_session.json"


def _save_session(tokens: dict[str, Any]) -> None:
    try:
        TOKEN_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        print(f"Session saved to {TOKEN_FILE}")
    except Exception as err:
        print(f"Warning: Could not save session file: {err}", file=sys.stderr)


def _load_session() -> dict[str, Any] | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


async def _cmd_login(args: argparse.Namespace) -> int:
    auth = QuboAuth()
    device_name = getattr(args, "device_name", DEFAULT_DEVICE_ATTRIBUTE)
    print(f"Logging in with email: {args.email} ...")
    try:
        tokens = await auth.login_with_email(
            args.email, args.password, device_attribute=device_name
        )
        print("Login successful.")
        print(f"User UUID: {tokens.user_uuid}")
        _save_session(
            {
                "accessToken": tokens.access_token,
                "refreshToken": tokens.refresh_token,
                "uuid": tokens.user_uuid,
            }
        )
        return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    finally:
        await auth.close()


SESSION_TEMP_FILE = Path.home() / ".qubopy_otp_pending.json"


async def _cmd_login_phone(args: argparse.Namespace) -> int:
    auth = QuboAuth()
    phone = args.phone
    isd = getattr(args, "isd", "+91")
    clean_isd = isd if isd.startswith("+") else f"+{isd}"
    device_name = getattr(args, "device_name", DEFAULT_DEVICE_ATTRIBUTE)
    print(f"Requesting SMS OTP for phone: {clean_isd}{phone} ...")
    try:
        resp = await auth.request_phone_otp(
            phone, clean_isd, device_attribute=device_name
        )
        session_uuid = resp.get("uuid")
        if not session_uuid:
            print(f"Error: Server response missing session uuid: {resp}", file=sys.stderr)
            return 1

        print("OTP requested successfully.")
        # Cache pending session for verify-otp fallback
        try:
            SESSION_TEMP_FILE.write_text(
                json.dumps({
                    "phone": phone,
                    "isd": clean_isd,
                    "sessionUuid": session_uuid,
                    "deviceId": auth.device_id,
                    "deviceName": device_name,
                }),
                encoding="utf-8",
            )
        except Exception:
            pass

        # If interactive terminal, prompt immediately
        if sys.stdin.isatty():
            otp = input("Enter the 6-digit OTP received on your phone: ").strip()
            if otp:
                print("Verifying OTP ...")
                tokens = await auth.verify_phone_otp(
                    phone,
                    otp,
                    isd_code=clean_isd,
                    session_uuid=session_uuid,
                    device_attribute=device_name,
                )
                print("Phone authentication successful.")
                print(f"User UUID: {tokens.user_uuid}")
                _save_session(
                    {
                        "accessToken": tokens.access_token,
                        "refreshToken": tokens.refresh_token,
                        "uuid": tokens.user_uuid,
                    }
                )
                try:
                    SESSION_TEMP_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                return 0

        print(f"Session UUID: {session_uuid}")
        print("Run 'python -m qubopy verify-otp --otp <code>' to complete login.")
        return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    finally:
        await auth.close()


async def _cmd_verify_otp(args: argparse.Namespace) -> int:
    phone = args.phone
    isd = getattr(args, "isd", "+91")
    session_uuid = getattr(args, "session_uuid", None)
    device_name = getattr(args, "device_name", None)

    # Fall back to pending session cache if phone or session_uuid not provided
    if SESSION_TEMP_FILE.exists():
        try:
            pending = json.loads(SESSION_TEMP_FILE.read_text(encoding="utf-8"))
            phone = phone or pending.get("phone")
            isd = isd or pending.get("isd", "+91")
            session_uuid = session_uuid or pending.get("sessionUuid")
            device_id = pending.get("deviceId")
            device_name = device_name or pending.get("deviceName")
        except Exception:
            pass

    device_name = device_name or DEFAULT_DEVICE_ATTRIBUTE
    auth = QuboAuth(device_id=device_id)

    if not phone:
        print("Error: Phone number is required. Provide --phone <number>", file=sys.stderr)
        return 1
    if not session_uuid:
        print("Error: Session UUID is required. Provide --session-uuid <uuid> or run login-phone first.", file=sys.stderr)
        return 1

    clean_isd = isd if isd.startswith("+") else f"+{isd}"
    print(f"Verifying OTP for phone: {clean_isd}{phone} ...")
    try:
        tokens = await auth.verify_phone_otp(
            phone,
            args.otp,
            isd_code=clean_isd,
            session_uuid=session_uuid,
            device_attribute=device_name,
        )
        print("Phone authentication successful.")
        print(f"User UUID: {tokens.user_uuid}")
        _save_session(
            {
                "accessToken": tokens.access_token,
                "refreshToken": tokens.refresh_token,
                "uuid": tokens.user_uuid,
            }
        )
        try:
            SESSION_TEMP_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    finally:
        await auth.close()


async def _get_authenticated_client(args: argparse.Namespace) -> QuboClient:
    auth = QuboAuth()
    token = getattr(args, "token", None)
    uuid = getattr(args, "user_uuid", None)

    if token and uuid:
        auth.set_tokens(access_token=token, user_uuid=uuid)
    else:
        cached = _load_session()
        if not cached or not cached.get("accessToken"):
            raise QuboError("No active session found. Please run 'qubopy login' first.")
        auth.set_tokens(
            access_token=cached["accessToken"],
            refresh_token=cached.get("refreshToken"),
            user_uuid=cached.get("uuid", ""),
        )

    return QuboClient(auth)


async def _cmd_list_devices(args: argparse.Namespace) -> int:
    try:
        client = await _get_authenticated_client(args)
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        async with client:
            print("Discovering devices...")
            devices = await client.get_all_devices()
            if not devices:
                print("No devices found in this account.")
                return 0

            print(f"\nFound {len(devices)} device(s):")
            header = f"{'Name':<25} {'Model':<12} {'Type':<18} {'Online':<8} {'Device UUID':<36}"
            print(header)
            print("-" * len(header))
            for d in devices:
                online_str = "Yes" if d.is_online else "No"
                type_str = d.__class__.__name__
                if isinstance(d, QuboLock):
                    type_str = f"Lock (Gateway)" if d.is_gateway_accessible else "Lock (BLE Only)"
                print(f"{d.name:<25} {d.model:<12} {type_str:<18} {online_str:<8} {d.device_id:<36}")
            print()
            return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


async def _cmd_export_ble_keys(args: argparse.Namespace) -> int:
    try:
        client = await _get_authenticated_client(args)
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        async with client:
            print("Fetching devices for BLE key extraction...")
            devices = await client.get_all_devices()
            locks = [d for d in devices if isinstance(d, QuboLock)]

            if args.device_id:
                locks = [l for l in locks if l.device_id == args.device_id]
                if not locks:
                    print(f"No smart lock found with ID: {args.device_id}", file=sys.stderr)
                    return 1

            if not locks:
                print("No Bluetooth smart locks (HLM/HLW series) found in account.")
                return 0

            print(f"\nExporting BLE keys for {len(locks)} lock(s):\n")
            for lock in locks:
                try:
                    keys = await lock.get_ble_lock_keys()
                    print(f"--- Lock: {keys.device_name} ({keys.device_uuid}) ---")
                    print(f"  MAC Address    : {keys.mac_address}")
                    print(f"  Auth Key (GATT): {keys.auth_key}")
                    print(f"  Offline Key    : {keys.offline_key}")
                    if keys.admin_pass:
                        print(f"  Admin Passcode : {keys.admin_pass}")
                    if keys.bluetooth_name:
                        print(f"  Bluetooth Name : {keys.bluetooth_name}")
                    if keys.battery_level is not None:
                        print(f"  Battery Level  : {keys.battery_level}%")
                    print()
                except QuboError as err:
                    print(f"  Failed to export keys for {lock.name}: {err}\n", file=sys.stderr)

            return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


async def _cmd_unlock(args: argparse.Namespace) -> int:
    auth = _create_auth_from_session(args)
    if not auth.is_authenticated:
        print("Error: No active session. Run 'qubopy login' first.", file=sys.stderr)
        return 1

    device_id = args.device_id
    gateway_id = getattr(args, "gateway_id", None)
    print(f"Unlocking device {device_id} ...")
    try:
        async with QuboClient(auth) as client:
            devices = await client.get_all_devices()
            target = next((d for d in devices if d.device_id == device_id), None)
            if not target:
                print(f"Error: Device {device_id} not found in account.", file=sys.stderr)
                return 1
            if not isinstance(target, QuboLock):
                print(f"Error: Device {device_id} ({target.name}) is not a smart lock.", file=sys.stderr)
                return 1

            res = await target.unlock(gateway_uuid=gateway_id)
            print("Unlock command sent successfully.")
            print(f"Response: {res}")
            return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


async def _cmd_stream(args: argparse.Namespace) -> int:
    try:
        client = await _get_authenticated_client(args)
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    device_id = getattr(args, "device_id", None)
    quality = getattr(args, "quality", "high") or "high"
    try:
        async with client:
            devices = await client.get_all_devices()
            target = next((d for d in devices if d.device_id == device_id), None)
            if not target:
                cameras = [d for d in devices if isinstance(d, QuboCamera)]
                if len(cameras) == 1 and not device_id:
                    target = cameras[0]
                else:
                    print(f"Error: Camera {device_id} not found in account.", file=sys.stderr)
                    return 1

            if not isinstance(target, QuboCamera):
                print(f"Error: Device {target.name} is not a camera.", file=sys.stderr)
                return 1

            print(f"Requesting live stream for {target.name} ({target.device_id}) ...")
            stream_url = await target.start_stream(quality=quality)
            print("\nLive RTSPS Stream URL:")
            print(stream_url)
            print("\nYou can open this URL directly in VLC, ffplay, go2rtc, or Home Assistant.")
            return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


async def _cmd_dashcam_wifi(args: argparse.Namespace) -> int:
    try:
        client = await _get_authenticated_client(args)
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    device_id = getattr(args, "device_id", None)
    try:
        async with client:
            devices = await client.get_all_devices()
            dashcams = [d for d in devices if isinstance(d, QuboDashcam)]
            if not dashcams:
                print("No dashcams found in this account.", file=sys.stderr)
                return 1

            target = (
                next((d for d in dashcams if d.device_id == device_id), None)
                if device_id
                else dashcams[0]
            )
            if not target:
                print(f"Error: Dashcam {device_id} not found.", file=sys.stderr)
                return 1

            print(f"Fetching in-car Wi-Fi credentials for {target.name} ...")
            await target.refresh()
            print(f"  Dashcam Name   : {target.name}")
            print(f"  Model          : {target.model}")
            print(f"  Serial Number  : {target.serial_number}")
            print(f"  In-Car Wi-Fi AP: {target.wifi_ap_ssid or 'Not set'}")
            print(f"  WPA2 Password  : {target.wifi_ap_password or 'Not set'}")
            print(
                f"  Parking Mode   : {'Enabled' if target.is_parking_monitoring_on else 'Disabled'}"
            )
            print(f"  Speed Warning  : {target.overspeed_limit or 'Off'} {target.speed_unit}")
            return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


def main() -> None:
    """CLI entry point for qubopy."""
    parser = argparse.ArgumentParser(
        prog="qubopy",
        description="Qubo Python Client Library & Local BLE Enabler CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # login
    p_login = subparsers.add_parser("login", help="Login with email and password")
    p_login.add_argument("--email", required=True, help="Qubo account email")
    p_login.add_argument("--password", required=True, help="Qubo account password")
    p_login.add_argument(
        "--device-name",
        default=DEFAULT_DEVICE_ATTRIBUTE,
        help=f"Device label shown in Qubo app (default: {DEFAULT_DEVICE_ATTRIBUTE})",
    )

    # login-phone
    p_phone = subparsers.add_parser("login-phone", help="Request SMS OTP for phone login")
    p_phone.add_argument("--phone", required=True, help="Phone number (without +91)")
    p_phone.add_argument("--isd", default="+91", help="ISD country code (default: +91)")
    p_phone.add_argument(
        "--device-name",
        default=DEFAULT_DEVICE_ATTRIBUTE,
        help=f"Device label shown in Qubo app (default: {DEFAULT_DEVICE_ATTRIBUTE})",
    )

    # verify-otp
    p_otp = subparsers.add_parser("verify-otp", help="Verify SMS OTP and complete login")
    p_otp.add_argument("--otp", required=True, help="OTP code received via SMS")
    p_otp.add_argument("--phone", help="Phone number (optional if login-phone was just run)")
    p_otp.add_argument("--isd", default="+91", help="ISD country code (default: +91)")
    p_otp.add_argument(
        "--session-uuid",
        help="Session UUID from login-phone (optional if login-phone was just run)",
    )
    p_otp.add_argument(
        "--device-name",
        default=DEFAULT_DEVICE_ATTRIBUTE,
        help=f"Device label shown in Qubo app (default: {DEFAULT_DEVICE_ATTRIBUTE})",
    )

    # list-devices
    p_list = subparsers.add_parser("list-devices", help="List all registered devices")
    p_list.add_argument("--token", help="Override JWT access token")
    p_list.add_argument("--user-uuid", help="Override User UUID")

    # export-ble-keys
    p_ble = subparsers.add_parser("export-ble-keys", help="Export offline BLE credentials for smart locks")
    p_ble.add_argument("--device-id", help="Optional specific device UUID")
    p_ble.add_argument("--token", help="Override JWT access token")
    p_ble.add_argument("--user-uuid", help="Override User UUID")

    # unlock
    p_unlock = subparsers.add_parser("unlock", help="Send cloud unlock command to a smart lock via gateway")
    p_unlock.add_argument("--device-id", required=True, help="Lock device UUID to unlock")
    p_unlock.add_argument("--gateway-id", help="Optional gateway device UUID override")
    p_unlock.add_argument("--token", help="Override JWT access token")
    p_unlock.add_argument("--user-uuid", help="Override User UUID")

    # stream
    p_stream = subparsers.add_parser("stream", help="Mint and display live RTSPS stream URL for a camera")
    p_stream.add_argument("--device-id", help="Camera device UUID (optional if only 1 camera in account)")
    p_stream.add_argument("--quality", default="high", choices=["high", "low"], help="Stream resolution/quality")
    p_stream.add_argument("--token", help="Override JWT access token")
    p_stream.add_argument("--user-uuid", help="Override User UUID")

    # dashcam-wifi
    p_dwifi = subparsers.add_parser("dashcam-wifi", help="Show in-car Wi-Fi AP credentials for dashcam")
    p_dwifi.add_argument("--device-id", help="Dashcam device UUID (optional if only 1 dashcam in account)")
    p_dwifi.add_argument("--token", help="Override JWT access token")
    p_dwifi.add_argument("--user-uuid", help="Override User UUID")

    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if args.command == "login":
            sys.exit(loop.run_until_complete(_cmd_login(args)))
        elif args.command == "login-phone":
            sys.exit(loop.run_until_complete(_cmd_login_phone(args)))
        elif args.command == "verify-otp":
            sys.exit(loop.run_until_complete(_cmd_verify_otp(args)))
        elif args.command == "list-devices":
            sys.exit(loop.run_until_complete(_cmd_list_devices(args)))
        elif args.command == "export-ble-keys":
            sys.exit(loop.run_until_complete(_cmd_export_ble_keys(args)))
        elif args.command == "unlock":
            sys.exit(loop.run_until_complete(_cmd_unlock(args)))
        elif args.command == "stream":
            sys.exit(loop.run_until_complete(_cmd_stream(args)))
        elif args.command == "dashcam-wifi":
            sys.exit(loop.run_until_complete(_cmd_dashcam_wifi(args)))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
