"""Append-only versioned JSONL, raw frames kept independently of display filters."""

import csv
import json
import time
from .protocol import Frame


class Recorder:
    def __init__(self, path, metadata):
        self.file = open(path, "x", encoding="utf8")
        self.failures = 0
        self.write(
            "metadata", {"format": "wireless-can-jsonl", "version": 1, **metadata}
        )

    def write(self, kind, data, receipt_ns=None):
        # Only allow known non-secret event types. Never record provisioning packets.
        if kind not in {
            "metadata",
            "rx",
            "status",
            "gap",
            "tx_request",
            "tx_event",
            "disconnect",
        }:
            raise ValueError("unsupported recording event")
        try:
            self.file.write(
                json.dumps(
                    {
                        "type": kind,
                        "pc_receipt_ns": receipt_ns or time.time_ns(),
                        "data": data,
                    },
                    allow_nan=False,
                )
                + "\n"
            )
            self.file.flush()
        except OSError:
            self.failures += 1
            raise

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def read_recording(path):
    with open(path, encoding="utf8") as stream:
        for number, line in enumerate(iter(lambda: stream.readline(1048577), ""), 1):
            if len(line) > 1048576:
                raise ValueError(f"oversize record at line {number}")
            try:
                event = json.loads(line)
                if number == 1 and (
                    event["type"] != "metadata"
                    or event["data"]["format"] != "wireless-can-jsonl"
                    or event["data"]["version"] != 1
                ):
                    raise ValueError("unsupported recording")
                if event["type"] == "rx":
                    Frame.from_dict(event["data"])
                yield event
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid recording line {number}: {exc}") from exc
        if stream.tell() == 0:
            raise ValueError("empty recording")


def export_csv(path, output, decoder=None):
    fields = [
        "session",
        "sequence",
        "timestamp_us",
        "pc_receipt_ns",
        "channel",
        "identifier",
        "flags",
        "dlc",
        "length",
        "data",
        "message",
        "signals",
        "decode_error",
    ]
    with open(output, "x", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for event in read_recording(path):
            if event["type"] != "rx":
                continue
            frame = Frame.from_dict(event["data"])
            name, signals, error = decoder.decode(frame) if decoder else ("", {}, None)
            writer.writerow(
                {
                    **frame.as_dict(),
                    "length": len(frame.data),
                    "pc_receipt_ns": event["pc_receipt_ns"],
                    "message": name,
                    "signals": json.dumps(signals),
                    "decode_error": error,
                }
            )
