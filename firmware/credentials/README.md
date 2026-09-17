# Per-device generated credentials

Generate `device_credentials.h` using `python tools/provision.py`. The header is intentionally ignored and required by the build. There is no shared/example production key. Keep the corresponding private PC profile securely. Reprovisioning requires a new private directory and reflashing the matching header; do not mix profiles and firmware.
