"""V1 big-endian wire protocol; see docs/protocol.md."""

from dataclasses import dataclass
import enum
import json
import struct

MAGIC = b"WCAN"
VERSION = 1
MAX_PAYLOAD = 4096
HEADER = struct.Struct(">4sBBHIIQ")
RECORD = struct.Struct(">QQIBBBB")
CONFIG = struct.Struct(">BBIHIH")
TX_PREFIX = struct.Struct(">II")
FRAME = struct.Struct(">IBBBB")
LENGTHS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)
EXT, FD, BRS, ESI, RTR = 1, 2, 4, 8, 16


class Kind(enum.IntEnum):
    HELLO = 1
    INFO = 2
    CONFIGURE = 3
    START = 4
    STOP = 5
    TX = 6
    CANCEL = 7
    WIFI = 8
    PING = 9
    RESPONSE = 128
    STATUS = 129
    FRAMES = 130
    TX_EVENT = 131


@dataclass(frozen=True)
class Packet:
    kind: Kind
    request: int = 0
    session: int = 0
    payload: bytes = b""

    def encode(self):
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError("payload too large")
        return (
            HEADER.pack(
                MAGIC,
                VERSION,
                int(self.kind),
                0,
                len(self.payload),
                self.request,
                self.session,
            )
            + self.payload
        )


class Parser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        # Caller feeds bounded socket reads; reject bad headers before awaiting bodies.
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= HEADER.size:
            magic, version, kind, flags, size, request, session = HEADER.unpack_from(
                self.buffer
            )
            if magic != MAGIC or version != VERSION or flags or size > MAX_PAYLOAD:
                raise ValueError("invalid header or incompatible protocol version")
            kind = Kind(kind)
            if len(self.buffer) < HEADER.size + size:
                break
            payload = bytes(self.buffer[HEADER.size : HEADER.size + size])
            del self.buffer[: HEADER.size + size]
            result.append(Packet(kind, request, session, payload))
        return result


@dataclass(frozen=True)
class Frame:
    identifier: int
    data: bytes = b""
    flags: int = 0
    dlc: int | None = None
    channel: int = 0
    sequence: int = 0
    timestamp_us: int = 0
    session: int = 0

    def __post_init__(self):
        if self.dlc is None:
            if len(self.data) not in LENGTHS:
                raise ValueError("illegal payload length; explicit padding required")
            object.__setattr__(self, "dlc", LENGTHS.index(len(self.data)))
        if not 0 <= self.identifier <= (0x1FFFFFFF if self.flags & EXT else 0x7FF):
            raise ValueError("CAN ID out of range")
        if self.flags & ~31 or self.channel != 0 or not 0 <= self.dlc <= 15:
            raise ValueError("invalid flags/channel/DLC")
        if self.flags & FD:
            if self.flags & RTR:
                raise ValueError("FD cannot be RTR")
            length = LENGTHS[self.dlc]
        else:
            if self.flags & (BRS | ESI):
                raise ValueError("BRS/ESI require FD")
            length = min(self.dlc, 8)
        if self.flags & RTR:
            length = 0
        if len(self.data) != length:
            raise ValueError("DLC and payload disagree")
        if min(self.sequence, self.timestamp_us, self.session) < 0:
            raise ValueError("negative metadata")

    @property
    def key(self):
        return self.channel, self.identifier, self.flags & (EXT | FD | RTR)

    def wire(self):
        return (
            RECORD.pack(
                self.sequence,
                self.timestamp_us,
                self.identifier,
                self.channel,
                self.flags,
                self.dlc,
                len(self.data),
            )
            + self.data
        )

    def tx_wire(self, interval_ms=0, count=1):
        if self.flags & ESI:
            raise ValueError("ESI is controller-owned on transmission")
        if (
            not 1 <= count <= 10000
            or not 0 <= interval_ms <= 60000
            or (count > 1 and interval_ms < 10)
        ):
            raise ValueError("count 1..10000, periodic interval 10..60000 ms")
        if not self.flags & FD and self.dlc > 8:
            raise ValueError("transmit Classical DLC must be <=8")
        return (
            TX_PREFIX.pack(interval_ms, count)
            + FRAME.pack(self.identifier, self.flags, self.dlc, len(self.data), 0)
            + self.data
        )

    def as_dict(self):
        return dict(
            identifier=self.identifier,
            data=self.data.hex(),
            flags=self.flags,
            dlc=self.dlc,
            channel=self.channel,
            sequence=self.sequence,
            timestamp_us=self.timestamp_us,
            session=self.session,
        )

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, "data": bytes.fromhex(value["data"])})


def decode_frames(packet):
    data = packet.payload
    result = []
    while data:
        if len(data) < RECORD.size:
            raise ValueError("truncated frame header")
        seq, ts, identifier, channel, flags, dlc, size = RECORD.unpack_from(data)
        if size > 64 or len(data) < RECORD.size + size:
            raise ValueError("truncated frame data")
        result.append(
            Frame(
                identifier,
                data[RECORD.size : RECORD.size + size],
                flags,
                dlc,
                channel,
                seq,
                ts,
                packet.session,
            )
        )
        data = data[RECORD.size + size :]
    return result


def json_payload(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def configuration(
    fd=False,
    active=False,
    bitrate=500000,
    sample_point=875,
    data_bitrate=2000000,
    data_sample_point=800,
):
    if not 10000 <= bitrate <= 1000000 or not 500 <= sample_point <= 950:
        raise ValueError("invalid nominal timing")
    if not 10000 <= data_bitrate <= 5000000 or not 500 <= data_sample_point <= 950:
        raise ValueError("invalid data timing")
    return CONFIG.pack(
        fd, active, bitrate, sample_point, data_bitrate, data_sample_point
    )
