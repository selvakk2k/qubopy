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
    print(f"Logging in with email: {args.email} ...")
    try:
        tokens = await auth.login_with_email(args.email, args.password)
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


async def _cmd_login_phone(args: argparse.Namespace) -> int:
    auth = QuboAuth()
    print(f"Requesting OTP for phone: {args.isd}{args.phone} ...")
    try:
        resp = await auth.request_phone_otp(args.phone, args.isd)
        print("OTP requested successfully.")
        print(f"Server response: {resp}")
        print("Run 'python -m qubopy verify-otp --phone <phone> --otp <code>' to complete login.")
        return 0
    except QuboError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    finally:
        await auth.close()


async def _cmd_verify_otp(args: argparse.Namespace) -> int:
    auth = QuboAuth()
    isd = getattr(args, "isd", "91")
    print(f"Verifying OTP for phone: {isd}{args.phone} ...")
    try:
        tokens = await auth.verify_phone_otp(args.phone, args.otp, isd_code=isd)
        print("Phone authentication successful.")
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
                print(f"{d.name:<25} {d.model:<12} {d.__class__.__name__:<18} {online_str:<8} {d.device_id:<36}")
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

    # login-phone
    p_phone = subparsers.add_parser("login-phone", help="Request SMS OTP for phone login")
    p_phone.add_argument("--phone", required=True, help="Phone number (without +91)")
    p_phone.add_argument("--isd", default="+91", help="ISD country code (default: +91)")

    # verify-otp
    p_otp = subparsers.add_parser("verify-otp", help="Verify SMS OTP and complete login")
    p_otp.add_argument("--phone", required=True, help="Phone number")
    p_otp.add_argument("--otp", required=True, help="OTP code received via SMS")
    p_otp.add_argument("--isd", default="91", help="ISD country code (default: 91)")

    # list-devices
    p_list = subparsers.add_parser("list-devices", help="List all registered devices")
    p_list.add_argument("--token", help="Override JWT access token")
    p_list.add_argument("--user-uuid", help="Override User UUID")

    # export-ble-keys
    p_ble = subparsers.add_parser("export-ble-keys", help="Export offline BLE credentials for smart locks")
    p_ble.add_argument("--device-id", help="Optional specific device UUID")
    p_ble.add_argument("--token", help="Override JWT access token")
    p_ble.add_argument("--user-uuid", help="Override User UUID")

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
    finally:
        loop.close()


if __name__ == "__main__":
    main()
