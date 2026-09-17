# WCAN protocol version 1

TLS 1.2 TCP port 7443; mutual certificate authentication. One connected owner at a time. All multibyte integers are unsigned **big-endian**. No compression. Maximum payload 4096 bytes. No USB operational protocol.

## Header (24 bytes)

| Offset | Bytes | Meaning |
|---|---:|---|
| 0 | 4 | ASCII `WCAN` |
| 4 | 1 | Major version, exactly 1 |
| 5 | 1 | Packet type |
| 6 | 2 | Reserved flags, zero |
| 8 | 4 | Payload length |
| 12 | 4 | Request ID; commands require nonzero |
| 16 | 8 | Boot session ID |

The first command is HELLO with session 0, no payload. The response supplies the random nonzero boot session. All subsequent commands must echo it. A different version, invalid header, unknown command type, bad session or missing initial HELLO closes the connection. No best-effort version downgrade.

| Type | Name | Request payload |
|---:|---|---|
| 1 | HELLO | empty |
| 2 | INFO | empty |
| 3 | CONFIGURE | 14 bytes described below |
| 4 | START | empty |
| 5 | STOP | empty; cancels TX and removes active permission |
| 6 | TX | 16-byte prefix + payload |
| 7 | CANCEL | empty; stops channel and cancels entire schedule |
| 8 | WIFI | legacy mode/SSID length/password length, or extended format below |
| 9 | PING | empty; renews lease |
| 128 | RESPONSE | UTF-8 JSON, matching request ID |
| 129 | STATUS | UTF-8 JSON, request 0, about once/second |
| 130 | FRAMES | concatenated RX records, request 0 |
| 131 | TX_EVENT | JSON, associated TX request ID |

Control/status JSON is enclosed in the binary framing; RX records are binary. Response has `ok:true` or `ok:false,error,code` (negative errno when supplied). Configuration/INFO responses contain status and applied timing. An accepted TX response means an application schedule was accepted, not that hardware has transmitted anything. TX events carry request, successful completion count, state, error, terminal flag. States: `completed`, `failed`, `cancelled`, `indeterminate`. A failed/uncertain final event must not be retried automatically.

### Configuration

`fd:u8, active:u8, nominal_bitrate:u32, nominal_sample_point:u16, data_bitrate:u32, data_sample_point:u16`. Booleans must be 0/1. Sample points use per-mille, e.g. 875 = 87.5%. Nominal 10 kbit/s–1 Mbit/s, data 10 kbit/s–5 Mbit/s. Sample points 500–950. These are policy bounds, not a promise that every value is realizable. Firmware uses Zephyr timing calculation, then verifies exact bitrate and sample point using the controller clock. Approximation is rejected. Changes stop CAN, cancel schedules and discard outstanding transport records (counted). START is explicit. Invalid configuration leaves START disabled until a valid configuration is applied.

Hardware acceptance-filter configuration is **unsupported in this driver API**. The firmware installs two disjoint software filters covering all standard and extended frames. `hardware_filters:null` and `capture_filter:"all_standard_and_extended"` document that fact. Display filters reside on the PC and are unrelated.

### RX records

`sequence:u64, timestamp_us:u64, identifier:u32, channel:u8, flags:u8, dlc:u8, length:u8, data:length`. Session is inherited from the enclosing packet. Channel is 0. Flags: bit 0 extended, bit 1 FD, bit 2 BRS, bit 3 ESI, bit 4 RTR; other bits must be zero.

FD DLC maps to lengths `[0,1,2,3,4,5,6,7,8,12,16,20,24,32,48,64]`. FD cannot be RTR. Classical receive DLC 9–15 means 8 bytes; RTR has zero payload with a requested DLC preserved. Classical TX DLC >8 is rejected. BRS/ESI require FD. ESI cannot be set in a TX request; hardware owns it. Standard IDs ≤0x7ff, extended ≤0x1fffffff. Illegal lengths are rejected rather than padded.

Sequence starts at 1, assigned at receive callback entry before queue insertion, and continues across capture starts within one boot. A new boot changes session. The application counts only frames delivered by the driver, not all frames on the wire. Timestamp method is `callback_kernel_ticks_us`, currently **1000 µs resolution**, converted from monotonic kernel ticks. It is not the truncated 16-bit Zephyr hardware timestamp and not exact wire-arrival time. PC receipt time is separate wall-clock nanoseconds; clocks are not synchronized.

### TX prefix

`interval_ms:u32, count:u32, identifier:u32, flags:u8, dlc:u8, length:u8, reserved:u8` followed by payload. Reserved=0. Count 1–10000. Interval 0–60000; count >1 requires interval ≥10 ms. One schedule, at most one driver TX outstanding. Schedule uses device time, no catch-up bursts. CAN one-shot mode disables automatic hardware retransmission; a frame can fail due to arbitration or bus error. A one-second outstanding-TX deadline stops the channel and reports indeterminate. No real-time timing guarantee.

### Ownership, lease, duplicates

Ownership is the authenticated TCP connection; observers should attach to the owning PC library, not open another device control connection. Every fresh command must have an increasing uint32 request ID; scope is the TLS connection. The most recent request (up to 96 payload bytes) and its response are cached. An identical immediate duplicate gets the original response; a changed or older duplicate is rejected without execution. Longer requests cannot be retransmitted using the cache. ID exhaustion requires a new explicit connection.

PING every 500 ms is the PC default. Three seconds without a complete command expires the lease and stops capture/TX; the independent scheduler enforces this even if a network write blocks. Disconnect stops CAN, asserts SLNT when available and clears active permission. STOP/CANCEL do likewise. Reconnect never resumes active mode or resends an uncertain request. A frame already placed on the bus cannot be withdrawn; in-flight cancellation is indeterminate.

### Backpressure and loss

Receive ISR callback copies full frames to a bounded internal-RAM queue (default 128), K_NO_WAIT; incoming frames are dropped on overflow. It does no allocation, formatting, socket or filesystem work. The server/batching task drains at most 16 records per packet. Slow writes have a finite timeout, after which capture stops. A failed/partial batch send counts every record in that batch as a transport discard (conservative: some may have reached the PC). Queued records discarded at disconnect/reconfiguration are also counted. Successful TCP write does not prove PC recording.

Status includes software counters, queue depth/high-water, last sequence, controller state, current REC/TEC, driver-reported bit/stuff/form/ACK error counts, Wi-Fi mode/error/IP, versions, session and applied timing. Hardware receive losses and CRC error-event count are null because the pinned driver does not expose/update them reliably. Counters have boot scope unless the driver resets its own error statistics. A recording may end before final status arrives. Zero software drops is never evidence of lossless operation.

Partial headers/bodies are buffered; multiple packets per read are parsed. Header length is checked before reading a body. Incomplete packets expire after two seconds. Maximum application buffers are fixed. PC event queue is bounded; overflow raises an error, closes transport and marks recording incomplete rather than silently dropping frames.

### Extended WIFI payload

Header bytes: `[0x80 | mode, ssid_length, password_length, band, channel, country0, country1]`, followed by SSID then password bytes. Mode is 0 AP / 1 Station; band is 0 for 2.4 GHz / 1 for 5 GHz. Country is two uppercase ASCII letters from the pinned HAL supported list, or two zero bytes for the default 2.4 GHz world domain. 5 GHz requires an explicit supported country. Channel 0 selects Station scanning or AP default; AP permits 1–11 (2.4 GHz) or 36/40/44/48 (5 GHz). Station requires channel 0. AP uses embedded unique credentials and requires both credential lengths zero. See wifi-setup.md for country restrictions.

Legacy unmarked three-byte headers remain accepted as 2.4 GHz. Extended payloads preserve protocol version 1 because old firmware rejects their invalid mode byte without applying settings. Never record either payload. Credentials, band, channel and country are saved atomically; successful response schedules a stopped-CAN reboot, not proof of connection. INFO includes `wifi_provision_version: 2` for this extension.

Network status adds requested/actual band, actual channel, negotiated Station PHY and configured country. Actual band/PHY are null when unknown; channel 0 is unknown. The existing `wifi_error` carries a negative errno or negated Espressif radio configuration error.
