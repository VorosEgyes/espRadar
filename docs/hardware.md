# Hardware

## Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | Wemos D1 mini (ESP8266, 4 MB flash) | the MCU |
| 1 | Hi-Link HLK-LD2410 (or LD2410B / LD2410C) | 24 GHz FMCW mmWave radar, 9 gates × 0.75 m (at default 0.75 m resolution). C variant also has BLE, not used here. |
| 1 | USB cable (micro-USB or USB-C depending on D1 mini variant) | for power + flashing |
| 1 | USB charger or 5 V / ≥ 0.5 A supply | the D1 mini's USB 5 V input is fed directly to the **5V** rail on the header; this is what powers the LD2410 (BL-05) |
| 4 | Female-to-female jumper wires | for TX / RX / VCC (5V) / GND |
| 1 (optional) | 3D-printed case | see `docs/case.stl` (TODO) |

Approximate BoM cost: 7 € HWY / 7 € EU.

> **Critical wiring note (BL-05).** The LD2410 **must be powered from the D1 mini's 5V rail**, NOT 3V3. Some Hi-Link LD2410 batches (and most clone modules) require 5 V for reliable UART signal levels; on 3V3 the UART may appear alive on power-up but no communication happens (`Firmware version` text_sensor stays `NA`, all per-gate energy sensors stay `NA`, `Detection distance` stays `NA`). This is the most common first-build failure mode for the v1.1.0 firmware; the symptom looks like a wiring fault (TX/RX reversed) or a baud-rate mismatch. Check the `LD2410 MAC` text_sensor first — if it is `NA`, the LD2410 is not communicating, and 5V-on-VCC is the first thing to verify.

## Wiring

```
                D1 mini (top view, USB on top)
              ┌──────────────────────────┐
              │  [USB]      RST          │
              │
              │  D1 (GPIO5)
   LD2410 ────┤  D2 (GPIO4)               ── (not used)
              │  D3 (GPIO0)  ─► FLASH BTN
              │  D4 (GPIO2)  ─► LED
              │
              │  5V  ●──────────────● VCC │ ◄── LD2410 VCC  (BL-05: 5V, NOT 3V3)
              │  GND ●──────────────● GND │ ◄── LD2410 GND
              │
   LD2410 ────┤  D7 (GPIO13)  ◄──────── TX │ ◄── LD2410 TX  (ESP-side RX)
   RX    ────►  D8 (GPIO15)  ──────────► RX │ ──► LD2410 RX  (ESP-side TX)
              │
              └──────────────────────────┘
```

**Two non-obvious details:**

1. **Crossing the wires is correct.** TX from the LD2410 must go to the D1 mini's RX (D7), and vice versa. The D1 mini "TX" label (D8 / GPIO15) means *the D1 mini transmits to the LD2410*, not "the D1 mini receives from a TX-labeled device".

2. **5V on VCC, not 3V3** (BL-05). The D1 mini's `5V` header pin is fed directly from the USB input (it bypasses the on-board 3V3 LDO). The `3V3` header pin is the regulated 3.3 V output. The LD2410 needs 5 V; using 3V3 leads to the silent-no-communication symptom described above.

## Why D7/D8 (GPIO13/GPIO15)

- GPIO1 / GPIO3 (UART0) is used by the **serial bootloader** and by the **logger**. If we tied the LD2410 to those, we would either lose logs (`baud_rate: 0`) or break OTA updates.
- The D1 mini has only one free UART pair (D7/D8 = UART1 = `Serial1`). GPIO16 is not a UART pin on the ESP8266.
- The upstream LD2410 ESPHome component supports **any** UART. We use D7/D8 and disable the logger's serial output (`logger.baud_rate: 0`).

## Power budget

- D1 mini: ~70 mA @ 3V3 (ESP8266 active, Wi-Fi connected) — for the MCU only
- HLK-LD2410: average 50 mA, peak 100 mA — powered from the **5 V** rail (USB-direct, not through the LDO)
- USB charger / supply: needs to provide **at least 500 mA** total (D1 mini + LD2410 + headroom for the D1 mini's on-board LDO)

## Mounting tips

- The LD2410 has a **wall-mount orientation** and a **ceiling-mount orientation**. The detection cone is ±60° from the long axis of the PCB.
- **Wall mount** (typical): PCB horizontal, antenna facing out. Maximum detection range 6 m (moving), 4.5 m (still) at default 0.75 m resolution; up to 3.2 m at 0.2 m resolution (finer gates, shorter range).
- **Ceiling mount**: PCB horizontal, antenna facing down. Maximum range 4 m (moving), 3 m (still) at default 0.75 m resolution.
- Keep **at least 30 cm of free space** around the antenna; metal surfaces behind the radar block the cone.

## UART protocol notes

- The LD2410 firmware out-of-the-box baud rate is **256000** (8-N-1). The `substitutions.ld2410_baud` in `firmware/livingroom.yaml` must match.
- The LD2410 reports per-gate energy (`g0..g8.move_energy` / `still_energy`) only when `engineering_mode` is on. Engineering mode auto-disables after 5 minutes (Hi-Link firmware spec). To use the per-gate sensors, switch it on via the web UI or openHAB.
- The LD2410 persists every `set_*` (timeout, max_move_distance_gate, per-gate thresholds, etc.) to its EEPROM automatically. There is no separate `apply_config` button (unlike the LD2420 v1.0.0 firmware).

## See also

- `README.md` — project overview, flashing instructions
- `firmware/livingroom.yaml` — the actual configuration
- `RELEASE_CHECKLIST.md` — BL-01 / BL-01a / BL-01b / BL-02 / BL-03 / BL-04 (toolchain, libstdc++ workaround, register_listener binding, preflight guards) and BL-05 (this 5V supply note)