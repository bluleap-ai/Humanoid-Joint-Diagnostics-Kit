# Wireless CAN / CAN FD Diagnostics — V1

Local, authenticated Wi-Fi diagnostics for **Seeed XIAO ESP32-C5 + Adafruit CAN Pal 5708**. Firmware uses **Zephyr**, following the requested change from ESP-IDF. USB is used only for power, development flashing and logs.

**Status:** firmware builds for the XIAO; Python, TLS simulator and host-compiled firmware logic tests are provided. **No physical hardware validation has been performed.** This is an engineering prototype, not a validated lossless capture device. See [test evidence](testing.md) and [limitations](limitations.md).

## Implemented

- One Classical CAN / CAN FD channel, standard/extended IDs, RTR, FD BRS/ESI receive flags, payloads through 64 bytes.
- Boot stopped; passive capture by default. Explicit active control, one finite TX schedule, cancellation, disconnect/lease shutdown, no automatic resend.
- Internal-RAM receive queue, sequence gaps, batching, status and separate loss categories.
- Selectable 2.4/5 GHz password-protected AP and persisted WPA2 Station provisioning, reconnect attempts, physical AP recovery, mDNS and manual IPv4 connection.
- Mutual TLS with unique per-device credentials; no universal password or cloud dependency.
- Python CLI and interactive terminal trace/latest views; display filtering, cantools DBC decode/encode library, raw recording, offline playback and CSV export.
- Bounded reusable adapter interface. **No external diagnostic UI adapter is certified or enabled.**

## Host setup

Python **3.11+** for the PC tool. The pinned Zephyr revision requires Python **3.12+** for building firmware. Tests here ran on macOS arm64 with Python 3.14.7.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
python tools/provision.py
```

Provisioning creates private `.secrets/device/` files and `firmware/credentials/device_credentials.h`. It refuses to overwrite an existing credential directory. Read `profile.json` locally for the unique hotspot SSID/password. Do not commit or share the secrets, firmware binary, or build directory: the firmware includes a device private key. Never flash the same identity into multiple devices.

## Build and flash

Pinned Zephyr commit: `737426a187da4b58222665f6427646e092fa9275` (development snapshot **4.4.99**, not a stable release). This revision contains the C5 TWAI-FD driver missing from the pre-existing local checkout. The exact dependency revisions are imported by [west.yml](../west.yml). Tested toolchain: **Zephyr SDK 1.0.1**, RISC-V GCC 14.3.0; west 1.5.0; esptool 5.3.0.

For a new isolated workspace, place this repository at `can-workspace/wireless-can-tool`, then:

```sh
cd can-workspace
west init -l wireless-can-tool
west update
west packages pip --install
west blobs fetch hal_espressif
# Install Zephyr SDK 1.0.1 and make its location discoverable.
west build -b xiao_esp32c5/esp32c5/hpcore wireless-can-tool/firmware -d build
west flash -d build --esp-device /dev/cu.usbmodemYOUR_DEVICE
```

Activate your Zephyr Python environment so `esptool` is on PATH. Generate credentials **before** building. Initial hardware bring-up should be with CANH/CANL disconnected. Firmware starts stopped, but verify SLNT/reset behavior before attaching a live bus. No hardware has been flashed by this implementation session.

Build-time pins are in `firmware/boards/xiao_esp32c5_esp32c5_hpcore.overlay`. Queue sizes and four/five-wire selection are Kconfig options. `CONFIG_WCAN_SLNT=n` enables four-wire operation. See [wiring](wiring.md).

## Connect and run

Join the device's unique AP (no internet). Default device address: **192.168.4.1**, TLS TCP **7443**. Keep the provisioned CA and client key on the PC.

```sh
can-tool discover
can-tool info --device 192.168.4.1
can-tool monitor --device 192.168.4.1 --dbc examples/synthetic.dbc
can-tool monitor --device 192.168.4.1 --fd --data-bitrate 2000000 --view trace
can-tool record --device 192.168.4.1 --output capture.jsonl --include 0x100-0x200
can-tool inspect capture.jsonl --dbc examples/synthetic.dbc
can-tool play capture.jsonl --dbc examples/synthetic.dbc --speed 2
can-tool export capture.jsonl --output capture.csv --format csv
can-tool wifi --device 192.168.4.1 station --ssid MyRouter
```

Router password is prompted without echo. Wi-Fi changes stop CAN, persist the new mode, and reboot. On Station mode, use the router-assigned address or discovery. See [Wi-Fi setup](wifi-setup.md) for `--band 5 --country XX`, supported country codes, AP channels, and actual Wi-Fi 6 status. 5 GHz has not yet been tested on hardware.

TUI keys: **q** quit, **t** chronological trace, **a** latest messages. `--include`, `--exclude`, `--format standard|extended`, `--name` and `--signal` only affect display. Raw recording is unaffected. `--seconds N` limits capture duration.

### Explicit finite transmission

On a properly terminated test bus with a known peer:

```sh
can-tool send --device 192.168.4.1 --allow-tx --id 0x123 --data '01 02 03'
can-tool send --device 192.168.4.1 --allow-tx --fd --brs --extended \
  --id 0x12345 --data '01 02 03 04' --interval-ms 100 --count 10 --output tx.jsonl
```

The command owns one TLS session, explicitly selects active mode, starts CAN, waits for outcomes, then stops. Ctrl-C/disconnect cancels the schedule. CAN hardware is configured for one-shot TX; no application retransmission. Completion is controller completion, **not proof that an actuator executed a command**. Wi-Fi is not a deterministic motor-control loop.

`configure` validates/applies timing and reports it, then disconnects; capture remains stopped and active permission is discarded. Library users can configure/start/send on one connection. The CLI does not preserve active permission between commands.

## No-hardware demonstration

```sh
PYTHONPATH=pc python -m can_tool.simulator --credentials .secrets/device
# In another terminal:
can-tool monitor --device 127.0.0.1
can-tool record --device 127.0.0.1 --output synthetic-live.jsonl --seconds 5
can-tool play examples/synthetic.jsonl --dbc examples/synthetic.dbc
python -m pytest -q
```

The simulator uses actual local TLS sockets but **simulates** the controller. Its recordings are marked synthetic. Playback has no connection to a CAN device and cannot transmit.

## Documentation

- [Protocol](protocol.md), [recording format](recording-format.md), [security](security.md)
- [External tools and adapter interface](external-tools.md)
- [Specification review and decisions](spec-review.md)
- [Tests and next hardware steps](testing.md), [known limits](limitations.md)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)

**Project license is not selected.** The original code has not been given an open-source license yet. Choose a license before publishing it as open source; third-party licenses remain unchanged.
