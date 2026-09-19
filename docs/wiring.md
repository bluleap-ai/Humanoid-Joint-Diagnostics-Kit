# Wiring and reset behavior

For the selected XIAO, CAN Pal, microSD, DS3231 RTC and DC-DC power modules, see the [top-view wiring picture and complete connection table](hardware-block-diagram.md). SD and RTC remain planned firmware extensions.

Verified against the [Seeed XIAO ESP32-C5 pin map](https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/) and the pinned Zephyr board connector definition:

| XIAO | CAN Pal | Firmware |
|---|---|---|
| 3V3 | Vcc | 3.3 V board power/logic |
| GND | GND | Common ground |
| D6 / GPIO11 | TX | TWAI0 TX |
| D7 / GPIO12 | RX | TWAI0 RX |
| D2 / GPIO25 | SLNT | Recommended; high disables physical transmission |

The overlay disables UART0, which otherwise uses GPIO11/12. USB Serial/JTAG remains the development console. CAN Pal generates its transceiver supply internally; **no level shifter or RX divider** is required with Vcc at 3.3 V. See [Adafruit product 5708](https://www.adafruit.com/product/5708).

## Four wires or five

- Five-wire default: GPIO25 drives SLNT high before CAN initialization. It stays high while stopped/passive and goes low only after explicitly starting active mode.
- Four-wire: set `CONFIG_WCAN_SLNT=n`; leave SLNT unwired. Listen-only is enforced by the CAN controller. Status reports `hardware_silent:false`. There is no independent GPIO-controlled hardware inhibition during reset.

## Reset-time protection

Reviewed [Adafruit Eagle schematic](https://github.com/adafruit/Adafruit-CAN-Pal-PCB/blob/56618b3a53162ce48872514be044eab033ed33ef/Adafruit%20CAN%20Pal%20Breakout.sch), commit `56618b3a53162ce48872514be044eab033ed33ef`: `CAN1_S` connects IC1 S directly to header JP2 pin 3. There is **no external board pull-up** on that net.

For five-wire use, add a **10 kΩ resistor from SLNT to the same 3.3 V/Vcc rail** to hold silent mode while GPIO25 is high impedance during reset. This is an engineering recommendation based on the schematic and NXP electrical limits, not a measured boot guarantee: S requires at least 0.7×VIO and its specified high-level input current is at most 10 µA, giving approximately 0.1 V drop across 10 kΩ. GPIO leakage and supply sequencing still require measurement. This resistor is a silent-control bias, not a level converter. [NXP TJA1051 datasheet, mode control input limits](https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf).

Firmware alone cannot establish the reset-time signal before it runs. Verify SLNT and CANH/CANL with an oscilloscope across reset, flashing and power cycling before connecting to a sensitive bus.

## Bus side

Connect H to CANH, L to CANL, and an appropriate bus signal ground to CAN Pal ground. The module is **not galvanically isolated**. Use a short twisted pair and short tap stub.

Turn termination ON only when this module supplies one of the bus's two endpoint 120 Ω terminations. Leave it OFF on an already terminated bus. A passive listener does not ACK; a functioning physical test bus needs appropriate active nodes. Do not enable active mode to hide missing test equipment.

The transceiver's specified FD data-phase ceiling is 5 Mbit/s; firmware rejects higher requested rates. Cable length, sample points, reference adapter, power and sustained throughput remain unvalidated.
