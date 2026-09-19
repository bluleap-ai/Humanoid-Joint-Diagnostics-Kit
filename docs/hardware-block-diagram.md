# Hardware block diagram

Solid connections show the current design. Dashed connections show planned optional SD/RTC additions. Physical hardware validation is pending.

```mermaid
flowchart LR
    PC["PC / laptop<br/>CLI / TUI · decode · record"]
    PSU["Regulated 5 V provider<br/>USB supply / power bank<br/>Source model TBD"]

    subgraph KIT["Humanoid Joint Diagnostics Kit"]
        MCU["Seeed XIAO ESP32-C5<br/>Zephyr firmware<br/>Wi-Fi + native TWAI CAN / CAN FD controller"]
        PWR["XIAO 3V3 output<br/>Peripheral supply rail"]
        CAN["Adafruit CAN Pal · 5708<br/>CAN / CAN FD transceiver<br/>3.3 V Vcc / logic · non-isolated"]
        BIAS["3.3 V → 10 kΩ → SLNT<br/>Recommended reset-silence pull-up"]
        SD["SD card module · planned<br/>Adafruit microSD breakout 4682<br/>3.3 V power / logic"]
        CARD["microSD card<br/>Model / capacity TBD"]
        RTC["RTC module · planned<br/>Select 3.3 V-compatible module<br/>Battery-backed UTC"]
        BAT["RTC backup battery<br/>Type depends on RTC module"]
    end

    BUS["Target CAN / CAN FD bus<br/>CANH · CANL · signal GND<br/>Robot / joint nodes"]

    PC <-->|"Local Wi-Fi · mutual TLS<br/>Direct AP or via router"| MCU
    PSU -->|"5 V via USB"| MCU
    MCU --> PWR
    PWR -->|"3.3 V"| CAN
    PWR --> BIAS
    PWR -.->|"3.3 V"| SD
    PWR -.->|"3.3 V · confirm module compatibility"| RTC
    MCU -->|"TX: D6 / GPIO11 → TX<br/>SLNT: D2 / GPIO25 → SLNT"| CAN
    CAN -->|"RX → D7 / GPIO12"| MCU
    BIAS --> CAN
    CAN <-->|"H ↔ CANH · L ↔ CANL<br/>Common signal ground"| BUS
    MCU -.->|"SPI: CLK D8 / GPIO8 · SO D9 / GPIO9<br/>SI D10 / GPIO10 · CS D1 / GPIO0<br/>Optional DET D0 / GPIO1"| SD
    SD -.->|"Card socket"| CARD
    MCU -.->|"I2C: SDA D4 / GPIO23<br/>SCL D5 / GPIO24"| RTC
    BAT -.->|"Backup power"| RTC

    classDef current fill:#e9f2ff,stroke:#3871b7,color:#163451;
    classDef planned fill:#fff7e6,stroke:#b98522,stroke-dasharray:5 5,color:#60420d;
    classDef external fill:#f1f4f7,stroke:#788797,color:#243546;
    class MCU,PWR,CAN,BIAS current;
    class SD,CARD,RTC,BAT planned;
    class PC,PSU,BUS external;
```

- CAN Pal is a transceiver; the CAN controller is inside the ESP32-C5. No separate SPI CAN controller or level shifter is used.
- SLNT high inhibits physical transmission. The recommended 10 kΩ pull-up goes to the same 3.3 V rail as CAN Pal Vcc; reset behavior still needs measurement.
- Enable the CAN Pal's 120 Ω termination only if it is one of the bus's two endpoints. Leave it off when tapping an already terminated bus.
- USB supplies power and supports flashing/debug; operational communication uses Wi-Fi. The kit does not power the target actuators.
- The 5 V provider feeds the XIAO through USB. Peripheral power comes from its 3V3 output; verify available current under combined Wi-Fi, CAN and SD load before finalizing the supply. The diagram shows one USB power source at a time.
- Join XIAO, CAN Pal, SD and RTC grounds to the supply return and appropriate CAN signal ground. Ground wiring is omitted from individual power arrows for readability.
- SD and RTC interfaces are reserved in the roadmap and currently disabled in the firmware overlay. SPI labels SO/SI refer to the SD breakout. RTC module, supply compatibility and backup battery remain undecided.

Sources: [wiring and reset behavior](wiring.md), [hardware roadmap](roadmap.md#2-hardware-and-reserved-interfaces), and [firmware pin configuration](../firmware/boards/xiao_esp32c5_esp32c5_hpcore.overlay).
