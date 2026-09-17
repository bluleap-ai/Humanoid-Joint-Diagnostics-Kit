import importlib.util
import json
import socket
import ssl
import time
import pytest
from can_tool.client import Client
from can_tool.protocol import Frame, Packet, Kind, configuration, decode_frames
from can_tool.simulator import Simulator


@pytest.fixture
def credentials(tmp_path):
    spec = importlib.util.spec_from_file_location("provision", "tools/provision.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    directory = tmp_path / "keys"
    m.generate(directory, tmp_path / "keys.h")
    return directory


@pytest.fixture
def sim(credentials):
    device = Simulator(credentials, fragment=7).start()
    yield device
    device.close()


def test_tls_capture_and_reconnect(sim, credentials):
    with Client("127.0.0.1", credentials, sim.port) as c:
        c.configure(configuration())
        c.request(Kind.START)
        _, p = c.events.get(timeout=3)
        assert decode_frames(p)[0].session == c.session
        with pytest.raises(PermissionError):
            c.send_frame(Frame(1))
    time.sleep(0.1)
    with Client("127.0.0.1", credentials, sim.port) as c:
        info = c.request(Kind.INFO)
        assert not info["active"] and not info["capture"]


def test_tls_tx_completion(sim, credentials):
    with Client("127.0.0.1", credentials, sim.port) as c:
        with pytest.raises(PermissionError):
            c.configure(configuration(active=True))
        c.configure(configuration(active=True), allow_tx=True)
        c.request(Kind.START)
        assert c.send_frame(Frame(2, b"\x01"), 20, 2)["state"] == "accepted"
        terminal = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, p = c.events.get(timeout=1)
            if p.kind == Kind.TX_EVENT and json.loads(p.payload)["terminal"]:
                terminal = True
                break
        assert terminal


def test_missing_client_certificate_rejected(sim, credentials):
    ctx = ssl.create_default_context(cafile=str(credentials / "ca.pem"))
    hostname = json.loads((credentials / "profile.json").read_text())["hostname"]
    with socket.create_connection(("127.0.0.1", sim.port)) as raw:
        try:
            with ctx.wrap_socket(raw, server_hostname=hostname) as s:
                s.sendall(Packet(Kind.HELLO, 1).encode())
                assert s.recv(1024) == b""
        except ssl.SSLError:
            pass
    time.sleep(0.1)
    assert sim.errors


def test_host_queue_overflow_closes_connection(sim, credentials):
    c = Client("127.0.0.1", credentials, sim.port, event_capacity=1)
    c.connect()
    try:
        c.configure(configuration())
        c.request(Kind.START)
        assert c.closed.wait(3)
        assert c.pc_queue_discards == 1
    finally:
        c.close()


@pytest.mark.parametrize("iteration", range(10))
def test_cli_record_and_offline_export(sim, credentials, tmp_path, capsys, iteration):
    from can_tool.cli import run, parser
    from can_tool.recording import read_recording

    target = tmp_path / "record.jsonl"
    args = parser().parse_args(
        [
            "record",
            "--device",
            "127.0.0.1",
            "--port",
            str(sim.port),
            "--credentials",
            str(credentials),
            "--output",
            str(target),
            "--seconds",
            "0.3",
            "--include",
            "0x777",
        ]
    )
    run(args)
    events = list(read_recording(target))
    assert events[0]["data"]["synthetic"] is True
    assert any(
        e["type"] == "rx" for e in events
    )  # display filter must not affect recording
    run(
        parser().parse_args(
            ["export", str(target), "--output", str(tmp_path / "data.csv")]
        )
    )
    assert "identifier" in (tmp_path / "data.csv").read_text()


def test_wrong_server_identity_rejected(sim, credentials):
    profile = credentials / "profile.json"
    obj = json.loads(profile.read_text())
    obj["hostname"] = "wrong.local"
    profile.write_text(json.dumps(obj))
    with pytest.raises(ssl.SSLCertVerificationError):
        Client("127.0.0.1", credentials, sim.port).connect()


def test_cli_tx_record_preserves_request_identity(sim, credentials, tmp_path, capsys):
    from can_tool.cli import run, parser
    from can_tool.recording import read_recording

    target = tmp_path / "tx.jsonl"
    args = parser().parse_args(
        [
            "send",
            "--device",
            "127.0.0.1",
            "--port",
            str(sim.port),
            "--credentials",
            str(credentials),
            "--allow-tx",
            "--id",
            "0x123",
            "--data",
            "01 02",
            "--count",
            "2",
            "--interval-ms",
            "20",
            "--output",
            str(target),
        ]
    )
    run(args)
    events = list(read_recording(target))
    intent = next(e["data"] for e in events if e["type"] == "tx_request")
    completed = [
        e["data"]
        for e in events
        if e["type"] == "tx_event" and e["data"].get("terminal")
    ]
    assert len(completed) == 1 and completed[0]["request"] == intent["request"]
    assert completed[0]["completed"] == 2


def test_close_waits_for_inflight_socket_read(tmp_path):
    """A closed/reused fd must never remain inside an SSL read."""
    import threading

    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    class Socket:
        def recv(self, size):
            entered.set()
            assert release.wait(3)
            assert not closed.is_set()
            return b""

        def shutdown(self, how):
            pass

        def close(self):
            closed.set()

    client = Client("unused", tmp_path)
    client.sock = Socket()
    client.reader = threading.Thread(target=client._read)
    client.reader.start()
    assert entered.wait(3)
    closer = threading.Thread(target=client.close)
    closer.start()
    assert client.closed.wait(3)
    assert not closed.is_set()
    release.set()
    closer.join(3)
    assert not closer.is_alive() and not client.reader.is_alive()
    assert closed.is_set()
