# External diagnostic tools

## Evaluation result: adapter interface delivered; compatibility pending

No SavvyCAN or Foxglove application was found in the inspected macOS Applications inventory. No end-to-end external tool test was performed. `can-tool bridge --adapter ...` returns a clear unsupported error and nonzero exit status. The built-in CLI/TUI works independently.

### SavvyCAN candidate

Its [connection documentation](https://www.savvycan.com/docs/connectionwindow.html) documents GVRET devices and a host-side virtual device. The [project site](https://www.savvycan.com/) lists Qt SerialBus interfaces and capture/transmission support. This establishes an integration direction, but does not establish that a custom TCP GVRET implementation preserves this tool's CAN FD length/flags and timestamp semantics on the user's macOS build. No GVRET compatibility is claimed. A concrete release, its protocol implementation, CAN FD handling, RX/TX echo behavior, license and macOS packaging must be inspected and exercised before selecting it.

### Foxglove candidate

The [official WebSocket SDK documentation](https://docs.foxglove.dev/docs/sdk/websocket-server) documents a local server and client-to-server message callbacks. A custom schema could carry all raw CAN/FD fields and explicit TX commands. This is a possible generic robotics viewer integration, not evidence of a native CAN diagnostic frontend or verified adapter. SDK/platform availability, exact license, timestamp representation, UI schema configuration and both traffic directions still need checking against a selected installed release. No Foxglove dependency is installed or redistributed here.

## Delivered extension interface

`can_tool.model.DiagnosticAdapter` holds an already-authenticated `Client`. `events` is an `AdapterQueue` with a bounded `queue.Queue`; `publish(event)` never waits and increments `discards` for a slow consumer. Consumers drain it on their own thread. Capture/recording must continue through the core path independently; adapter loss is separate from device capture loss.

`adapter.send(frame, allow_tx=True)` delegates to `Client.send_frame()`. The client must already own an explicitly configured active session. Adapters must not create hidden owners, skip the gate, auto-retry, or replay received/TX-completion events as transmit requests. Raw frames include ID, format flags, channel, DLC/length/payload, boot session, sequence and monotonic callback timestamp. Record PC receipt time separately. Preserve 64-bit integers without floating-point truncation; an eventual timestamp conversion must be documented.

No field conversion/loss exists in this interface itself. No external wire mapping has been implemented. Tests exercise overflow and the explicit adapter send gate, not third-party compatibility.
