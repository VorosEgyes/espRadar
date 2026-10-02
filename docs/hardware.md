# Hardware

## Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | Wemos D1 mini (ESP8266, 4 MB flash) | the MCU |
| 1 | Hi-Link HLK-LD2420 | 24 GHz FMCW mmWave radar, 16 gates × 0.70 m |
| 1 | USB cable (micro-USB or USB-C depending on D1 mini variant) | for power + flashing |
| 1 | USB charger or 5 V / ≥ 0.5 A supply | the D1 mini's on-board LDO supplies 3V3 to the LD2420 |
| 4 | Female-to-female jumper wires | for TX/RX/VCC/GND |
| 1 (optional) | 3D-printed case | see `docs/case.stl` (TODO) |

Approximate BoM cost: 8 € HWY / 8 € EU.

## Wiring

```
                D1 mini (top view, USB on top)
              ┌──────────────────────────┐
              │  [USB]      RST          │
              │                            │
   LD2420 ────┤  D1 (GPIO5)                │
   TX    ────►  D2 (GPIO4)                │
              │  D3 (GPIO0)  ─► FLASH BTN  │
              │  D4 (GPIO2)  ─► LED       │
              │                            │
              │  3V3  ●──────────────● VCC │ ◄── LD2420 VCC
              │  GND  ●──────────────● GND │ ◄── LD2420 GND
              │                            │
   LD2420 ────┤  D7 (GPIO13)  ◄──────── TX │ ◄── LD2420 TX  (ESP-side RX)
   RX    ────►  D8 (GPIO15)  ──────────► RX │ ──► LD2420 RX  (ESP-side TX)
              │                            │
              └──────────────────────────┘
```

**Crossing the wires is correct.** TX from the LD2420 must go to the D1 mini's RX (D7), and vice versa.

## Why D7/D8 (GPIO13/GPIO15)

- GPIO1 / GPIO3 (UART0) is used by the **serial bootloader** and by the **logger**. If we tied the LD2420 to those, we would either lose logs (`baud_rate: 0`) or break OTA updates.
- The upstream LD2420 ESPHome component supports **any** UART. We use D7/D8 and disable the logger's serial output (`logger.baud_rate: 0`).

## Power budget

- D1 mini: ~70 mA @ 3V3 (ESP8266 active, Wi-Fi connected)
- HLK-LD2420: average 50 mA, peak 100 mA
- Headroom on the D1 mini `3V3` pin: ~400 mA — comfortable margin.

## Mounting tips

- The LD2420 has a **wall-mount orientation** and a **ceiling-mount orientation**. The detection cone is ±60° from the long axis of the PCB.
- **Wall mount** (typical): PCB horizontal, antenna facing out. Maximum detection range 8 m (moving), 6 m (still).
- **Ceiling mount**: PCB horizontal, antenna facing down. Maximum range 5 m (moving), 4 m (still).
- Keep **at least 30 cm of free space** around the antenna; metal surfaces behind the radar block the cone.

## Photos

TODO: real photos of the assembled device in the `docs/` folder.