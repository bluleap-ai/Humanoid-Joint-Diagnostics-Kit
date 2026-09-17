"""Versioned Wi-Fi provisioning payload; secrets must never be recorded."""

COUNTRIES = frozenset(
    "AT AU BE BG BR CA CH CN CY CZ DE DK EE ES FI FR GB GR HK HR HU IE IN IS IT JP KR LI LT LU LV MT MX NL NO NZ PL PT RO SE SI SK TW US".split()
)


def provisioning(mode, ssid="", password="", band="2.4", channel=0, country=None):
    if mode not in ("ap", "station") or band not in ("2.4", "5"):
        raise ValueError("invalid Wi-Fi mode or band")
    country = (country or "").upper()
    if country and (len(country) != 2 or not all("A" <= c <= "Z" for c in country)):
        raise ValueError("country must be a two-letter country code")
    if country and country not in COUNTRIES:
        raise ValueError(
            "country is not documented as supported by the pinned Wi-Fi HAL"
        )
    if band == "5" and not country:
        raise ValueError("5 GHz requires --country for your operating location")
    if channel not in ((0, 36, 40, 44, 48) if band == "5" else range(12)):
        raise ValueError("AP channel must be 1..11 (2.4 GHz) or 36/40/44/48 (5 GHz)")
    if mode == "station" and channel:
        raise ValueError("Station mode scans the selected band; omit --channel")
    a, b = ssid.encode(), password.encode()
    if b"\0" in a + b or len(a) > 32 or len(b) > 63:
        raise ValueError("invalid SSID/password bytes")
    if mode == "station" and (not a or len(b) < 8):
        raise ValueError("SSID 1..32 bytes; WPA2 password 8..63 bytes")
    if mode == "ap" and (a or b):
        raise ValueError("AP uses its provisioned unique credentials")
    return (
        bytes([0x80 | (mode == "station"), len(a), len(b), band == "5", channel])
        + (country.encode() or b"\0\0")
        + a
        + b
    )
