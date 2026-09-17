# Wi-Fi operation

## Provisioning identity

Run `python tools/provision.py` on the trusted development PC before building. Each run generates a random 48-bit device identity, unique random AP password, per-device CA, server key/certificate, and one client identity. The CA signing key is not retained. Files have private permissions where supported. No credential is printed to the console.

Read `.secrets/device/profile.json` locally to join `CAN-<identity>`. Do not paste its contents into logs/issues/recordings. The firmware and host must use the same credential set. The default profile directory can be overridden with `--credentials`.

## AP

First boot without saved Station settings uses password-protected WPA2 AP, channel 6, 2.4 GHz. Device IPv4 is `192.168.4.1`; DHCP begins at `192.168.4.10`; TLS TCP is 7443. No internet, routing or NAT is provided. A PC may warn that this network lacks internet; keep it joined for direct operation.

## Station

`can-tool wifi --device 192.168.4.1 station --ssid YourSSID` prompts privately for the WPA2 password. V1 accepts SSID 1–32 bytes and passphrase 8–63 bytes; open/enterprise Wi-Fi is unsupported. The default is 2.4 GHz; `--band 5 --country XX` selects 5 GHz only. Credentials/mode are stored as one NVS settings record. CAN is stopped before saving. The device acknowledges and reboots to apply the mode; it never resumes active CAN automatically.

Find the new address through `can-tool discover`, router DHCP leases, or `can-<identity>.local`. A manual IPv4 address is always supported. The PC can retain internet access through the router. mDNS uses `_wcan._tcp.local`; discovery is a hint, and the TLS certificate remains the identity check.

Station failures are exposed as `wifi_error`; disconnected Station mode retries every 15 seconds. Failed credentials do not silently open an unauthenticated fallback network. If the device is unreachable, restore AP mode physically. Client isolation, guest networks, VLANs, local firewalls and blocked multicast can prevent access/discovery; manual addressing only helps when TCP routing is allowed.

## Physical AP recovery

1. Power/reset normally **without holding BOOT**. BOOT is GPIO28, a boot-strapping input.
2. Wait at least five seconds after application initialization.
3. Ensure BOOT has been released, then press and hold BOOT for at least three seconds.
4. Release after reboot; reconnect to the original unique AP.

The application deliberately requires a released button after its startup delay. Holding BOOT during reset enters ROM download mode and is not the recovery procedure. Recovery clears saved Station/band/channel/country settings and restores the 2.4 GHz channel-6 AP, stops CAN and reboots; it does not change the embedded TLS/AP credentials. Missing GPIO/flash support is an initialization error. Power-cycle recovery and NVS persistence are still pending hardware tests.

## Selecting 5 GHz / Wi-Fi 6

Use your actual operating country, not an arbitrary code. For example, **only when operating in the United States**:

```sh
# Join a router on 5 GHz; password is prompted privately.
can-tool wifi --device 192.168.4.1 station --ssid YourSSID --band 5 --country US
# Or create a direct 5 GHz hotspot (same unique AP password/IP).
can-tool wifi --device 192.168.4.1 ap --band 5 --country US --channel 36
# Return to default 2.4 GHz AP using the current reachable device address.
can-tool wifi --device DEVICE_IP ap --band 2.4
```

Station mode scans only the selected band and does not accept a fixed channel. AP channels are limited to 1–11 on 2.4 GHz (default 6), and 36/40/44/48 on 5 GHz (default 36), subject to the HAL country rules. DFS AP operation and automatic band fallback are not implemented. The country is fixed explicitly, with 802.11d country overrides disabled. Invalid syntax is rejected before saving; radio configuration/association failure after reboot is reported when reachable and otherwise requires physical recovery. A successful provisioning response means settings were saved, not that the new network connected.

The pinned HAL documents these country codes: AT AU BE BG BR CA CH CN CY CZ DE DK EE ES FI FR GB GR HK HR HU IE IN IS IT JP KR LI LT LU LV MT MX NL NO NZ PL PT RO SE SI SK TW US. Other codes are rejected conservatively. **Indonesia (`ID`) is not documented in this HAL version, so 5 GHz operation there remains blocked pending HAL support verification/update. Do not select another country as a workaround.** With no country supplied, 2.4 GHz uses HAL world-safe code `01`.

The pinned driver ignores the generic connection `band` field. Firmware therefore sets the band through `esp_wifi_set_band_mode()` before Station association/AP enable, after the driver's initial NULL-mode radio start. All connectivity still uses Zephyr. Existing legacy saved settings and Wi-Fi commands remain readable as 2.4 GHz configurations. Extended commands are rejected by older firmware; update firmware and CLI together.

The C5 HAL defaults include 802.11ax on both bands. Wi-Fi 6 is negotiable, not forced: a peer can negotiate an older compatible mode. INFO/status separates `wifi_band_requested` from actual `wifi_band`, `wifi_channel` (0 if unknown), and `wifi_phy`. Station `wifi_phy: "802.11ax"` means the driver reported negotiated Wi-Fi 6; unknown modes and AP-wide PHY are null. AP mode has no single negotiated PHY across clients. No successful hardware negotiation is claimed yet.

Verified against the pinned HAL `components/esp_wifi/include/esp_wifi.h` (country code, band mode and protocol defaults) and Zephyr `drivers/wifi/esp32/src/esp_wifi_drv.c` (startup, connection and status paths). See [Espressif Wi-Fi API reference](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c5/api-reference/network/esp_wifi.html); the local pinned header remains the compatibility source for this build.
