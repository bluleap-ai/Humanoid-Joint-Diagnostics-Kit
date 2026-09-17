# Third-party notices

No third-party licenses are replaced by this project. Dependencies are fetched by their package managers, not copied into the original application source tree. Preserve upstream licenses when distributing dependency source, linked firmware, or binary packages.

| Dependency | Pinned version/revision | License / notice |
|---|---|---|
| Zephyr | `737426a187da4b58222665f6427646e092fa9275` | Apache-2.0 and per-file upstream notices |
| hal_espressif | `e6d4a9c9c6247326934a4a7c5bd40c037f84b469` | Mixed Espressif/upstream source and binary-library terms; inspect module LICENSE and blob metadata before redistribution |
| Mbed TLS | `c43f34b93797e81fd0257c30004dcd0ae332ae51` | Upstream Apache-2.0/GPL-2.0-or-later dual-license terms, per-file notices |
| TF-PSA-Crypto | `765af96a20a2b408474dcd950372ba9af4d26b62` | Upstream dual-license and third-party notices |
| zcbor | `9164bd18dcd88ff9d9ef98279501fc1093571017` | Apache-2.0 |
| cantools | 41.0.0 | MIT; DBC parser and encoder |
| rich | 14.1.0 | MIT; terminal rendering |
| zeroconf | 0.147.0 | LGPL-2.1-or-later; discovery, preserve its redistribution obligations |
| cryptography | 45.0.7 | Apache-2.0 OR BSD-3-Clause; provisioning certificates |
| pytest | 8.4.2 | MIT; development tests |

Python transitive dependency versions are captured in `requirements.lock`; their installed `.dist-info/licenses` or metadata contain authoritative license texts. cantools transitively installs python-can (LGPL-3.0-or-later); this application does not use python-can as its transport. Inspect all transitive notices for distribution. Zephyr's vendor radio binaries are not made open-source by linking them into this application.

References reviewed: [cantools repository](https://github.com/cantools/cantools), [Zephyr](https://github.com/zephyrproject-rtos/zephyr), [Espressif HAL](https://github.com/zephyrproject-rtos/hal_espressif), [Mbed TLS](https://github.com/zephyrproject-rtos/mbedtls). Dependency metadata was inspected locally.

Original application code and synthetic fixtures: **license choice pending from project owner**. No LICENSE file granting public reuse has been invented.
