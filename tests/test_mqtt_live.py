"""Live Mosquitto broker integration tests for QuboMqttListener reconnect logic."""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import time
from typing import Any

import pytest
from paho.mqtt import publish

from qubopy import QuboAuth
from qubopy.models import TokenPayload
from qubopy.mqtt import QuboMqttListener

HAVE = bool(shutil.which("mosquitto") and shutil.which("mosquitto_passwd"))
if not HAVE and os.environ.get("QUBOPY_REQUIRE_MOSQUITTO"):
    raise RuntimeError("QUBOPY_REQUIRE_MOSQUITTO set but mosquitto is not installed")
pytestmark = pytest.mark.skipif(not HAVE, reason="mosquitto not installed")

TOPIC = "/monitor/unit1/dev1/svc"
EVENT = '{"devices":{"services":{"svc":{"events":{"e":{"n":1}}}}}}'


class Broker:
    """Ephemeral Mosquitto broker instance for integration testing."""

    def __init__(self, tmp_path: Any) -> None:
        self.d = tmp_path
        self.proc: subprocess.Popen[Any] | None = None
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]

        ca_path = (self.d / "ca.pem").as_posix()
        key_path = (self.d / "key.pem").as_posix()
        pw_path = (self.d / "pw").as_posix()

        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                key_path,
                "-out",
                ca_path,
                "-days",
                "2",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )

        is_root = getattr(os, "geteuid", lambda: -1)() == 0
        root = "user root\n" if is_root else ""
        conf_content = (
            f"{root}listener {self.port} 127.0.0.1\n"
            f"cafile {ca_path}\n"
            f"certfile {ca_path}\n"
            f"keyfile {key_path}\n"
            f"allow_anonymous false\n"
            f"password_file {pw_path}\n"
            f"persistence false\n"
        )
        (tmp_path / "m.conf").write_text(conf_content, encoding="utf-8")

    def set_password(self, tok: str) -> None:
        pw_path = (self.d / "pw").as_posix()
        subprocess.run(["mosquitto_passwd", "-b", "-c", pw_path, "user1", tok], check=True)

    def start(self) -> None:
        conf_path = (self.d / "m.conf").as_posix()
        self.proc = subprocess.Popen(
            ["mosquitto", "-c", conf_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("broker did not start")

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait()

    def publish(self, tok: str) -> None:
        ca_path = (self.d / "ca.pem").as_posix()
        publish.single(
            TOPIC,
            EVENT,
            hostname="127.0.0.1",
            port=self.port,
            auth={"username": "user1", "password": tok},
            tls={"ca_certs": ca_path},
        )


class StubAuth(QuboAuth):
    """Test auth stub with dynamic token control."""

    current: str = "tok1"

    def set_tokens(self, access_token: str, user_uuid: str) -> None:
        self.current = access_token
        self._tokens = TokenPayload(access_token=access_token, user_uuid=user_uuid)

    async def get_valid_access_token(self) -> str:
        return self.current


@pytest.fixture
def broker(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    b = Broker(tmp_path)
    monkeypatch.setenv("SSL_CERT_FILE", (tmp_path / "ca.pem").as_posix())
    b.set_password("tok1")
    b.start()
    yield b
    b.stop()


async def _wait_for(pred: Any, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        await asyncio.sleep(0.5)
    return False


async def _drop_and_check(broker: Broker, new_token: str) -> None:
    auth = StubAuth()
    auth.set_tokens(access_token="tok1", user_uuid="user1")
    auth.current = "tok1"
    events: list[Any] = []
    listener = QuboMqttListener(
        auth,
        unit_uuid="unit1",
        broker_host="127.0.0.1",
        broker_port=broker.port,
    )
    listener.add_event_listener(events.append)
    await listener.start()
    try:
        await asyncio.sleep(1)
        await asyncio.get_running_loop().run_in_executor(None, broker.publish, "tok1")
        assert await _wait_for(lambda: len(events) >= 1, 5)
        broker.stop()
        broker.set_password(new_token)
        auth.current = new_token
        broker.start()

        async def got_second() -> bool:
            await asyncio.get_running_loop().run_in_executor(None, broker.publish, new_token)
            return len(events) >= 2

        end = time.monotonic() + 40
        while time.monotonic() < end and len(events) < 2:
            await got_second()
            await asyncio.sleep(1)
        assert len(events) >= 2 and listener.is_running
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_reconnect_same_token(broker: Broker) -> None:
    """Verify listener successfully reconnects and receives events with unchanged token."""
    await _drop_and_check(broker, "tok1")


@pytest.mark.asyncio
async def test_reconnect_rotated_token(broker: Broker) -> None:
    """Verify listener successfully reconnects and receives events with rotated token."""
    await _drop_and_check(broker, "tok2")


@pytest.mark.asyncio
async def test_rejected_credentials_stop_listener(broker: Broker) -> None:
    """Verify listener halts cleanly without retry storms when credentials are rejected."""
    auth = StubAuth()
    auth.set_tokens(access_token="tok1", user_uuid="user1")
    auth.current = "tok1"
    fired: list[int] = []
    listener = QuboMqttListener(
        auth,
        unit_uuid="unit1",
        broker_host="127.0.0.1",
        broker_port=broker.port,
        on_auth_failure=lambda: fired.append(1),
    )
    await listener.start()
    try:
        broker.stop()
        broker.set_password("tok2")
        broker.start()  # stub keeps returning stale "tok1"
        assert await _wait_for(lambda: bool(fired), 30)
        assert len(fired) == 1 and not listener.is_running  # fired once, stopped
        await asyncio.sleep(5)
        assert len(fired) == 1  # no retry storm afterwards
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_wait_subscribed_timing(broker: Broker) -> None:
    """Verify wait_subscribed wakes event loop immediately upon SUBACK (<1.0s)."""
    auth = StubAuth()
    auth.set_tokens(access_token="tok1", user_uuid="user1")
    listener = QuboMqttListener(
        auth,
        unit_uuid="unit1",
        broker_host="127.0.0.1",
        broker_port=broker.port,
    )
    await listener.start()
    try:
        start_time = time.monotonic()
        subscribed = await listener.wait_subscribed(timeout=5.0)
        elapsed = time.monotonic() - start_time
        assert subscribed is True
        assert elapsed < 1.0, f"wait_subscribed took {elapsed:.2f}s, expected < 1.0s"
    finally:
        await listener.stop()
