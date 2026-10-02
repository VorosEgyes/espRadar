# espRadar — release checklist (R1)

> Living reference for the **single known-good firmware build** of the
> espRadar project (D1 mini + HLK-LD2420 mmWave radar, ESPHome 2026.9.1,
> exposed to openHAB 5.x). Update this file when a toolchain, ESPHome, or
> firmware-version bump changes the build path.

---

## R1B Backlog (open items)

### BL-01 — Toolchain pinning: `espressif8266@2.6.3` (CLOSED 2026-10-02)

**Symptom.** `esphome run firmware/livingroom.yaml` fails with a cascade of
errors in `toolchain-xtensa@3.x / gcc 10.3.0` libstdc++ headers
(`'std::size_t' has not been declared`, `'_M_bucket' was not declared`,
`'tuple_element_t' has not been declared`, …). The cascade surfaces in
`src/main.cpp` through `<functional>` (included by ESPHome's
`component.h`), but the actual trigger is the `ld2420_energy/sensor.cpp`
include of the same `component.h`.

**Root cause.** ESPHome 2025.11+ defaults to `platform =
platformio/espressif8266@4.2.1`, which pulls `toolchain-xtensa@3.x`
(gcc 10.3.0). That toolchain's libstdc++ headers are inconsistent with
`-std=gnu++20` (the standard ESPHome 2026.9.1 builds with). The 2.x
line of espressif8266 uses `toolchain-xtensa@~2.100100.0` (gcc 5.2) and
does not exhibit the bug.

**Fix.** Pin the platform in `firmware/livingroom.yaml`:

```yaml
esp8266:
  board: d1_mini
  platform_version: 2.6.3
  framework:
    version: recommended
```

**Why we cannot just upgrade the toolchain.** ESPHome 2025.11+ does
not support any espressif8266 ≥ 3.x without `-std=gnu++20`, and the
toolchain-xtensa@3.x header bug has no upstream fix as of 2026-09.
Possible future workarounds (not yet needed):

- Override the c++ standard in `build_flags` to `-std=gnu++17`
  (loses some C++20 features used by upstream ESPHome 2026.x).
- Wait for a toolchain-xtensa@3.x fix.

**Validation.** `scripts/preflight.py` now has `check_6_platform_pinned`
that fails CI if the pin is removed.

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
3. `cd firmware && esphome run livingroom.yaml` → must reach `[SUCCESS]`.
4. If a new node was added: also `scripts/new_node.sh <name>` and run
   the new config through the same gate.
5. Tag only after a SUCCESS build with the new toolchain (no leftover
   `toolchain-xtensa@3.x` in `~/.platformio/packages/`).

---

## Known follow-ups (out of scope for R1)

- **`external_components` path duplication** (firmware/livingroom.yaml
  uses `path: components`, which is a path relative to the YAML file —
  i.e. `firmware/components/ld2420_energy/`. The ESPHome build copies
  the parent `components/` into that location, so the build cache ends
  up with a stale duplicate if the parent is edited but the build
  cache is not wiped. The two fixes (pick one):
  1. Change `path: components` to `path: ../components` in
     firmware/livingroom.yaml. One-line change; breaks the current
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

## Build environment snapshot (2026-10-02, the first successful build)

| Component | Version |
|---|---|
| ESPHome | 2026.9.1 |
| platformio/espressif8266 | 2.6.3 (pinned) |
| toolchain-xtensa | ~2.100100.0 (gcc 5.2.0) |
| framework-arduinoespressif8266 | ~3.30102.0 |
| LD2420 firmware (target) | ≥ v1.5.4 |
| Python | 3.14 (macOS preflight) |
| Host | macOS (MacBook Air, modmj) |
