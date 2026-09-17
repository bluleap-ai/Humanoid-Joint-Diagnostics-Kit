import ctypes
import subprocess

import pytest

from can_tool.wifi import provisioning
from can_tool.cli import parser


class Saved(ctypes.Structure):
    _fields_ = [
        ("station", ctypes.c_uint8),
        ("ssid", ctypes.c_char * 33),
        ("password", ctypes.c_char * 64),
        ("band", ctypes.c_uint8),
        ("channel", ctypes.c_uint8),
        ("country", ctypes.c_char * 3),
    ]


@pytest.fixture(scope="module")
def firmware(tmp_path_factory):
    path = tmp_path_factory.mktemp("wifi") / "wifi.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Werror",
            "-Ifirmware/src",
            "firmware/src/wifi_config.c",
            "-o",
            str(path),
        ],
        check=True,
    )
    lib = ctypes.CDLL(str(path))
    lib.wifi_payload_parse.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.POINTER(Saved),
    ]
    return lib


@pytest.mark.parametrize(
    "mode,band,channel,country",
    [
        ("station", "2.4", 0, None),
        ("station", "5", 0, "GB"),
        ("ap", "2.4", 6, None),
        ("ap", "5", 36, "US"),
        ("ap", "5", 48, "GB"),
    ],
)
def test_wifi_c_python_roundtrip(firmware, mode, band, channel, country):
    ssid, password = ("router", "test-password") if mode == "station" else ("", "")
    payload = provisioning(mode, ssid, password, band, channel, country)
    result = Saved()
    assert firmware.wifi_payload_parse(payload, len(payload), ctypes.byref(result)) == 0
    assert result.station == (mode == "station") and result.band == (band == "5")
    assert result.channel == channel and result.country.decode() == (country or "")
    assert result.ssid.decode() == ssid and result.password.decode() == password
    for n in range(len(payload)):
        assert firmware.wifi_payload_parse(payload, n, ctypes.byref(result)) < 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"band": "5"},
        {"country": "ID"},
        {"country": "USA"},
        {"country": "1D"},
        {"band": "6"},
        {"band": "5", "country": "US", "channel": 52},
        {"channel": 14},
        {"channel": -1},
        {"mode": "station", "ssid": "x", "password": "short"},
        {"mode": "station", "ssid": "x", "password": "12345678", "channel": 6},
        {"ssid": "custom"},
        {"country": "éé"},
    ],
)
def test_wifi_invalid_host(kwargs):
    with pytest.raises(ValueError):
        provisioning(**{"mode": "ap", **kwargs})


def test_firmware_rejects_malformed_and_accepts_legacy(firmware):
    result = Saved()
    for payload in [
        b"",
        b"\x80",
        b"\x82\0\0\0\0\0\0",
        b"\x80\0\0\x01\0\0\0",
        b"\x80\0\0\x01\x34US",
        b"\x80\0\0\0\0U1",
        b"\x80\0\0\0\0\0S",
        b"\0\0\0extra",
    ]:
        assert (
            firmware.wifi_payload_parse(payload, len(payload), ctypes.byref(result)) < 0
        )
    for payload in [b"\0\0\0", b"\x01\x01\x08x12345678"]:
        assert (
            firmware.wifi_payload_parse(payload, len(payload), ctypes.byref(result))
            == 0
        )
        assert result.band == 0 and not result.country


def test_cli_wifi_options():
    args = parser().parse_args(
        [
            "wifi",
            "--device",
            "192.168.4.1",
            "ap",
            "--band",
            "5",
            "--country",
            "GB",
            "--channel",
            "36",
        ]
    )
    assert args.band == "5" and args.country == "GB" and args.channel == 36
