# Recording format v1

UTF-8 JSON Lines, append-only. Files are created exclusively: an existing file is never overwritten. Every event has `type`, `pc_receipt_ns` (PC wall-clock receipt/creation time in nanoseconds), and `data`.

First line: `type:"metadata"`, data containing `format:"wireless-can-jsonl"`, `version:1`, configuration, session, and `synthetic` boolean. Live firmware configuration includes capture filter and timestamp method. Synthetic examples explicitly say so. Integers, including 64-bit session/sequence/device times, must be preserved exactly; JavaScript adapters should avoid floating-point conversion of these fields.

Event types:

- `rx`: identifier, flags, DLC, channel, sequence, timestamp_us, session and lowercase hex `data` bytes. RX only.
- `status`: device status/loss/configuration report, including null unsupported counters.
- `gap`: observed missing sequence count within a session. Does not identify the loss layer by itself.
- `tx_request`: PC intent with raw frame, interval/count; distinct from receipt or completion.
- `tx_event`: device outcome and request association.
- `disconnect`: local close/error and PC queue discards.

No Wi-Fi provisioning packets, passwords, certificates or keys are recorded. PC recording errors raise immediately and stop operation; a full/unwritable disk may prevent writing the error itself. The CLI returns nonzero. Files are flushed per event, **not fsynced**, so power loss can lose buffered OS writes or truncate the final line. The reader rejects invalid/truncated lines and unsupported versions rather than inventing records.

Display filters never change the recording. Failed/missing DBC definitions preserve raw frames. DBC files are supplied separately and not embedded; keep the matching DBC with your recording. Decoder warnings/unsupported container semantics are reported. Manufacturer integrity algorithms are not inferred from DBC encoding.

`inspect` emits JSONL, optionally decoded. `play` displays offline events without creating a network client. Long gaps are capped at two seconds for usability; playback is a visual inspection aid, not timing reproduction. `export --format csv` exports RX rows with device/PC timestamps, session, sequence, raw ID/flags/DLC/length/data and optional decoded fields. TX/status events remain in the source JSONL and are deliberately not mislabeled as RX CSV rows.
