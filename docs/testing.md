# Test evidence and hardware qualification

## Environment

Implementation/test date: 2026-09-16, macOS arm64, Python 3.14.7. Firmware target `xiao_esp32c5/esp32c5/hpcore`. Zephyr `737426a187da4b58222665f6427646e092fa9275`, Zephyr SDK 1.0.1, RISC-V GCC 14.3.0, west 1.5.0, esptool 5.3.0. Dependency versions are pinned in west.yml and requirements.lock.

The pre-existing Zephyr checkout was read only. A separate checkout/workspace under `/tmp/can-tool-ws` was used. Network downloads required sandbox approval. Local TCP tests initially could not bind inside the sandbox; they were rerun with permission to bind localhost. No physical device access was used.

## Automated checks actually performed

Final run: **126 passed in 20.48 seconds**, zero failures/skips (`pytest-results.xml`). Firmware compilation, linking and ESP32-C5 image generation succeeded (`build-log.txt`).

Final linked footprint: FLASH **803456 / 8388352 bytes (9.58%)**; SRAM **345984 / 378384 bytes (91.44%)**. This is link-time allocation, not measured runtime heap/stack headroom. The locally generated `build/zephyr/zephyr.bin` SHA-256 is `4d8d972b21c76351f39628f4e658bf2b1d64be225d0ef156516564e605f14a3a`; regenerating private credentials changes the image. Do not distribute this credential-bearing binary.

A repeated pre-final run exposed a socket teardown/read race: the saved recording remained intact, but a concurrent TLS operation could consume bytes from a reused descriptor while the recording was read. Socket operations and teardown are now serialized, and close waits for the reader to exit. The final suite includes a deterministic in-flight-read/close regression and ten independent TLS capture/record/export repetitions. These tests establish the exercised behavior, not a general lossless guarantee.

The suite includes:

- Wi-Fi extended provisioning C/Python round trips (actual wifi_config.c compiled on host), truncated/malformed payloads, legacy 2.4 GHz payload compatibility, supported-country/band/channel validation and CLI option parsing. These do not exercise the radio HAL, NVS, or RF.
- All legal FD lengths, Classical/RTR rules, invalid IDs/flags/lengths, frame round trips.
- 49 fragmentation boundaries, concatenated packets, malformed headers, version mismatch and oversized/truncated records.
- Host compilation of the actual `firmware/src/wire.c`, 500 deterministic C/Python validation comparisons and binary record comparison.
- Host compilation of the actual `capture.c` against a deterministic fake HAL/kernel queue. Application tests cover owned RX copies/overflow, gaps, explicit active mode, busy schedule rejection, stop/start listen-only regression, lease expiry, invalid timing and outstanding-TX timeout. **This is not Zephyr scheduler or hardware execution.**
- Sequence gaps/session resets; standard/extended distinction; display ranges/exclusions/names; bounded trace/latest data.
- Synthetic DBC fixtures: signed little/big endian, scaling/offset, units, enumeration, multiplexing, encode/decode and malformed/no-match handling.
- JSONL round trip, CSV export, version rejection, exclusive file creation and explicit recording failure.
- Simulated ownership, duplicate/stale request rejection, cancellation, reconnect and lease expiry. These state-machine tests use the Python simulator; they do not execute the firmware TCP server.
- Real localhost mutual TLS with deliberately fragmented writes: capture/reconnect, TX completion, missing client certificate and wrong server identity rejection, slow-host queue overflow shutdown.
- CLI capture-to-recording with a display filter that excludes all frames, proving raw recording is retained; offline CSV export; TX intent and completion request-ID association.
- Slow external-consumer queue and adapter TX permission gate. No external application compatibility test.

Also performed: editable Python package install; `can-tool --help`; `can-tool inspect` with the synthetic DBC; `can-tool export` to CSV; `pip check`; Ruff lint/format; ESP32-C5 firmware compilation/link/image generation.

A build is not a flash/boot result. Host TLS tests are not embedded TLS validation. No throughput, latency, RF range, bus timing accuracy or zero-loss operating envelope has been measured.

## Reproduce

```sh
python -m pytest -q --junitxml=docs/pytest-results.xml
ruff check pc tools tests
ruff format --check pc tools tests
```

The C tests need a host compiler (`cc`). Ruff used here: 0.14.2 (optional development tool). Tests creating a localhost TCP listener need permission in restricted environments. Credential fixtures use temporary, unique certificates; no live device is contacted. Build instructions are in README.md; the build log records the final image footprint. Credentials are excluded from the public test/build logs.

## Hardware tests actually performed

**None.** Flash permission/device connection was not confirmed. No physical CAN peer/reference adapter or external diagnostic UI was available/verified for testing. The following is a pending checklist, not a success report.

| Test | Status | Required evidence |
|---|---|---|
| Flash, boot and reset | Pending | USB logs, exact binary hash, board revision |
| SLNT during power-up/reset/flash | Pending | Scope traces; 10 kΩ bias and four/five-wire distinction |
| AP + authenticated TCP | Pending | Address, association, mutual TLS rejection checks |
| 5 GHz Station/AP and Wi-Fi 6 | Pending | Actual operating country, router/client model, channels, reported band/PHY, association and throughput; ID country support remains unverified |
| Station, NVS persistence, reconnect | Pending | Router model/config, reboot and credential failure logs |
| BOOT-button AP recovery | Pending | Release/hold sequence after startup; no strapping conflict |
| Internal controller self-test | Pending | Explicit loopback test build; distinguish from physical bus |
| Classical known-source RX | Pending | Numbered source/recording comparison |
| CAN FD, 64-byte payloads | Pending | Reference controller/firmware, nominal/data timing, counts |
| Standard/extended/RTR/BRS/ESI | Pending | Source vectors and captured raw fields |
| Listen-only behavior | Pending | Analyzer/scope evidence of no ACK/active error/TX |
| Active finite TX, cancel, lease | Pending | Bus-side transmitted count and failure/uncertain outcomes |
| Wi-Fi interruption/recovery | Pending | Visible gaps/discards, stopped state, no auto-resume |
| Overload/memory stress | Pending | Source counts, queue high-water, drops, heap/stack margin |
| External UI | Blocked | Select/install release, inspect interface, bidirectional test |

## Exact next validation procedure

1. Confirm XIAO connected and authorize flashing. Keep CAN bus disconnected. Build with the matching private profile, flash, record boot logs and measure idle current/stack/heap margin. Check AP and authenticated INFO first.
2. Wire CAN Pal per wiring.md, including recommended SLNT bias. Measure reset silence. Test Station provisioning/restart and physical AP recovery before any active bus operation.
3. Obtain a reference CAN FD adapter and an ACK-capable peer or an already functioning bus. A passive listener cannot provide ACK. Verify two endpoint terminations, cable/stub lengths and common ground.
4. Generate monotonically numbered payloads at recorded rates for at least 60 seconds each. Start with 500 kbit/s Classical, then FD 500 kbit/s / 2 Mbit/s, 8/12/16/32/64 bytes, alternating standard and extended IDs. Record source count, every payload number, device status, PC receipt and raw recording. Escalate load in documented steps.
5. Compare source sequence numbers with recording; distinguish source failures, bus errors, unobservable hardware losses, application queue drops, transport discards and PC errors. Zero application drops alone is insufficient.
6. Test active finite TX separately with safe synthetic IDs and a reference receiver. Count actual on-bus frames, cancel mid-schedule, remove Wi-Fi, stop heartbeats and reset. Never silently enable active mode for a passive reception test.
7. Publish a measured envelope only for the exact reference adapter, firmware hashes, topology, bitrates/sample points, frame mix/load, AP/Station network, duration and PC version used. No results are populated until measured.
