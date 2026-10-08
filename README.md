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
> The fix is a single flag in `firmware/radar.yaml`:
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

The YAML lives in `firmware/radar.yaml`. Copy `firmware/secrets.yaml.example` to `firmware/secrets.yaml` and fill in Wi-Fi + openHAB `api:` encryption key before flashing.

```bash
cd firmware
# first time, or after a toolchain change:
../scripts/clean.sh
# every time, before flashing:
../scripts/preflight.py
esphome run radar.yaml     # first flash via USB
esphome run radar.yaml     # later: OTA after Wi-Fi is up
```

The custom component `components/ld2420_energy/` adds the 16 gate-energy sensors. It hooks into the upstream `LD2420Component` through the `LD2420Listener::on_energy()` interface that the parent already calls on every parsed energy frame (Normal mode, firmware ≥ v1.5.4, ~10 Hz). **No upstream fork is required.**

---

## openHAB integration

Uses the third-party **[seime/openhab-esphome](https://github.com/seime/openhab-esphome)** binding (MIT, currently `[4.0.0.0;6.0.0.0)` — openHAB 5.1.3 ✓).

The full integration guide (binding install, mDNS discovery, thing / items / sitemap / rules, common gotchas) is in **[`docs/openhab.md`](docs/openhab.md)**. A minimal example below; the v1.1.0 LD2410 firmware exposes the channel set below.

### 1. Install the binding

The binding has an **unmet dependency** on the `bluetooth` binding even if you do not use it; install both:

```text
openhab> bundle:install https://github.com/seime/openhab-esphome/releases/download/latest_oh4/no.seime.openhab.binding.esphome-4.1.0-SNAPSHOT.jar
```

(or drop the JAR into `$OPENHAB_ADDONS` and install the `bluetooth` add-on through the UI). For openHAB 5.1.3+, the binding is also available in the **Marketplace** (Settings → Add-ons → Bindings → "ESPHome Native API" → Install).

### 2. Discover the device

The binding discovers the ESPHome node over mDNS as `radar.local` (the `name:` field in `firmware/radar.yaml`). You will see it appear in **Settings → Things → Inbox** within a few seconds. Add it, paste the `api.encryption.key` from `firmware/secrets.yaml` into the Thing configuration.

The Thing auto-creates the following channels (v1.1.0 LD2410 channel set):

| Type | Channels |
|---|---|
| Binary Sensor | `has_target`, `has_moving_target`, `has_still_target` |
| Sensor | `moving_distance`, `still_distance`, `detection_distance`, `moving_energy`, `still_energy`, `g0`..`g8.move_energy`, `g0`..`g8.still_energy` (per-gate only in engineering mode) |
| Text Sensor | `fw_version`, `mac_address` (LD2410 MAC) |
| Switch | `restart`, `engineering_mode` |
| Select | `distance_resolution`, `baud_rate`, `light_function`, `out_pin_level` |
| Number | `max_move_distance_gate`, `max_still_distance_gate`, `timeout` (None duration), `light_threshold`, `g0`..`g8.move_threshold`, `g0`..`g8.still_threshold` |
| Button | `restart` (Restart module), `factory_reset`, `query_params` |

For the exact `Radar_*` item names, full sitemap, rule examples (AC auto-off on `Radar_HasTarget` close, AC low-power on `Radar_HasMovingTarget` close + `Radar_HasStillTarget` open), and 6 common gotchas (encryption_key mismatch, None duration tuning, 5V-on-VCC wiring, etc.), see **[`docs/openhab.md`](docs/openhab.md)**.

### 3. Items & Sitemap (minimal example)

```text
// items/radar.items
Number  Radar_MovingDistance    "Moving distance [%.0f cm]"   {channel="esphome:thing:radar:moving_distance"}
Number  Radar_StillDistance     "Still distance [%.0f cm]"    {channel="esphome:thing:radar:still_distance"}
Number  Radar_DetectionDistance "Detection distance [%.0f cm]" {channel="esphome:thing:radar:detection_distance"}
Number  Radar_MovingEnergy      "Moving energy [%.0f %%]"     {channel="esphome:thing:radar:moving_energy"}
Number  Radar_StillEnergy       "Still energy [%.0f %%]"      {channel="esphome:thing:radar:still_energy"}
Contact Radar_HasTarget         "Occupied [MAP(presence.map):%s]" {channel="esphome:thing:radar:has_target"}
Contact Radar_HasMovingTarget   "Moving [MAP(motion.map):%s]" {channel="esphome:thing:radar:has_moving_target"}
Contact Radar_HasStillTarget    "Still [MAP(presence.map):%s]"  {channel="esphome:thing:radar:has_still_target"}
String  Radar_FwVersion         "Firmware [%s]"               {channel="esphome:thing:radar:fw_version"}
String  Radar_LD2410MAC         "LD2410 MAC [%s]"             {channel="esphome:thing:radar:ld2410_mac"}
```

```text
// sitemaps/radar.sitemap
sitemap radar label="Radar presence" {
    Frame label="State" {
        Switch item=Radar_HasTarget label="Occupied"
        Text    item=Radar_MovingDistance
        Text    item=Radar_StillDistance
        Text    item=Radar_DetectionDistance
        Text    item=Radar_MovingEnergy
        Text    item=Radar_StillEnergy
        Text    item=Radar_FwVersion
    }
    Frame label="Tuning" {
        Switch item=Radar_EngineeringMode
        Setpoint item=Radar_NoneDuration minValue=0 maxValue=32767 step=1
        Setpoint item=Radar_MaxMoveDistanceGate minValue=2 maxValue=8 step=1
        Setpoint item=Radar_MaxStillDistanceGate minValue=2 maxValue=8 step=1
        Selection item=Radar_DistanceResolution mappings=["0.75m"="0.75m","0.2m"="0.2m"]
    }
}
```

---

## Calibration

The calibration procedure depends on which radar module is wired
in. Set `substitutions.radar_type` in `firmware/<node>.yaml` to
match the hardware (`ld2410` or `ld2420`); the v1.2.0 dispatcher
picks the right calibration workflow automatically.

### LD2410 / LD2410B / LD2410C (v1.1.0+)

The LD2410 firmware does its own auto-calibration: every
`set_*` (timeout, max_move_distance_gate, per-gate move/still
thresholds, etc.) is persisted to the LD2410 EEPROM
automatically. There is no separate "Apply config" button.

1. Make sure `Engineering mode` is **ON** in the web UI (or
   the `Radar_EngineeringMode` openHAB switch). It auto-disables
   after 5 minutes per Hi-Link spec.
2. Stand 1-1.5 m in front of the radar and read
   `Radar_MovingEnergy` (web UI: `Moving energy`). It should
   be 30-80%. If it stays < 10%, lower `Radar_Gate 0 move
   threshold` from 50 to 20.
3. Leave the room empty for ≥ 30 s, then read
   `Radar_StillEnergy`. It should drop to 0-5%. If it stays
   > 20%, the room is too noisy (HVAC, fans) — raise
   `Radar_Gate 0 still threshold` from 0 to 30.

For a typical 6 m × 4 m room on wall mounting:
- `Max move distance gate: 8` (full range, ~6 m at 0.75 m resolution)
- `Max still distance gate: 6` (still targets are within ~4.5 m)
- `Distance resolution: 0.75m` (default; switch to `0.2m` only if you
  need finer-grained gate readings, at the cost of shorter range)
- `None duration: 5s` (Presence turns off 5 s after the last
  detection; lower for faster off-response, higher for still-presence
  reliability)

### LD2420 (v1.0.0 + v1.2.0)

The LD2420 firmware requires a manual calibration cycle via the
`Apply config` button. The `set_*` number entities are
**not** persisted to the LD2420 EEPROM until you press the
button.

1. Set `Operating mode` to **Calibrate** through the openHAB
   Thing or the ESPHome device page.
2. Leave the room empty for ≥ 30 s.
3. Press the `Apply config` button. The LD2420 computes
   per-gate noise-floor thresholds and writes them to flash.
   It returns to Normal mode automatically.

For best results with a 6 m room on wall mounting:
- `Max gate distance: 9` (≈ 6.3 m physical)
- `Min gate distance: 0`
- `Presence timeout: 30s` is a reasonable default; raise it
  for still-presence reliability.

The v1.0.0 firmware on the GitHub Releases page uses this same
workflow; the v1.2.0 LD2420 build (loaded by the dispatcher
when `radar_type: ld2420`) is functionally identical to v1.0.0.

---

## Project layout

```
.
├── firmware/
│   ├── _common.yaml.include    Platform-level blocks (wifi/api/ota/logger/esphome)
│   │                             Shared by both LD2410 and LD2420 builds (BL-07)
│   ├── radar_ld2410.yaml       LD2410-specific blocks (uart, ld2410:, 9 gates)
│   ├── radar_ld2420.yaml       LD2420-specific blocks (external_components,
│   │                             uart, ld2420:, 16 gates via local listener)
│   ├── radar.yaml                Per-node template (substitutions + packages:)
│   │                             Cloned by `scripts/new_node.sh` for each node
│   └── secrets.yaml.example      Template — copy to secrets.yaml and fill in
├── components/ld2420_energy/     Local ESPHome component: 16 gate-energy sensors
│   ├── __init__.py
│   ├── sensor.py                 Binds the listener to the upstream LD2420Component
│   ├── sensor.h                  C++ listener (overrides LD2420Listener::on_energy)
│   └── sensor.cpp
├── docs/
│   ├── openhab.md                Detailed openHAB thing / item / rules examples
│   ├── hardware.md               Wiring diagram, photos, BOM
│   ├── protocol.md               LD2420 UART frame reference (V2.x protocol)
│   ├── RELEASE_NOTES_v1.0.0.md   v1.0.0 (LD2420-only) release notes
│   ├── RELEASE_NOTES_v1.1.0.md   v1.1.0 (LD2410-only) release notes
│   └── RELEASE_NOTES_v1.2.0.md   v1.2.0 (dual-radar dispatcher) release notes
├── scripts/
│   ├── clean.sh                  Wipe the toolchain cache so a stale
│   │                             toolchain-xtensa@3.x cannot leak into the next build
│   ├── new_node.sh               Clone radar.yaml for a 2nd / 3rd / 4th node
│   │                             Usage: scripts/new_node.sh <name> [radar_type]
│   └── preflight.py              Smoke-check before `esphome run` (pinned versions, syntax)
├── RELEASE_CHECKLIST.md          R1B Backlog (BL-01..BL-07), build env snapshot, pre-release gate
├── .github/workflows/
│   └── lint.yaml                 yaml-lint on PR
├── LICENSE                       MIT
└── README.md                     (this file)
```

### Radar type selection (BL-07, v1.2.0+)

The `substitutions.radar_type` key in `firmware/radar.yaml` (and
every per-node YAML cloned from it) selects which radar-specific
block to include. Valid values:

- `ld2410` — Hi-Link LD2410 / LD2410B / LD2410C, 256000 baud, 9
  gates, engineering mode, every `set_*` auto-persists to EEPROM.
  Default in `scripts/new_node.sh`.
- `ld2420` — Hi-Link LD2420, 115200 baud, 16 gates via the local
  `components/ld2420_energy/` listener, `apply_config` button
  required to persist changes.

To create a new node, run:

```bash
# LD2410 (default)
scripts/new_node.sh bedroom
# LD2420
scripts/new_node.sh kitchen ld2420
```

The script generates `firmware/<name>.yaml` from the template,
swaps the substitutions, generates a per-node API encryption
key (BL-06), and appends it to `firmware/secrets.yaml`. The
`packages:` block in the per-node YAML is patched to reference
the matching `radar_ld<type>.yaml` include.

The v1.0.0 LD2420 firmware is still available on the GitHub
Releases page; the v1.1.0 LD2410 firmware is also unchanged.
The `main` branch carries the v1.2.0 dispatcher that builds for
either radar module.

---

## License

MIT — see [LICENSE](./LICENSE).

ESPHome itself is GPL-3.0; the upstream `ld2420` component is GPL-3.0. This project's local component is MIT; consumers must accept the GPL-3.0 dependency if they use ESPHome.