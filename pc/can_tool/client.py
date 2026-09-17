"""Authenticated transport; request IDs are never retried automatically."""

import json
import queue
import socket
import ssl
import threading
import time
from pathlib import Path
from .protocol import Packet, Kind, Parser


class Client:
    def __init__(self, address, credentials, port=7443, event_capacity=1024):
        self.address, self.port = address, port
        self.credentials = Path(credentials)
        self.events = queue.Queue(event_capacity)
        self.pending = {}
        self.lock = threading.Lock()
        self.request_lock = threading.Lock()
        # SSLSocket operations and teardown must not race across threads.
        self.io_lock = threading.Lock()
        self.next_id = 1
        self.session = 0
        self.failure = None
        self.sock = None
        self.closed = threading.Event()
        self.active = False
        self.pc_queue_discards = 0

    def connect(self):
        profile = json.loads((self.credentials / "profile.json").read_text())
        context = ssl.create_default_context(cafile=str(self.credentials / "ca.pem"))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            self.credentials / "client.pem", self.credentials / "client.key"
        )
        raw = socket.create_connection((self.address, self.port), timeout=5)
        try:
            self.sock = context.wrap_socket(raw, server_hostname=profile["hostname"])
        except Exception:
            raw.close()
            raise
        self.sock.settimeout(0.2)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            result = self.request(Kind.HELLO)
            self.session = int(result["session"])
            self.heartbeat = threading.Thread(target=self._heartbeat, daemon=True)
            self.heartbeat.start()
            return result
        except Exception:
            self.close()
            raise

    def _read(self):
        parser = Parser()
        try:
            while not self.closed.is_set():
                try:
                    with self.io_lock:
                        if self.closed.is_set():
                            break
                        data = self.sock.recv(8192)
                except socket.timeout:
                    self.closed.wait(0.001)
                    continue
                if not data:
                    raise ConnectionError(
                        "device disconnected; outstanding TX may be indeterminate"
                    )
                for packet in parser.feed(data):
                    if self.session and packet.session != self.session:
                        raise ValueError("device session changed within connection")
                    if packet.kind == Kind.RESPONSE:
                        value = json.loads(packet.payload)
                        with self.lock:
                            waiter = self.pending.get(packet.request)
                        if waiter:
                            waiter.put_nowait(value)
                    else:
                        try:
                            self.events.put_nowait((time.time_ns(), packet))
                        except queue.Full:
                            self.pc_queue_discards += 1
                            raise BufferError(
                                "PC event queue overflow: capture stopped; recording incomplete"
                            )
        except Exception as exc:
            if not self.closed.is_set():
                self.failure = exc
        finally:
            self.closed.set()
            self.active = False
            self._close_socket()

    def request(self, kind, payload=b"", timeout=5, on_request=None):
        with self.request_lock:
            if self.closed.is_set():
                raise ConnectionError(str(self.failure or "connection closed"))
            rid = self.next_id
            self.next_id += 1
            if rid > 0xFFFFFFFF:
                raise ConnectionError("request ID exhausted; reconnect explicitly")
            waiter = queue.Queue(1)
            with self.lock:
                self.pending[rid] = waiter
            try:
                if on_request:
                    on_request(rid)
                with self.io_lock:
                    if self.closed.is_set():
                        raise ConnectionError("connection closed")
                    self.sock.sendall(Packet(kind, rid, self.session, payload).encode())
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        response = waiter.get(timeout=0.1)
                        break
                    except queue.Empty:
                        if self.closed.is_set() or time.monotonic() > deadline:
                            raise TimeoutError(
                                f"request {rid} indeterminate; not resent"
                            )
                if not response.get("ok"):
                    raise RuntimeError(
                        f"{response.get('error', 'device rejected command')} (code {response.get('code', 'unspecified')})"
                    )
                if kind in (Kind.STOP, Kind.CANCEL):
                    self.active = False
                return response
            except (OSError, TimeoutError):
                self.close()
                raise
            finally:
                with self.lock:
                    self.pending.pop(rid, None)

    def _heartbeat(self):
        while not self.closed.wait(0.5):
            try:
                self.request(Kind.PING, timeout=2)
            except Exception as exc:
                if not self.closed.is_set():
                    self.failure = exc
                self.close()
                return

    def configure(self, payload, *, allow_tx=False):
        from .protocol import CONFIG

        if CONFIG.unpack(payload)[1] and not allow_tx:
            raise PermissionError("active mode needs --allow-tx")
        result = self.request(Kind.CONFIGURE, payload)
        self.active = bool(CONFIG.unpack(payload)[1])
        return result

    def send_frame(self, frame, interval_ms=0, count=1, on_request=None):
        if not self.active:
            raise PermissionError("connection is not explicitly active")
        return self.request(
            Kind.TX, frame.tx_wire(interval_ms, count), on_request=on_request
        )

    def close(self):
        self.closed.set()
        self.active = False
        self._close_socket()
        reader = getattr(self, "reader", None)
        if reader and reader is not threading.current_thread():
            reader.join()

    def _close_socket(self):
        with self.io_lock:
            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.sock.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
