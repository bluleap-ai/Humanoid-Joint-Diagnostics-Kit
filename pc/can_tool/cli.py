import argparse
import getpass
import json
import queue
import sys
import time
from .protocol import Kind, Frame, EXT, FD, BRS, RTR, configuration, decode_frames
from .client import Client
from .wifi import provisioning
from .model import Decoder, DisplayFilter, Monitor, SequenceTracker
from .recording import Recorder, read_recording, export_csv


def frame_args(p):
    p.add_argument("--id", type=lambda v: int(v, 0), required=True)
    p.add_argument("--data", default="")
    p.add_argument("--extended", action="store_true")
    p.add_argument("--fd", action="store_true")
    p.add_argument("--brs", action="store_true")
    p.add_argument("--rtr", action="store_true")
    p.add_argument("--dlc", type=int)


def timing_args(p):
    p.add_argument("--bitrate", type=int, default=500000)
    p.add_argument("--sample-point", type=int, default=875)
    p.add_argument("--data-bitrate", type=int, default=2000000)
    p.add_argument("--data-sample-point", type=int, default=800)


def parser():
    p = argparse.ArgumentParser(
        description="Local Wi-Fi CAN/CAN FD diagnostics; never automatically replays transmissions."
    )
    commands = p.add_subparsers(dest="command", required=True)
    d = commands.add_parser("discover")
    d.add_argument("--seconds", type=float, default=3)
    for name in ("info", "configure", "monitor", "record", "send", "wifi", "bridge"):
        s = commands.add_parser(name)
        s.add_argument("--device", required=True)
        s.add_argument("--port", type=int, default=7443)
        s.add_argument(
            "--credentials",
            default=".secrets/device",
            help="directory with profile.json, CA, client certificate/key",
        )
        if name in ("configure", "monitor", "record", "send"):
            timing_args(s)
            if name != "send":
                s.add_argument("--fd", action="store_true")
        if name == "configure":
            s.add_argument("--active", action="store_true")
            s.add_argument("--allow-tx", action="store_true")
        if name in ("monitor", "record"):
            s.add_argument("--dbc")
            s.add_argument("--output", required=name == "record")
            s.add_argument("--seconds", type=float, default=0)
            s.add_argument("--include", default="")
            s.add_argument("--exclude", default="")
            s.add_argument(
                "--format", choices=["any", "standard", "extended"], default="any"
            )
            s.add_argument("--name", action="append", default=[])
            s.add_argument("--signal", action="append", default=[])
            s.add_argument("--view", choices=["trace", "latest"], default="latest")
        if name == "send":
            frame_args(s)
            s.add_argument("--allow-tx", action="store_true", required=True)
            s.add_argument("--interval-ms", type=int, default=0)
            s.add_argument("--count", type=int, default=1)
            s.add_argument(
                "--output", help="record TX request/outcomes and observed RX"
            )
        if name == "wifi":
            s.add_argument("mode", choices=["ap", "station"])
            s.add_argument("--ssid")
            s.add_argument("--band", choices=["2.4", "5"], default="2.4")
            s.add_argument(
                "--channel", type=int, default=0, help="AP channel; 0 uses band default"
            )
            s.add_argument(
                "--country", help="two-letter operating country; required for 5 GHz"
            )
        if name == "bridge":
            s.add_argument("--adapter", required=True)
    for name in ("inspect", "play", "export"):
        s = commands.add_parser(name)
        s.add_argument("recording")
        s.add_argument("--dbc")
        if name == "export":
            s.add_argument("--output", required=True)
            s.add_argument("--format", choices=["csv"], default="csv")
        if name == "play":
            s.add_argument("--speed", type=float, default=1)
    return p


def render(model, view, signals=()):
    from rich.table import Table

    table = Table(title="CAN RX — device callback time; q quits, t trace, a latest")
    for name in (
        "Device µs",
        "Relative µs",
        "Δ µs",
        "ID / format",
        "Flags / DLC / len",
        "Data",
        "Count",
        "DBC / signals",
    ):
        table.add_column(name)
    rows = list(model.trace if view == "trace" else model.latest.values())[-25:]
    for row in rows:
        f = row["frame"]
        selected = {
            k: v for k, v in row["signals"].items() if not signals or k in signals
        }
        table.add_row(
            str(f.timestamp_us),
            str(row["relative_us"]),
            str(row["interval_us"]),
            f"{f.identifier:X} " + ("EXT" if f.flags & EXT else "STD"),
            f"{'FD' if f.flags & FD else 'CAN'} {f.flags:02x} / {f.dlc} / {len(f.data)}",
            f.data.hex(" "),
            str(row["count"]),
            row["name"] + " " + json.dumps(selected),
        )
    return table


class Keys:
    def __enter__(self):
        self.old = None
        if sys.stdin.isatty() and sys.platform != "win32":
            import termios
            import tty

            self.old = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def get(self):
        if sys.platform == "win32":
            import msvcrt

            return msvcrt.getwch() if msvcrt.kbhit() else ""
        import select

        return (
            sys.stdin.read(1)
            if self.old and select.select([sys.stdin], [], [], 0)[0]
            else ""
        )

    def __exit__(self, *a):
        if self.old:
            import termios

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old)


def monitor(client, args, recorder):
    from rich.live import Live
    from rich.console import Group
    import threading

    decoder = Decoder(args.dbc) if args.dbc else None
    filt = DisplayFilter(
        args.include,
        args.exclude,
        None if args.format == "any" else args.format == "extended",
        args.name,
    )
    model = Monitor()
    tracker = SequenceTracker()
    lock = threading.Lock()
    stop = threading.Event()
    counters = {"received": 0, "ui_refreshes_skipped": 0}
    errors = []
    status = {}
    tx_events = []

    def process():
        try:
            while not stop.is_set():
                try:
                    receipt, packet = client.events.get(timeout=0.1)
                except queue.Empty:
                    if client.closed.is_set():
                        raise ConnectionError(str(client.failure or "disconnected"))
                    continue
                if packet.kind == Kind.FRAMES:
                    for frame in decode_frames(packet):
                        gap = tracker.observe(frame)
                        counters["received"] += 1
                        if recorder:
                            if gap:
                                recorder.write(
                                    "gap",
                                    {
                                        "missing_sequences": gap,
                                        "session": frame.session,
                                    },
                                    receipt,
                                )
                            recorder.write("rx", frame.as_dict(), receipt)
                        name, values, error = (
                            decoder.decode(frame) if decoder else ("", {}, None)
                        )
                        if error:
                            values = {"decode_error": error}
                        if filt.matches(frame, name):
                            with lock:
                                model.add(frame, name, values)
                elif packet.kind in (Kind.STATUS, Kind.TX_EVENT):
                    event = json.loads(packet.payload)
                    if recorder:
                        recorder.write(
                            "status" if packet.kind == Kind.STATUS else "tx_event",
                            event,
                            receipt,
                        )
                    with lock:
                        if packet.kind == Kind.STATUS:
                            status.clear()
                            status.update(event)
                        else:
                            tx_events.append(event)
                            del tx_events[:-5]
        except Exception as exc:
            errors.append(exc)
            stop.set()
            client.close()

    worker = threading.Thread(target=process, daemon=True)
    worker.start()
    view = args.view
    start = time.monotonic()
    try:
        with (
            Keys() as keys,
            Live(render(Monitor(), view, args.signal), auto_refresh=False) as live,
        ):
            while not stop.is_set() and (
                not args.seconds or time.monotonic() - start < args.seconds
            ):
                if lock.acquire(blocking=False):
                    try:
                        # Copy bounded state; table rendering never holds the ingestion lock.
                        snapshot = Monitor()
                        snapshot.trace = model.trace.copy()
                        snapshot.latest = model.latest.copy()
                        state = dict(status)
                        tx = list(tx_events)
                    finally:
                        lock.release()
                    summary = f"RX {counters['received']} | sequence gaps {tracker.gaps} | queue drops {state.get('queue_drops', '?')} | transport discards {state.get('transport_discards', '?')} | hardware losses {state.get('hardware_rx_losses', 'unsupported')} | skipped UI refreshes {counters['ui_refreshes_skipped']}"
                    live.update(
                        Group(
                            render(snapshot, view, args.signal),
                            summary,
                            "TX events: " + json.dumps(tx),
                        ),
                        refresh=True,
                    )
                else:
                    counters["ui_refreshes_skipped"] += 1
                key = keys.get()
                if key == "q":
                    break
                if key == "t":
                    view = "trace"
                if key == "a":
                    view = "latest"
                stop.wait(0.1)
    finally:
        # Stop reception while ingestion still drains queued records, then join before closing recorder.
        if not client.closed.is_set():
            try:
                client.request(Kind.STOP)
            except Exception:
                pass
        deadline = time.monotonic() + 1
        while not client.events.empty() and not errors and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()
        worker.join(2)
        if worker.is_alive():
            raise RuntimeError("recording worker blocked; output may be incomplete")
    if errors:
        raise errors[0]
    return {
        **counters,
        "sequence_gaps": tracker.gaps,
        "pc_queue_discards": client.pc_queue_discards,
        "recording_failures": recorder.failures if recorder else 0,
    }


def discover(seconds):
    from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

    found = {}

    class Listener(ServiceListener):
        def add_service(self, z, t, n):
            info = z.get_service_info(t, n)
            if info:
                found[n] = {
                    "name": n,
                    "addresses": info.parsed_addresses(),
                    "port": info.port,
                }

        def update_service(self, z, t, n):
            self.add_service(z, t, n)

        def remove_service(self, z, t, n):
            found.pop(n, None)

    with Zeroconf() as z:
        browser = ServiceBrowser(z, "_wcan._tcp.local.", Listener())
        time.sleep(max(0, min(seconds, 30)))
        browser.cancel()
    print(json.dumps(list(found.values()), indent=2))


def run(args):
    if args.command == "discover":
        return discover(args.seconds)
    if args.command in ("inspect", "export", "play"):
        decoder = Decoder(args.dbc) if args.dbc else None
        if args.command == "export":
            return export_csv(args.recording, args.output, decoder)
        if args.command == "play" and args.speed <= 0:
            raise ValueError("speed must be positive")
        previous = None
        model = Monitor()
        for event in read_recording(args.recording):
            if args.command == "play" and event["type"] == "rx":
                f = Frame.from_dict(event["data"])
                if previous and previous.session == f.session:
                    time.sleep(
                        min(
                            2,
                            max(
                                0,
                                (f.timestamp_us - previous.timestamp_us)
                                / 1e6
                                / args.speed,
                            ),
                        )
                    )
                previous = f
                name, signals, error = decoder.decode(f) if decoder else ("", {}, None)
                model.add(f, name, signals)
                from rich.console import Console

                c = Console()
                c.clear()
                c.print(render(model, "trace"))
            elif args.command == "inspect":
                if decoder and event["type"] == "rx":
                    event["decoded"] = decoder.decode(Frame.from_dict(event["data"]))
                print(json.dumps(event))
        return
    if args.command == "bridge":
        raise ValueError(
            "No external UI adapter is verified yet. See docs/external-tools.md; reusable DiagnosticAdapter is available."
        )
    with Client(args.device, args.credentials, args.port) as client:
        if args.command == "info":
            print(json.dumps(client.request(Kind.INFO), indent=2))
            return
        if args.command == "wifi":
            ssid = (
                (args.ssid or input("Router SSID: ")) if args.mode == "station" else ""
            )
            password = (
                getpass.getpass("Router password (not logged): ")
                if args.mode == "station"
                else ""
            )
            payload = provisioning(
                args.mode, ssid, password, args.band, args.channel, args.country
            )
            print(client.request(Kind.WIFI, payload))
            return
        active = args.command == "send" or getattr(args, "active", False)
        cfg = configuration(
            args.fd,
            active,
            args.bitrate,
            args.sample_point,
            args.data_bitrate,
            args.data_sample_point,
        )
        applied = client.configure(cfg, allow_tx=getattr(args, "allow_tx", False))
        if args.command == "configure":
            print(json.dumps(applied, indent=2))
            print(
                "Connection closing: device returns to stopped/listen-only. Use send for scoped active control."
            )
            return
        recorder = (
            Recorder(
                args.output,
                {
                    "configuration": applied,
                    "session": client.session,
                    "synthetic": bool(applied.get("synthetic", False)),
                },
            )
            if args.output
            else None
        )
        try:
            client.request(Kind.START)
            if args.command in ("monitor", "record"):
                result = monitor(client, args, recorder)
                print(json.dumps(result))
            else:
                f = Frame(
                    args.id,
                    bytes.fromhex(args.data),
                    (EXT if args.extended else 0)
                    | (FD if args.fd else 0)
                    | (BRS if args.brs else 0)
                    | (RTR if args.rtr else 0),
                    args.dlc,
                )

                def record_intent(request):
                    if recorder:
                        recorder.write(
                            "tx_request",
                            {
                                "request": request,
                                "frame": f.as_dict(),
                                "count": args.count,
                                "interval_ms": args.interval_ms,
                            },
                        )

                accepted = client.send_frame(
                    f, args.interval_ms, args.count, on_request=record_intent
                )
                if recorder:
                    recorder.write("tx_event", accepted)
                print(json.dumps(accepted))
                deadline = time.monotonic() + args.count * args.interval_ms / 1000 + 5
                while time.monotonic() < deadline:
                    if client.closed.is_set():
                        raise ConnectionError(str(client.failure))
                    try:
                        receipt, p = client.events.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if p.kind == Kind.FRAMES and recorder:
                        for frame in decode_frames(p):
                            recorder.write("rx", frame.as_dict(), receipt)
                    elif p.kind in (Kind.STATUS, Kind.TX_EVENT):
                        event = json.loads(p.payload)
                        if recorder:
                            recorder.write(
                                "status" if p.kind == Kind.STATUS else "tx_event",
                                event,
                                receipt,
                            )
                        if p.kind == Kind.TX_EVENT:
                            print(json.dumps(event))
                            if event.get("terminal"):
                                if event.get("state") != "completed":
                                    raise RuntimeError(
                                        "transmission did not complete successfully"
                                    )
                                break
                else:
                    raise TimeoutError("TX outcome indeterminate; no automatic resend")
        finally:
            if not client.closed.is_set():
                try:
                    client.request(Kind.STOP)
                except Exception:
                    pass
            if recorder:
                recorder.write(
                    "disconnect",
                    {
                        "reason": str(client.failure or "client closed"),
                        "pc_queue_discards": client.pc_queue_discards,
                    },
                )
                recorder.close()


def main():
    try:
        run(parser().parse_args())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
