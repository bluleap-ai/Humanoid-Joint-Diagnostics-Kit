"""Synthetic TLS device for host integration tests. Never accesses a CAN interface."""

import argparse
from collections import deque
import secrets
import socket
import ssl
import threading
import time
from pathlib import Path
import struct
from .protocol import (
    Kind,
    Frame,
    Packet,
    Parser,
    CONFIG,
    FRAME,
    TX_PREFIX,
    FD,
    configuration,
    json_payload,
)


class SimState:
    def __init__(self, capacity=16):
        self.session = secrets.randbits(64) or 1
        self.capacity = capacity
        self.frames = deque()
        self.sequence = 0
        self.drops = 0
        self.discards = 0
        self.enqueued = 0
        self.highwater = 0
        self.owner = None
        self.active = False
        self.running = False
        self.fd = False
        self.pending = None
        self.last_id = 0
        self.last_packet = None
        self.last_reply = None
        self.lease = 0
        self.executions = 0

    def connect(self, owner):
        if self.owner is not None:
            raise PermissionError("one control owner")
        self.owner = owner
        self.last_id = 0
        self.last_packet = None

    def disconnect(self, owner):
        if owner == self.owner:
            self.active = self.running = False
            self.pending = None
            self.owner = None
            self.discards += len(self.frames)
            self.frames.clear()

    def receive(self, data=b"\x00", flags=0):
        if not self.running:
            return
        self.sequence += 1
        frame = Frame(
            0x100,
            data,
            flags,
            sequence=self.sequence,
            timestamp_us=time.monotonic_ns() // 1000,
            session=self.session,
        )
        if len(self.frames) >= self.capacity:
            self.drops += 1
        else:
            self.frames.append(frame)
            self.enqueued += 1
            self.highwater = max(self.highwater, len(self.frames))

    def info(self):
        return {
            "ok": True,
            "synthetic": True,
            "session": self.session,
            "active": self.active,
            "capture": self.running,
            "fd": self.fd,
            "received": self.sequence,
            "enqueued": self.enqueued,
            "queue_drops": self.drops,
            "transport_discards": self.discards,
            "queue_highwater": self.highwater,
            "hardware_rx_losses": None,
            "timestamp_method": "synthetic_host_monotonic_us",
            "hardware_filters": None,
        }

    def command(self, owner, packet):
        if owner != self.owner:
            return {"ok": False, "error": "not owner"}
        if packet.request <= self.last_id:
            return (
                self.last_reply
                if packet == self.last_packet
                else {"ok": False, "error": "stale request"}
            )
        self.last_id = packet.request
        self.last_packet = packet
        self.lease = time.monotonic() + 3
        try:
            if packet.kind != Kind.HELLO and packet.session != self.session:
                raise ValueError("session mismatch")
            if packet.kind == Kind.HELLO:
                if packet.session or packet.payload:
                    raise ValueError("invalid hello")
                result = self.info()
            elif packet.kind in (Kind.PING, Kind.INFO):
                result = self.info()
            elif packet.kind == Kind.CONFIGURE:
                fd, active, rate, sp, dr, dsp = CONFIG.unpack(packet.payload)
                configuration(fd, active, rate, sp, dr, dsp)
                self.running = False
                self.pending = None
                self.fd = bool(fd)
                self.active = bool(active)
                result = self.info()
            elif packet.kind == Kind.START:
                self.running = True
                result = {"ok": True}
            elif packet.kind in (Kind.STOP, Kind.CANCEL):
                self.running = self.active = False
                self.pending = None
                result = {"ok": True}
            elif packet.kind == Kind.TX:
                if not self.active or not self.running:
                    raise ValueError("active mode required")
                if self.pending:
                    raise ValueError("schedule busy")
                interval, count = TX_PREFIX.unpack_from(packet.payload)
                identifier, flags, dlc, length, reserved = FRAME.unpack_from(
                    packet.payload, 8
                )
                if reserved or length != len(packet.payload) - 16:
                    raise ValueError("bad TX length")
                frame = Frame(identifier, packet.payload[16:], flags, dlc)
                frame.tx_wire(interval, count)
                if flags & FD and not self.fd:
                    raise ValueError("FD not enabled")
                self.executions += 1
                self.pending = [packet.request, count, interval, 0, time.monotonic()]
                result = {"ok": True, "request": packet.request, "state": "accepted"}
            else:
                raise ValueError("not supported by simulator")
        except (ValueError, struct.error) as exc:
            result = {"ok": False, "error": str(exc)}
        self.last_reply = result
        return result

    def tick(self):
        now = time.monotonic()
        if self.owner and now > self.lease:
            self.disconnect(self.owner)
            return None
        if self.pending and now >= self.pending[4]:
            request, remaining, interval, completed, _ = self.pending
            remaining -= 1
            completed += 1
            self.pending = (
                [request, remaining, interval, completed, now + interval / 1000]
                if remaining
                else None
            )
            return {
                "request": request,
                "state": "completed",
                "completed": completed,
                "terminal": remaining == 0,
                "synthetic": True,
            }


class Simulator:
    def __init__(self, credentials, port=0, fragment=0):
        self.credentials = Path(credentials)
        self.fragment = fragment
        self.state = SimState()
        self.closed = threading.Event()
        self.errors = []
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", port))
        self.listener.listen(2)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(
            self.credentials / "server.pem", self.credentials / "server.key"
        )
        self.context.load_verify_locations(self.credentials / "ca.pem")
        self.context.verify_mode = ssl.CERT_REQUIRED
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.closed.set()
        self.thread.join(3)
        self.listener.close()

    def _send(self, sock, p):
        encoded = p.encode()
        n = self.fragment or len(encoded)
        for i in range(0, len(encoded), n):
            sock.sendall(encoded[i : i + n])

    def run(self):
        while not self.closed.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            owner = object()
            try:
                raw.settimeout(1)
                with self.context.wrap_socket(raw, server_side=True) as conn:
                    conn.settimeout(0.03)
                    parser = Parser()
                    self.state.connect(owner)
                    self.state.lease = time.monotonic() + 3
                    next_frame = 0
                    hello = False
                    while not self.closed.is_set():
                        try:
                            data = conn.recv(4096)
                            if not data:
                                break
                            for packet in parser.feed(data):
                                if not hello and packet.kind != Kind.HELLO:
                                    raise ValueError("hello required")
                                response = self.state.command(owner, packet)
                                hello = True
                                self._send(
                                    conn,
                                    Packet(
                                        Kind.RESPONSE,
                                        packet.request,
                                        self.state.session,
                                        json_payload(response),
                                    ),
                                )
                        except socket.timeout:
                            pass
                        if not hello:
                            continue
                        if self.state.running and time.monotonic() > next_frame:
                            self.state.receive(bytes([self.state.sequence % 256]))
                            next_frame = time.monotonic() + 0.02
                        if self.state.frames:
                            payload = b"".join(f.wire() for f in self.state.frames)
                            self.state.frames.clear()
                            self._send(
                                conn,
                                Packet(
                                    Kind.FRAMES,
                                    session=self.state.session,
                                    payload=payload,
                                ),
                            )
                        event = self.state.tick()
                        if event:
                            self._send(
                                conn,
                                Packet(
                                    Kind.TX_EVENT,
                                    event["request"],
                                    self.state.session,
                                    json_payload(event),
                                ),
                            )
                        if self.state.owner is None:
                            break
            except (OSError, ValueError) as exc:
                self.errors.append(type(exc).__name__)
            finally:
                raw.close()
                self.state.disconnect(owner)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credentials", default=".secrets/device")
    p.add_argument("--port", type=int, default=7443)
    a = p.parse_args()
    s = Simulator(a.credentials, a.port).start()
    print(f"SYNTHETIC device at 127.0.0.1:{s.port}; no hardware CAN")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        s.close()
