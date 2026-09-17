# Known limits

- **No hardware tests yet.** Successful compilation and host simulations do not prove boot, Wi-Fi, CAN electrical behavior, listen-only silence, FD bit timing or sustained throughput.
- Zephyr is pinned to a development snapshot containing the new C5 CAN FD driver. Physical qualification and review of that upstream driver remain necessary.
- One CAN channel; no galvanic isolation. No microSD, USB operational transport, replay-to-CAN, cloud, bootloader/actuator support or automatic diagnosis.
- Callback timestamps use 1 ms kernel ticks, expressed in microseconds. No hardware-accuracy or clock-synchronization claim.
- Hardware filtering is not exposed by this driver; all-ID capture with PC display filters. Hardware RX overrun count and CRC error count remain null because the driver does not expose/update them, even though generic Zephyr APIs have similarly named counters.
- Bounded RAM and TCP buffers cannot absorb unlimited traffic/outages. Queue overflow drops incoming records; a slow/disconnected client stops capture. Hardware losses can precede application sequence numbers.
- High internal-RAM usage. The final build footprint is in testing.md; runtime TLS/Wi-Fi heap and stack margins remain unmeasured. Increasing queue sizes can make the image too large or reduce runtime margin.
- Only one client/control owner. No automatic reconnect; manually reconnect/configure/start. Recent request deduplication is scoped to a TLS connection, not persistent across reboot or reconnect. Uncertain requests must be reconciled by the operator.
- Device TX is one-shot and finite, not deterministic scheduling. Arbitration, bus errors, Wi-Fi lease expiry or the 1 s outstanding deadline can prevent completion. Cancellation cannot retract a frame already sent.
- Active completion means controller completion, not actuator execution. DBC encode does not supply vendor command sequences, checksums or rolling counters.
- Wi-Fi supports WPA2 passphrases with selectable 2.4/5 GHz; enterprise/open Wi-Fi is unsupported. 5 GHz and Wi-Fi 6 negotiation are build-tested only. Country codes are restricted to the pinned HAL documented list (Indonesia ID remains unsupported/unverified); AP 5 GHz is limited to channels 36/40/44/48, with no DFS support. Mode changes reboot; wrong credentials require physical AP recovery.
- Device-side certificate dates/revocation are not checked without a trusted clock. Flash encryption/secure boot/production key protection are not enabled. See security.md.
- External diagnostic UI is an interface and documented blocker, not a verified adapter. `bridge` intentionally fails rather than pretend compatibility.
- DBC containers and AUTOSAR integrity semantics are not supported for commands. Raw frames survive decode errors. Message intervals are descriptive, never proof of missing feedback.
- JSONL is flushed but not fsynced per event. Full disks, process termination or power loss may leave incomplete recordings; reader errors are explicit. CSV is an RX-only export, not a complete event archive.
- macOS is the tested host. Core Python is portable, but Windows/Linux and terminal-specific interaction have not been exercised. The C harness needs a C compiler; Windows may require adaptation.
- The project's own license is undecided; it is not yet legally ready to publish as open-source software.
