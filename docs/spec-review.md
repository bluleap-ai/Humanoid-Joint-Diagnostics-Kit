# Specification review and implementation choices

The original specification is internally coherent. The later request to use **Zephyr** supersedes the ESP-IDF/FreeRTOS requirement. Firmware uses Zephyr native CAN, kernel queues/threads, networking/TLS sockets and settings. ESP-IDF is not an application dependency; Espressif's HAL/radio libraries are Zephyr dependencies with their own licensing.

Decisions made where the specification left room:

1. Pin a Zephyr development commit containing XIAO C5 and native TWAI-FD support. Do not modify the user's existing Zephyr checkout. Build in a separate workspace. Stable-release qualification remains future work.
2. Per-device build-time mutual TLS credentials created on the trusted PC; no universal AP password. USB is used for flashing these credentials, never operational commands.
3. One owning connection with PC-side fan-out; no multiple device observer sockets. Explicit scoped active transmission via `send` or library APIs.
4. Stop capture and cancel TX on disconnect rather than promise indefinite offline buffering. Resume requires a fresh explicit configuration/start. Session spans a boot; sequence spans start/stop within that session.
5. Exact timing only: reject sample point/rate approximation. Sample points are per-mille. The built-in timing solver's choices can be more restrictive than hardware's theoretical capabilities.
6. Use callback kernel-tick timestamps because the public Zephyr hardware timestamp is truncated to 16 bits. Microsecond units currently have millisecond resolution; no wire-time accuracy claim.
7. The selected driver implements receive filter matching in software. V1 captures all standard/extended IDs, reports hardware filters as unsupported, and provides separate PC display filters.
8. Bounded periodic TX lives on device: minimum 10 ms interval, maximum 10000 requests, at most one outstanding frame, one-shot hardware TX. No catch-up bursts, and a 1 s outstanding-frame deadline.
9. Single AP or Station mode selected through persisted configuration and reboot. WPA2 PSK, selectable 2.4/5 GHz; see wifi-setup.md for country/channel restrictions. Boot/recovery defaults to 2.4 GHz. Physical recovery uses the BOOT button **after boot/release** to avoid strapping conflicts.
10. Versioned binary framing with compact binary frames and JSON control/status responses; JSONL recording for readable inspection and robust raw metadata preservation.
11. cantools handles DBC signedness, byte order, scaling, offsets, units, choices and multiplexing. Container/AUTOSAR integrity command construction is rejected. No manufacturer checksums/counters are invented.
12. External UI evaluation did not establish end-to-end compatible installed software; deliver the bounded adapter interface and document that blocker rather than ship an unverified bridge.
13. Original project license remains undecided; no unrelated files existed at initial inspection. Third-party code is not relicensed.

Hardware availability/flash permission was not confirmed during implementation. Therefore no flash, boot, RF, electrical, reference-adapter or actuator test is claimed. The user's available XIAO/CAN Pal is enough for future power/boot/AP testing, but passive physical CAN validation needs a functioning source bus with ACK-capable peers.
