# espRadar v1.1.0 — release notes (DRAFT, pending Miklós approval)

> ⚠️ **DRAFT.** This is the release-notes draft for the `v1.1.0`
> tag. It is **not** pushed yet. The release-gate is per the
> user memory entry: every release-szintű döntés (verzió, tag,
> force push, törlés) előtt Miklós jóváhagyása kell.

## Summary

**v1.1.0 swaps the radar module from LD2420 to LD2410.** The
`v1.0.0` LD2420 firmware (SHA-256 `fb0ea4f06ddc406ce41632df86615962bbf2df0f50d0466072a4f7e537398d3c`)
remains available on the GitHub Releases page for any node
that is still wired to an LD2420 module. The v1.1.0 firmware
**only** works on LD2410 / LD2410B / LD2410C hardware.

The v1.0.0 → v1.1.0 transition is **per-node**: rewire the UART
jumpers if needed (LD2410 pinout is identical to LD2420:
TX → D7, RX → D8, VCC → 3V3, GND → GND), then flash the
v1.1.0 firmware over OTA (the API encryption key is unchanged
from v1.0.0, so no re-pairing with openHAB is required).

### What changed (v1.0.0 → v1.1.0)

| Area | v1.0.0 (LD2420) | v1.1.0 (LD2410) |
|---|---|---|
| Sensor chip | HLK-LD2420 (BGT24MTR11) | HLK-LD2410 / LD2410B / LD2410C (BGT24LTR11) |
| UART baud | 115200 | 256000 |
| ESPHome component | upstream `ld2420` + local `components/ld2420_energy/` | upstream `ld2410` (native, no local component needed) |
| Per-gate energy | 16 gates × `gate_energy_0..15` (dB) | 9 gates × `g0..g8.move_energy` / `still_energy` (%, **engineering mode only**) |
| Aggregate energies | (none) | `moving_energy` / `still_energy` (% 0-100) |
| Operating mode | Normal / Calibrate / Simple (per ESPHome `ld2420`) | `distance_resolution` / `baud_rate` / `light_function` / `out_pin_level` (per ESPHome `ld2410`) |
| Persistence model | `apply_config` button required | every `set_*` auto-persists to LD2410 EEPROM |
| Local component | `components/ld2420_energy/` (4 files) | none — upstream-native |
| openHAB entities | ~25 (presence, distance, 16 gates, fw_version, mode, thresholds, apply/revert buttons) | ~50 (presence, moving/still/detection distances, moving/still energies, 9×2 gate energies, fw_version, MAC, engineering mode switch, 4 selects, 20 numbers, 3 buttons) |

### Pinout (unchanged from v1.0.0, except the supply voltage — see BL-05)

| LD2410 láb | D1 mini láb | Megjegyzés |
|---|---|---|
| TX | D7 (GPIO13) | ESP-oldali RX — a LD2410 **TX-eli** az adatokat, a D1 mini **fogadja** |
| RX | D8 (GPIO15) | ESP-oldali TX — a D1 mini **küldi** a parancsokat, a LD2410 **fogadja** |
| **VCC** | **5V** | **BL-05: az 5V sínt használd, NEM a 3V3-at** — különben minden szenzor `NA` marad |
| GND | GND | Közös föld |

The LD2410 out-of-the-box baud rate is 256000. **Hardware UART
required** (D7/D8 = GPIO13/15, kept off UART0 so the logger
can use it). The LD2410's `baud_rate` select entity can change
this; if you do, the `substitutions.ld2410_baud` in the YAML
must match and the firmware must be reinstalled with the new
UART baud.

### Engineering mode

The LD2410 reports per-gate energy (`g0..g8.move_energy` /
`still_energy`) **only in engineering mode**. The upstream
firmware auto-disables engineering mode after 5 minutes
(Hi-Link spec) to save power and reduce UART noise. To use the
per-gate sensors:

1. Open the ESPHome web UI at `http://<device-ip>/`
2. Switch `Engineering mode` ON
3. Read the `Gate N move energy` / `Gate N still energy`
   sensors (they will report `unknown` when engineering mode
   is off, a real % value when on)
4. Set per-gate thresholds on the `Gate N move threshold` /
   `Gate N still threshold` number entities
5. Set `Max move distance gate` / `Max still distance gate`
   to limit the detection range (default 8, range 2..8)
6. Engineering mode auto-disables after 5 minutes; the
   threshold values persist to LD2410 EEPROM

### openHAB integration

The openHAB Things file (per `docs/openhab.md`) needs to be
updated for v1.1.0: replace the `ld2420_*` entity names with
the new LD2410 entity names (e.g. `Moving distance` →
`Moving_distance`, add `Moving_energy`, `Still_distance`,
`Still_energy`, `Detection_distance`, `Gate_0_move_energy` …,
`Engineering_mode`, `Distance_resolution`, etc.). The
ESPHome binding auto-discovers entities by name, so the
`.things` file is the only manual update.

The v1.0.0 sitemap (`sitemap presence label="Living room
presence" { ... }`) needs the new entity names too. A
v1.1.0-ready sitemap draft is at the bottom of this document.

### How to flash (first USB flash)

```bash
cd ~/dev/espRadar
git pull origin main
./scripts/clean.sh
./scripts/preflight.py   # must print "PRE-FLIGHT OK"
cd firmware
esphome run radar.yaml
# Pick the USB option at the "Found multiple options" prompt
```

Subsequent OTA updates from the ESPHome dashboard do not need
the USB cable. The OTA partition is preserved across the
v1.0.0 → v1.1.0 upgrade.

### How to flash a second node (LD2410)

```bash
cd ~/dev/espRadar
./scripts/new_node.sh bedroom
# Edit firmware/bedroom.yaml (substitutions at the top)
cd firmware
esphome run bedroom.yaml
```

Each node uses DHCP. Give every node a stable IP via
router-side MAC reservation (do NOT bake static IPs into the
firmware) — see the `## Network setup` section of README.md.

### How to revert a node to v1.0.0 (LD2420 hardware)

```bash
cd ~/dev/espRadar
git checkout v1.0.0 -- firmware/livingroom.yaml
cd firmware
esphome run radar.yaml
git checkout main -- firmware/radar.yaml   # restore v1.1.0 YAML for the next node
```

The `components/ld2420_energy/` directory is kept in the repo
on `main` (v1.1.0) for this reason — the v1.0.0 firmware
expects it to be loaded via `external_components:`.

---

## Build environment (snapshot, filled in after a successful build)

| Component | Value |
|---|---|

> The actual config_hash, firmware.bin SHA-256, RAM/Flash usage
> and link time will be filled in here after the first v1.1.0
> build succeeds, mirroring the v1.0.0 snapshot in
> `RELEASE_CHECKLIST.md` → "Build environment snapshot".

---

## Pre-release gate (recap, from RELEASE_CHECKLIST.md)

1. `scripts/preflight.py` → must print `PRE-FLIGHT OK` (checks 1–7).
2. `scripts/clean.sh` (without `--all`) → nukes the toolchain cache.
3. `cd firmware && esphome run radar.yaml` → must reach `[SUCCESS]`.
4. `scripts/preflight.py check_4_ld2410_yaml` → confirms the YAML
   is a v1.1.0 LD2410 config (not v1.0.0 LD2420).
5. Tag only after a SUCCESS build with the new toolchain (no leftover
   `toolchain-xtensa@2.x` in `~/.platformio/packages/`).

All five steps must be GREEN for `v1.1.0` before tagging. The
current branch (`main` at the v1.1.0 commit) is expected to
build clean — the BL-01b `-include stddef.h` workaround
remains in place, the LD2410 component is upstream-native
and has no toolchain surprises.

---

## What is NOT in v1.1.0 (out of scope, tracked in the R1B Backlog)

- LED diagnostics removed — LEDC is no longer a YAML section in
  ESPHome 2025.11+ (lives on `output:` platform now). Presence
  state is exposed via openHAB, so an on-board LED is not needed.
- `external_components` path duplication (firmware/radar.yaml
  uses `path: components` instead of `path: ../components`).
  Currently option 2 (de-facto behaviour: `clean.sh` wipes the
  build cache which transitively includes the copied component)
  is in effect. Tracked in `RELEASE_CHECKLIST.md` →
  "Known follow-ups".
- `firmware/components/` shows up in `git status` during a build
  because ESPHome's `external_components: type: local, path: components`
  copies the parent into the build dir. v1.1.0 does not load
  `external_components:` at all (LD2410 is upstream-native), so
  this artifact is gone for v1.1.0 builds.
- v1.0.0 → v1.1.0 OTA test: not yet performed end-to-end. The
  API encryption key is unchanged, so in theory the OTA
  partition should accept the v1.1.0 firmware. If it doesn't,
  the recovery is a USB re-flash (see "How to flash" above).

---

## v1.1.0-ready openHAB sitemap draft

```sitemap
sitemap radar label="Radar presence" {
    Frame label="State" {
        Switch item=Radar_HasTarget label="Occupied"
        Text    item=Radar_MovingDistance
        Text    item=Radar_StillDistance
        Text    item=Radar_DetectionDistance
        Text    item=Radar_MovingEnergy
        Text    item=Radar_StillEnergy
        Text    item=Radar_FwVersion
        Text    item=Radar_LD2410MAC
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

(For the per-gate tuning UI, use the upstream ESPHome card
template from the LD2410 docs:
`https://esphome.io/components/sensor/ld2410/#calibration-process`)

---

## License

MIT — see [LICENSE](./LICENSE).

ESPHome itself is GPL-3.0; the upstream `ld2410` component is
GPL-3.0. This project's local component (in
`components/ld2420_energy/`, kept for v1.0.0 archives) is MIT.
