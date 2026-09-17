import ctypes
import random
import subprocess
from pathlib import Path
import pytest
from can_tool.protocol import (
    Frame,
    Packet,
    Parser,
    Kind,
    FD,
    EXT,
    BRS,
    RTR,
    LENGTHS,
    HEADER,
    MAGIC,
    decode_frames,
)


@pytest.mark.parametrize("length", LENGTHS)
def test_fd_roundtrip(length):
    f = Frame(
        0x123456,
        bytes(range(length)),
        EXT | FD | BRS,
        sequence=42,
        timestamp_us=987654,
        session=9,
    )
    assert decode_frames(Packet(Kind.FRAMES, session=9, payload=f.wire())) == [f]
    assert f.dlc == LENGTHS.index(length)


@pytest.mark.parametrize(
    "kw",
    [
        {"identifier": 0x800},
        {"identifier": -1},
        {"identifier": 1, "data": b"x" * 9},
        {"identifier": 1, "flags": FD | RTR},
        {"identifier": 1, "flags": BRS},
        {"identifier": 1, "flags": 32},
        {"identifier": 1, "data": b"xx", "dlc": 1},
    ],
)
def test_invalid_frames(kw):
    with pytest.raises(ValueError):
        Frame(**kw)


def test_rtr_and_classic_large_dlc():
    assert Frame(1, b"", RTR, 8).tx_wire()
    assert len(Frame(1, b"12345678", dlc=15).data) == 8
    with pytest.raises(ValueError):
        Frame(1, b"12345678", dlc=15).tx_wire()


@pytest.mark.parametrize("split", range(1, 50))
def test_fragmented_packets(split):
    packets = [
        Packet(Kind.INFO, 1),
        Packet(Kind.FRAMES, session=7, payload=Frame(1, b"ab").wire()),
    ]
    raw = b"".join(p.encode() for p in packets)
    parser = Parser()
    out = []
    for i in range(0, len(raw), split):
        out += parser.feed(raw[i : i + split])
    assert out == packets


@pytest.mark.parametrize("offset,value", [(0, 0), (4, 2), (5, 99), (7, 1)])
def test_bad_headers(offset, value):
    raw = bytearray(Packet(Kind.INFO, 1).encode())
    raw[offset] = value
    with pytest.raises(ValueError):
        Parser().feed(raw)


def test_oversize_and_truncated_frame():
    raw = HEADER.pack(MAGIC, 1, 2, 0, 4097, 1, 0)
    with pytest.raises(ValueError):
        Parser().feed(raw)
    with pytest.raises(ValueError):
        decode_frames(Packet(Kind.FRAMES, payload=b"no"))


def test_c_wire_agrees(tmp_path):
    root = Path(__file__).parents[1]
    lib = tmp_path / "wire.dylib"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(root / "firmware/src/wire.c"),
            "-o",
            str(lib),
        ],
        check=True,
    )
    c = ctypes.CDLL(str(lib))

    class CHeader(ctypes.Structure):
        _fields_ = [
            ("kind", ctypes.c_uint8),
            ("length", ctypes.c_uint32),
            ("request", ctypes.c_uint32),
            ("session", ctypes.c_uint64),
        ]

    header = CHeader()
    raw = Packet(Kind.INFO, 12, 99).encode()
    assert c.w_parse(raw, ctypes.byref(header)) == 0
    assert (header.kind, header.request, header.session) == (2, 12, 99)
    for offset, value in [(0, 0), (4, 2), (5, 99), (7, 1)]:
        invalid = bytearray(raw)
        invalid[offset] = value
        assert c.w_parse(bytes(invalid), ctypes.byref(header)) == -1

    c.w_length.argtypes = [ctypes.c_uint8]
    for dlc, length in enumerate(LENGTHS):
        assert c.w_length(dlc) == length

    class CFrame(ctypes.Structure):
        _fields_ = [
            ("seq", ctypes.c_uint64),
            ("us", ctypes.c_uint64),
            ("id", ctypes.c_uint32),
            ("channel", ctypes.c_uint8),
            ("flags", ctypes.c_uint8),
            ("dlc", ctypes.c_uint8),
            ("len", ctypes.c_uint8),
            ("data", ctypes.c_uint8 * 64),
        ]

    rng = random.Random(123)
    for _ in range(500):
        cf = CFrame()
        cf.id = rng.randrange(0x3000)
        cf.flags = rng.randrange(64)
        cf.dlc = rng.randrange(18)
        cf.len = rng.randrange(66)
        valid = c.w_validate(ctypes.byref(cf), False) == 0
        try:
            Frame(
                cf.id,
                bytes(cf.data)[: cf.len] if cf.len <= 64 else b"x" * cf.len,
                cf.flags,
                cf.dlc,
            )
            pyvalid = True
        except ValueError:
            pyvalid = False
        assert valid == pyvalid
    f = Frame(0x123, b"abc", sequence=123, timestamp_us=345)
    cf = CFrame(123, 345, 0x123, 0, 0, 3, 3, (ctypes.c_uint8 * 64)(*b"abc"))
    out = ctypes.create_string_buffer(88)
    n = c.w_encode(out, ctypes.byref(cf))
    assert out.raw[:n] == f.wire()


def test_actual_firmware_capture_state(tmp_path):
    root = Path(__file__).parents[1]
    exe = tmp_path / "capture"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-I" + str(root / "tests/fakes"),
            str(root / "tests/capture_harness.c"),
            str(root / "firmware/src/wire.c"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    subprocess.run([str(exe)], check=True)
