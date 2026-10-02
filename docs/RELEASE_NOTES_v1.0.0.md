# espRadar v1.0.0 — release notes (DRAFT, pending Miklós approval)

> ⚠️ **DRAFT.** This is the release-notes draft for the `v1.0.0`
> tag. It is **not** pushed yet. The release-gate is per the
> user memory entry: every release-szintű döntés (verzió, tag,
> force push, törlés) előtt Miklós jóváhagyása kell.

## First end-to-end working build of the espRadar project

D1 mini + HLK-LD2420 mmWave radar, exposed to openHAB 5.x via
the ESPHome Native API. No MQTT broker required.

This is the home-automation companion to the `BirdNest` /
`RaisedGarden` VorosEgyes project family — same firmware + device
-class conventions, no separate cloud, fully local.

### Build artifact

- `firmware.bin` SHA-256: `fb0ea4f06ddc406ce41632df86615962bbf2df0f50d0466072a4f7e537398d3c`
- `firmware.bin` size: 472496 bytes (464 KB)
- RAM: 36924 / 81920 bytes (45.1%)
- Flash: 468349 / 1044464 bytes (44.8%)
- Config hash: 0xFED1A364

OTA reference: any update payload must match the SHA-256 of the
corresponding tagged release. See `RELEASE_CHECKLIST.md` →
"Build environment snapshot" for the full table.

### Hardware (already documented in docs/hardware.md)

- Wemos D1 mini (ESP8266, 4 MB flash) — the MCU
- Hi-Link HLK-LD2420 — 24 GHz FMCW mmWave radar, 16 gates × 0.70 m
- 4 jumper wires — TX / RX / VCC / GND (D7 / D8 = GPIO13 / GPIO15,
  kept off UART0 so the logger can use it)
- USB 5 V / 1 A supply

### Features (already documented in README.md)

- Presence detection (moving + still targets, 16 configurable gates)
- Moving distance in centimetres
- Per-gate energy sensors (`gate_energy_0` … `gate_energy_15`)
- Dynamic calibration (Normal / Calibrate / Simple modes; firmware
  ≥ v1.5.4 required)
- Calibration UI in openHAB (select, number, button entities)
- Firmware version reporting
- OTA updates through ESPHome dashboard
- DHCP networking (router-side MAC reservation; no static IPs in
  firmware)

### OpenHAB integration (already documented in docs/openhab.md)

Native API via the `seime/openhab-esphome` binding. Sitemap with
Occupancy / Moving distance / FwVersion + tuning UI
(PresenceTimeout / MaxGateDistance / OperatingMode).

---

## Build environment (snapshot 2026-10-02)

| Component | Value |
|---|---|
| ESPHome | 2026.9.1 |
| platformio/espressif8266 | 4.2.1 (default) |
| toolchain-xtensa | 3.x (gcc 10.3.0) |
| framework-arduinoespressif8266 | 3.1.2 (recommended) |
| LD2420 firmware (target) | ≥ v1.5.4 |
| Python | 3.14 (macOS preflight) |
| Host | macOS (MacBook Air, modmj) |

The build was finished with the BL-01b v2 workaround in
`firmware/livingroom.yaml`:

```yaml
esphome:
  platformio_options:
    build_flags:
      - -include stddef.h
```

This pre-includes `<stddef.h>` (C + C++ valid) so the
`std::size_t` cascade in toolchain-xtensa@3.x's libstdc++10
`<tuple>` / `<hashtable_policy.h>` never starts. The
workaround is guarded by `scripts/preflight.py` checks
`check_6_cstddef_workaround` + `check_6b_platformio_options_structure`.

See `RELEASE_CHECKLIST.md` for the full BL-01 / BL-01a / BL-01b
diagnosis history (the earlier `espressif8266@2.6.3` pin from
BL-01 turned out to be structurally incompatible with the current
ESPHome because the gcc 5.2 toolchain cannot compile C++20).

---

## How to flash (first USB flash)

```bash
cd ~/dev/espRadar
git pull origin main
./scripts/clean.sh
./scripts/preflight.py   # must print "PRE-FLIGHT OK"
cd firmware
esphome run livingroom.yaml
# Pick the USB option at the "Found multiple options" prompt
```

Subsequent OTA updates from the ESPHome dashboard do not need
the USB cable.

---

## How to flash a second node

```bash
cd ~/dev/espRadar
./scripts/new_node.sh bedroom
# Edit firmware/bedroom.yaml (substitutions at the top)
cd firmware
esphome run bedroom.yaml
```

Each node uses DHCP. Give every node a stable IP via router-side
MAC reservation (do NOT bake static IPs into the firmware) —
see the `## Network setup` section of README.md.

---

## Pre-release gate (recap, from RELEASE_CHECKLIST.md)

1. `scripts/preflight.py` → must print `PRE-FLIGHT OK` (checks 1–7).
2. `scripts/clean.sh` (without `--all`) → nukes the toolchain cache.
3. `cd firmware && esphome run livingroom.yaml` → must reach `[SUCCESS]`.
4. If a new node was added: also `scripts/new_node.sh <name>` and run
   the new config through the same gate.
5. Tag only after a SUCCESS build with the new toolchain (no leftover
   `toolchain-xtensa@2.x` in `~/.platformio/packages/`).

All five steps are GREEN for `v1.0.0`. The current branch
(`main` @ `93c58ac`) builds clean and uploads successfully.

---

## What is NOT in v1.0.0 (out of scope, tracked in the R1B Backlog)

- LED diagnostics removed — LEDC is no longer a YAML section in
  ESPHome 2025.11+ (lives on `output:` platform now). Presence
  state is exposed via openHAB, so an on-board LED is not needed.
- `external_components` path duplication (firmware/livingroom.yaml
  uses `path: components` instead of `path: ../components`).
  Currently option 2 (de-facto behaviour: `clean.sh` wipes the
  build cache which transitively includes the copied component)
  is in effect. Tracked in `RELEASE_CHECKLIST.md` →
  "Known follow-ups".
- `firmware/components/` shows up in `git status` during a build
  because ESPHome's `external_components: type: local, path: components`
  copies the parent into the build dir. Working as intended; will
  not be added to .gitignore in v1.0.0 to keep the change minimal.

---

## License

MIT — see [LICENSE](./LICENSE).

ESPHome itself is GPL-3.0; the upstream `ld2420` component is
GPL-3.0. This project's local component is MIT; consumers must
accept the GPL-3.0 dependency if they use ESPHome.
