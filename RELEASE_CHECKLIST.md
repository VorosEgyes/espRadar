# espRadar — release checklist (R1)

> Living reference for the **single known-good firmware build** of the
> espRadar project (D1 mini + HLK-LD2420 mmWave radar, ESPHome 2026.9.1,
> exposed to openHAB 5.x). Update this file when a toolchain, ESPHome, or
> firmware-version bump changes the build path.

---

## R1B Backlog (open items)

### BL-01 — Toolchain pinning: `espressif8266@2.6.3` (CLOSED 2026-10-02 → SUPERSEDED 2026-10-02 by BL-01b)

**Initial symptom (1st attempt).** `esphome run firmware/livingroom.yaml`
fails with a cascade of errors in `toolchain-xtensa@3.x / gcc 10.3.0`
libstdc++ headers (`'std::size_t' has not been declared`,
`'_M_bucket' was not declared`, `'tuple_element_t' has not been
declared`, …). The cascade surfaces in `src/main.cpp` through
`<functional>` (included by ESPHome's `component.h`).

**Initial fix (now superseded).** Pin `espressif8266@2.6.3`, which
ships `toolchain-xtensa@~2.100100.0` (gcc 5.2) and does not exhibit
the bug.

**Re-opening (BL-01a).** The pin worked for the build cache, but
ESPHome 2026.9.1 hard-codes `cg.set_cpp_standard("gnu++20")` and
rejects any framework < 3.0.0
(`esphome/esphome@2026.9.1 esphome/components/esp8266/__init__.py:
_arduino_check_versions`). The actual `toolchain-xtensa` version
that platform `2.6.3` ships is `2.40802.200502` (gcc 5.2.0), which
does not understand `-std=gnu++20`:

```
xtensa-lx106-elf-g++: error: unrecognized command line option '-std=gnu++20'
```

The pin strategy from BL-01 is therefore **structurally
incompatible** with the current ESPHome: gcc 5.2 will never
compile C++20. The right fix is to accept the default
espressif8266@4.2.1 + toolchain-xtensa@3.x (gcc 10.3.0) and
work around the libstdc++ cascade differently — see BL-01b.

**Schema learning.** `platform_version` lives under `framework:`
in the ESPHome 2026.9.1 esp8266 schema, not at the `esp8266:`
block level. Putting it at the wrong level is rejected with
"[platform_version] is an invalid option for [esp8266]". Verified
against `esphome/esphome@2026.9.1
esphome/components/esp8266/__init__.py`.

### BL-01b — Pre-include `<stddef.h>` for toolchain-xtensa@3.x (CLOSED 2026-10-02 → revised 2026-10-02 to stddef.h)

**Symptom.** With the BL-01 pin reverted, the default
`espressif8266@4.2.1` + `toolchain-xtensa@3.x` (gcc 10.3.0) returns
the original `'std::size_t' has not been declared` cascade.

**Root cause.** toolchain-xtensa@3.x's libstdc++10 `<tuple>` and
`<hashtable_policy.h>` assume `std::size_t` is in scope by the
time they are first parsed, but `<cstddef>` is not brought in
early enough by ESPHome's `component.h` → `<functional>` include
chain. The compiler then chokes on
`std::size_t __bkt, std::size_t __bkt_count` in `hashtable_policy.h`.

**First fix attempt (BL-01b v1, reverted).** Pre-include
`<cstddef>` via `-include cstddef`. This works for the .cpp
translation units but fails on the .c files in
ESPAsyncTCP / noise-c:

```
cc1: fatal error: cstddef: No such file or directory
compilation terminated.
*** [.pioenvs/livingroom/libe9a/ESPAsyncTCP/tcp_axtls.c.o] Error 1
```

The C standard library does not ship `<cstddef>`; it ships
`<stddef.h>`. The `-include` flag is global to the toolchain
invocation and applies to both C and C++ TUs.

**Final fix (BL-01b v2).** Pre-include `<stddef.h>` instead.
`<stddef.h>` is valid in both C and C++ and (in C++) declares
the same `size_t` / `ptrdiff_t` types in `std::` as well, so
the `std::size_t` cascade never starts:

```yaml
esphome:
  # ... other esphome: keys ...
  platformio_options:
    build_flags:
      - -include stddef.h
```

**Long-term fix (tracker).** File an issue against `esphome/core`
to add `#include <cstddef>` (or `#include <stddef.h>`) to
`esphome/core/component.h` (or the relevant shared header), so
the workaround can be removed once upstream lands a fix.

**Validation.** `scripts/preflight.py` `check_6_cstddef_workaround`
(really checks for `-include stddef.h`; the name kept for
provenance) plus `check_6b_platformio_options_structure` (PyYAML
parse + structural check) fail if the flag is ever removed or
if `cstddef` is substituted for `stddef.h`.

### BL-04 — Preflight guard check_4_ld2410_yaml + _strip_yaml_comments (CLOSED 2026-10-02)

The preflight.py was rewritten for the v1.1.0 LD2410 firmware
to drop the LD2420-specific 16 `gate_energy_N:` assertion
(`check_4_gate_keys`) and add a positive LD2410 check
(`check_4_ld2410_yaml`) that verifies:

- top-level `ld2410:` hub block
- at least one `platform: ld2410` block
- `uart.baud_rate: ${ld2410_baud}` and 256000 in the file
- at least one of `has_target:` / `has_moving_target:` /
  `has_still_target:` binary sensor
- no `ld2420:` / `platform: ld2420` / `ld2420_baud` / `fw_version` / `query:` (typos) in the active code
- the `components/ld2420_energy/` directory is still on disk (v1.0.0 archive)

To avoid substring false-positives from the comment text that
mentions `ld2420` for historical context, a `_strip_yaml_comments`
helper was added. The doksi page (esphome.io) for the LD2410
sensor is out of date in two places (the `text_sensor.fw_version`
key is actually `version`, and the `button.query` key is
actually `query_params`); the upstream Python schema
(`esphome/components/ld2410/text_sensor.py` and
`esphome/components/ld2410/button/__init__.py`) is the source
of truth, and the preflight checks are derived from it.

**Validation.** `scripts/preflight.py` `check_4_ld2410_yaml`
fails CI if the YAML ever drifts back to an LD2420-style
config (or to a wrong-key spelling of any LD2410 entity).

### BL-05 — Hardware: LD2410 must be powered from the D1 mini 5V rail, NOT 3V3 (CLOSED 2026-10-02)

**Symptom.** The first v1.1.0 build on the desk booted
successfully (the D1 mini joined the Wi-Fi, the web_server UI
loaded), but every LD2410 entity showed `NA` — `Firmware
version`, `LD2410 MAC`, `Detection distance`, all per-gate
`g0..g8.move_energy` / `still_energy` numbers. The D1 mini
itself was healthy (no warnings in the component loop other
than the `ld2410 took 253 ms` long-operation warning, which is
normal in engineering mode).

**Root cause.** The LD2410 was wired with VCC to the D1 mini's
`3V3` pin (per the LD2420 wiring in the v1.0.0 docs). Some
Hi-Link LD2410 batches (and most clone modules) require 5 V
for reliable UART signal levels; on 3V3 the UART appears alive
on power-up but no communication happens (`Firmware version`
stays `NA`, all per-gate energy sensors stay `NA`,
`Detection distance` stays `NA`). The symptom looks identical
to a wiring fault (TX/RX reversed) or a baud-rate mismatch.

**Fix.** Move the LD2410 VCC jumper from the D1 mini `3V3`
pin to the `5V` pin. The D1 mini's `5V` header pin is fed
directly from the USB input (it bypasses the on-board 3V3
LDO) and can source the LD2410's 50 mA average / 100 mA peak.
After the move, the `Firmware version` text_sensor shows the
LD2410's internal firmware version (typically `v2.x.x`) and
all other entities populate within ~1 second.

**Validation.** The first entity to populate is `LD2410 MAC`
— if it goes from `NA` to a real MAC address (e.g.
`AA:BB:CC:DD:EE:FF`), the wiring is good. The firmware
version is the second; the per-gate energies require
`Engineering mode` to be on (and auto-disable after 5 min,
see `docs/RELEASE_NOTES_v1.1.0.md`).

**Docs updated.**

- `firmware/radar.yaml`: long comment in `substitutions:`
  explaining the 5V requirement and the silent-no-communication
  symptom on 3V3.
- `README.md` Hardware section: wiring table shows
  `VCC → 5V (BL-05: NOT 3V3)` and a callout box.
- `docs/hardware.md`: full rewrite from LD2420 to LD2410,
  with the 5V supply note as a critical warning at the top
  and a detailed `## Power budget` section.
- `docs/RELEASE_NOTES_v1.1.0.md` pinout table: VCC row
  updated to 5V with BL-05 reference.

**Long-term fix (tracker).** Add a `check_5_ld2410_supply_voltage`
preflight check that reads the `firmware/radar.yaml`
comment for the 5V marker. Not implemented yet because the
preflight is YAML-side, not hardware-side — there is no way
to detect a 3V3 wiring from the YAML alone. The `BL-05`
backlog item is the doc-level guard; the actual hardware
verification is the `LD2410 MAC` text_sensor populating.

### BL-02 — Python binding: `register_listener` (not `add_listener`) (CLOSED 2026-10-02)

**Symptom.** `main.cpp:693:15: error: 'class esphome::ld2420::LD2420Component'
has no member named 'add_listener'`.

**Root cause.** `components/ld2420_energy/sensor.py` calls
`cg.add(hub.add_listener(var))`, but the upstream LD2420Component method
is `register_listener`. The name was stable from the 2023-11 merge
through 2026.9.1 (verified against
`esphome/esphome@2026.9.1 esphome/components/ld2420/ld2420.h:102`).

**Fix.** Changed the binding in `components/ld2420_energy/sensor.py:66`
from `add_listener` to `register_listener`. The C++ side
(`sensor.h`, `sensor.cpp`) was already correct — `LD2420Listener`-ből
öröklődik, `on_energy` override jó.

**Validation.** `scripts/preflight.py` `check_7_register_listener` fails
if `add_listener` ever reappears in the binding.

### BL-03 — Toolchain cache wipe on every clean build (CLOSED 2026-10-02)

**Symptom.** Even after BL-01's `platform_version: 2.6.3` pin is in
place, the first build after a fresh `esphome run` can still pull
`toolchain-xtensa@3.x` from the PlatformIO package cache at
`~/.platformio/packages/`. `esphome clean` only wipes
`firmware/.esphome/build/`, not the toolchain directory.

**Fix.** New script: `scripts/clean.sh`. Wipes:

- `firmware/.esphome/build/`
- `firmware/.esphome/storage/`
- `~/.platformio/packages/toolchain-xtensa@*`
- `~/.platformio/packages/framework-arduinoespressif8266@*`
- `~/.platformio/platforms/espressif8266@*`

Pass `--all` to also wipe `~/.platformio` entirely. Usage:

```bash
scripts/clean.sh              # keep ESP8266WiFi, ESPAsyncTCP, etc.
scripts/clean.sh --all        # nuke everything
```

---

## Pre-release gate (every release)

Run before any version bump / tag / GitHub release:

1. `scripts/preflight.py` → must print `PRE-FLIGHT OK` (checks 1–7).
2. `scripts/clean.sh` (without `--all`) → nukes the toolchain cache.
3. `cd firmware && esphome run radar.yaml` → must reach `[SUCCESS]`.
4. If a new node was added: also `scripts/new_node.sh <name>` and run
   the new config through the same gate.
5. Tag only after a SUCCESS build with the new toolchain (no leftover
   `toolchain-xtensa@3.x` in `~/.platformio/packages/`).

---

## Known follow-ups (out of scope for R1)

- **`external_components` path duplication** (firmware/radar.yaml
  uses `path: components`, which is a path relative to the YAML file —
  i.e. `firmware/components/ld2420_energy/`. The ESPHome build copies
  the parent `components/` into that location, so the build cache ends
  up with a stale duplicate if the parent is edited but the build
  cache is not wiped. The two fixes (pick one):
  1. Change `path: components` to `path: ../components` in
     firmware/radar.yaml. One-line change; breaks the current
     workflow where `firmware/components/` is checked in.
  2. Add `firmware/components/` to `firmware/.gitignore` and rely on
     `scripts/clean.sh` to wipe it. Less elegant but no behavioural
     change to the build.
  Currently option 2 is the de-facto behaviour — `clean.sh` wipes
  `firmware/.esphome/build/` which transitively includes the copied
  component — but the directory is briefly created in
  `firmware/components/` during a build, and shows up in
  `git status` if not ignored. Tracked here so we do not forget to
  decide on a long-term fix.

---

## Build environment snapshot

### First successful build (2026-10-02 23:48:24 +0200)

This is the **first build of the espRadar project**. The firmware
is the binary referenced by the eventual `v1.0.0` release tag
(once Miklós approves the release gate).

| Component | Value |
|---|---|
| ESPHome | 2026.9.1 |
| platformio/espressif8266 | 4.2.1 (default; BL-01's `2.6.3` pin is structurally incompatible, see BL-01a) |
| toolchain-xtensa | 3.x (gcc 10.3.0; see BL-01b for the `<stddef.h>` workaround) |
| framework-arduinoespressif8266 | 3.1.2 (recommended) |
| LD2420 firmware (target) | ≥ v1.5.4 |
| Python | 3.14 (macOS preflight) |
| Host | macOS (MacBook Air, modmj) |
| D1 mini (target) | ESP8266EX, 80MHz, 4MB flash, MAC f4:cf:a2:d8:18:e4 |
| USB port | /dev/cu.usbserial-1130 (CH340 USB2.0-Ser!) |
| esptool | 5.3.1 (Stub flasher) |
| Flash baud | 460800 |

| Build artifact | Value |
|---|---|
| `config_hash` | 0xFED1A364 (4275151716) |
| `build_time_str` | 2026-10-02 23:48:24 +0200 |
| `firmware.bin` size | 472496 bytes (464 KB) |
| `firmware.bin` SHA-256 | `fb0ea4f06ddc406ce41632df86615962bbf2df0f50d0466072a4f7e537398d3c` |
| RAM usage | 36924 / 81920 bytes (45.1%) |
| Flash usage | 468349 / 1044464 bytes (44.8%) |
| Link time | 125.20 s (full clean build) |
| Upload time | 9.2 s at 412.6 kbit/s (compressed 338625 / 472496) |
| Flash erase range | 0x00000000 → 0x00073fff |
| `firmware.elf` | `firmware/.esphome/build/livingroom/.pioenvs/livingroom/firmware.elf` |

**Reference for OTA verification.** The SHA-256 of the
`firmware.bin` is the canonical fingerprint of this build. Any
OTA update payload should match this hash (or the corresponding
hash of a later tagged release) byte-for-byte.
