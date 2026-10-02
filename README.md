# espRadar — D1 mini + HLK-LD2410 mmWave radar for openHAB

Hi-Link HLK-LD2410 24 GHz mmWave human-presence radar wired to a **Wemos D1 mini (ESP8266)** and exposed to **openHAB 5.x** via the ESPHome Native API. No MQTT broker required.

This is the home-automation companion to the `BirdNest` / `RaisedGarden` VorosEgyes project family — same firmware + device-class conventions, no separate cloud, fully local.

> **v1.0.0 used the LD2420 module (16 gates, 115200 baud). v1.1.0+ uses the LD2410 (9 gates, 256000 baud).** The v1.0.0 firmware is still available on the [GitHub Releases page](https://github.com/VorosEgyes/espRadar/releases/tag/v1.0.0) for any node wired to an LD2420. The pinout is identical between the two modules.

---

## Features

- **Presence detection** (moving + still targets, 16 configurable gates)
- **Moving distance** in centimetres
- **Per-gate energy sensors** (`gate_energy_0`…`gate_energy_15`) for fine tuning
- **Dynamic calibration** (Normal / Calibrate / Simple modes; firmware ≥ v1.5.4 required)
- **Calibration UI** in openHAB (select, number, button entities) — no manual UART poking
- **Firmware version** reporting
- **OTA updates** through ESPHome dashboard
- **USB powered** — no deep-sleep, always-on.
- **DHCP networking** — router-side MAC reservation gives every node a stable IP without baking per-node config into the binary.

---

## Hardware

| Part | Notes |
|---|---|
| Wemos D1 mini (ESP8266, 4 MB flash) | the MCU |
| Hi-Link HLK-LD2410 (or LD2410B / LD2410C) | 24 GHz FMCW mmWave radar, 9 gates × 0.75 m (at default 0.75 m resolution). C variant also has BLE, not used here. |
| USB 5 V / 1 A supply | powers the D1 mini; the LD2410 draws from the **5V rail** (USB-direct, NOT the 3V3 LDO) — see BL-05 below |
| 4 jumper wires | TX / RX / VCC (5V) / GND |

**Wiring table** (D1 mini `D7`/`D8` is GPIO13/GPIO15 — kept off UART0 so the logger can use it):

```
LD2410  →  D1 mini
─────      ──────
TX       →  D7   (GPIO13)   ESP-side RX
RX       →  D8   (GPIO15)   ESP-side TX
VCC      →  5V    (BL-05: NOT 3V3)
GND      →  GND
```

> **Critical (BL-05).** The LD2410 **must be powered from the D1 mini's 5V rail**, NOT 3V3. Some Hi-Link LD2410 batches (and most clone modules) require 5 V for reliable UART signal levels; on 3V3 the UART appears alive on power-up but no communication happens — every text_sensor and per-gate energy sensor stays `NA`. The D1 mini 5V rail is fed directly from the USB input (it bypasses the on-board 3V3 LDO) and can source the LD2410's 50 mA average / 100 mA peak. If your `Firmware version` and `LD2410 MAC` text_sensors are `NA`, this is the first thing to verify.

For full hardware details (why D7/D8, power budget, mounting tips, UART protocol notes), see [`docs/hardware.md`](docs/hardware.md).

## Network setup

Every node uses **DHCP**. To give each node a stable IP, set a **MAC reservation on the DHCP server** (your router, or a Pi-hole, or whatever) — do not bake static IPs into the firmware. Re-flashing a node will then never collide with another node's IP, and every firmware file looks identical.

The D1 mini MAC is printed on the silkscreen under the USB connector. Bind each MAC to the IP you want the node to live on.

---

## Firmware

Built with **ESPHome 2026.9.1** (the upstream `ld2420` component has been merged since 2023-11 and gets the maintenance fixes every release, e.g. 2025-11.0 `[ld2420] Eliminate substr() allocation in firmware version parsing`).

> ⚠️ **Toolchain workaround (BL-01b).** ESPHome 2026.9.1
> hard-codes `cg.set_cpp_standard("gnu++20")` and rejects any
> Arduino framework < 3.0.0. The default `toolchain-xtensa@3.x`
> (gcc 10.3.0) supports gnu++20, but its libstdc++10 `<tuple>` /
> `<hashtable_policy.h>` assume `std::size_t` is in scope by the
> time they are first parsed — and ESPHome's `component.h` →
> `<functional>` include chain does not guarantee that. The build
> dies with `'std::size_t' has not been declared` cascading
> through `<hashtable_policy.h>` and `<tuple>`.
>
> The fix is a single flag in `firmware/livingroom.yaml`:
>
> ```yaml
> esphome:
>   platformio_options:
>     build_flags:
>       - -include stddef.h
> ```
>
> This pre-includes `<stddef.h>` in every translation unit, so
> `std::size_t` is in scope before any toolchain header is
> parsed. `stddef.h` (not `cstddef`!) because the toolchain
> also builds `.c` files (e.g. ESPAsyncTCP/tcp_axtls.c) which
> only have the C standard library; `cstddef` is C++-only and
> those TUs would fail with
> `cstddef: No such file or directory`. `scripts/preflight.py`
> `check_6_cstddef_workaround` (the name keeps the BL-01b
> provenance) plus `check_6b_platformio_options_structure`
> guard against the flag ever being removed or `cstddef` being
> substituted. See `RELEASE_CHECKLIST.md` BL-01 / BL-01a /
> BL-01b for the full diagnosis history (the earlier
> `espressif8266@2.6.3` pin from BL-01 turned out to be
> structurally incompatible with the current ESPHome because
> the gcc 5.2 toolchain cannot compile C++20).

The YAML lives in `firmware/livingroom.yaml`. Copy `firmware/secrets.yaml.example` to `firmware/secrets.yaml` and fill in Wi-Fi + openHAB `api:` encryption key before flashing.

```bash
cd firmware
# first time, or after a toolchain change:
../scripts/clean.sh
# every time, before flashing:
../scripts/preflight.py
esphome run livingroom.yaml     # first flash via USB
esphome run livingroom.yaml     # later: OTA after Wi-Fi is up
```

The custom component `components/ld2420_energy/` adds the 16 gate-energy sensors. It hooks into the upstream `LD2420Component` through the `LD2420Listener::on_energy()` interface that the parent already calls on every parsed energy frame (Normal mode, firmware ≥ v1.5.4, ~10 Hz). **No upstream fork is required.**

---

## openHAB integration

Uses the third-party **[seime/openhab-esphome](https://github.com/seime/openhab-esphome)** binding (MIT, currently `[4.0.0.0;6.0.0.0)` — openHAB 5.1.3 ✓).

### 1. Install the binding

The binding has an **unmet dependency** on the `bluetooth` binding even if you do not use it; install both:

```text
openhab> feature:install openhab-transport-serial
openhab> bundle:install https://github.com/seime/openhab-esphome/releases/download/latest_oh4/no.seime.openhab.binding.esphome-4.1.0-SNAPSHOT.jar
```

(or drop the JAR into `$OPENHAB_ADDONS` and install the `bluetooth` add-on through the UI).

### 2. Discover the device

The binding discovers the ESPHome node over mDNS as `livingroom.local` (or whatever `name:` you set in the YAML). You will see it appear in **Settings → Things → Inbox** within a few seconds. Add it, paste the `api.encryption.key` from `firmware/secrets.yaml` into the Thing configuration.

The Thing auto-creates the following Channels:

| Type | Name |
|---|---|
| Switch | `restart_device` |
| Select | `operating_mode` (Normal / Calibrate / Simple) |
| Number | `presence_timeout`, `min_gate_distance`, `max_gate_distance`, `gate_select`, `still_threshold`, `move_threshold` |
| Sensor | `moving_distance`, `gate_energy_0` … `gate_energy_15` |
| Text Sensor | `fw_version` |
| Binary Sensor | `has_target` (presence) |
| Button | `apply_config`, `factory_reset`, `restart_module`, `revert_config` |

### 3. Items & Sitemap (minimal example)

```text
// items/presence.items
Number  Presence_MovingDistance   "Moving distance [%.1f cm]"  {channel="esphome:thing:livingroom:moving_distance"}
Number  Presence_Gate0Energy      "Gate 0 energy [%.0f]"       {channel="esphome:thing:livingroom:gate_energy_0"}
Contact Presence_HasTarget        "Room occupied [MAP(presence.map):%s]"  {channel="esphome:thing:livingroom:has_target"}
String  Presence_FwVersion        "Firmware [%s]"              {channel="esphome:thing:livingroom:fw_version"}
```

```text
// sitemaps/presence.sitemap
sitemap presence label="Living room presence" {
    Frame label="State" {
        Switch item=Presence_HasTarget label="Occupied"
        Text    item=Presence_MovingDistance
        Text    item=Presence_FwVersion
    }
    Frame label="Tuning" {
        Setpoint item=Presence_PresenceTimeout minValue=5 maxValue=600 step=5
        Setpoint item=Presence_MaxGateDistance minValue=1 maxValue=15 step=1
        Selection item=Presence_OperatingMode mappings=["Normal"="Normal","Calibrate"="Calibrate","Simple"="Simple"]
    }
}
```

---

## Calibration

1. Set `operating_mode` to **Calibrate** through the openHAB Thing or the ESPHome device page.
2. Leave the room empty for ≥ 30 s.
3. Press the **apply_config** button. The LD2420 computes per-gate noise-floor thresholds and writes them to flash. It returns to Normal mode automatically.

For best results with a 6 m room on wall mounting:
- `max_gate_distance: 9` (≈ 6.3 m physical)
- `min_gate_distance: 0`
- `presence_timeout: 30s` is a reasonable default; raise it for still-presence reliability.

---

## Project layout

```
.
├── firmware/
│   ├── livingroom.yaml           ESPHome configuration for the D1 mini + LD2410
│   └── secrets.yaml.example      Template — copy to secrets.yaml and fill in
├── components/ld2420_energy/     Local ESPHome component: 16 gate-energy sensors
│   ├── __init__.py
│   ├── sensor.py                 Binds the listener to the upstream LD2420Component
│   ├── sensor.h                  C++ listener (overrides LD2420Listener::on_energy)
│   └── sensor.cpp
├── docs/
│   ├── openhab.md                Detailed openHAB thing / item / rules examples
│   ├── hardware.md               Wiring diagram, photos, BOM
│   └── protocol.md               LD2420 UART frame reference (V2.x protocol)
├── scripts/
│   ├── clean.sh                  Wipe the toolchain cache so a stale
│   │                             toolchain-xtensa@3.x cannot leak into the next build
│   ├── new_node.sh               Clone livingroom.yaml for a 2nd / 3rd / 4th node
│   └── preflight.py              Smoke-check before `esphome run` (pinned versions, syntax)
├── RELEASE_CHECKLIST.md          R1B Backlog, build env snapshot, pre-release gate
├── .github/workflows/
│   └── lint.yaml                 yaml-lint on PR
├── LICENSE                       MIT
└── README.md                     (this file)
```

---

## License

MIT — see [LICENSE](./LICENSE).

ESPHome itself is GPL-3.0; the upstream `ld2420` component is GPL-3.0. This project's local component is MIT; consumers must accept the GPL-3.0 dependency if they use ESPHome.