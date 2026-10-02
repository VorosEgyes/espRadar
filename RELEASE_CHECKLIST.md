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

### BL-01b — Pre-include `<cstddef>` for toolchain-xtensa@3.x (CLOSED 2026-10-02)

**Symptom.** With the BL-01 pin reverted, the default
`espressif8266@4.2.1` + `toolchain-xtensa@3.x` (gcc 10.3.0) returns
the original `'std::size_t' has not been declared` cascade.

**Root cause.** toolchain-xtensa@3.x's libstdc++10 `<tuple>` and
`<hashtable_policy.h>` assume `std::size_t` is in scope by the
time they are first parsed, but `<cstddef>` is not brought in
early enough by ESPHome's `component.h` → `<functional>` include
chain. The compiler then chokes on
`std::size_t __bkt, std::size_t __bkt_count` in `hashtable_policy.h`.

**Fix.** Force `<cstddef>` to be pre-included in every translation
unit, via the `esphome.platformio_options.build_flags` key in
`firmware/livingroom.yaml`:

```yaml
esphome:
  # ... other esphome: keys ...
  platformio_options:
    build_flags:
      - -include cstddef
```

The `-include cstddef` flag makes gcc put `<cstddef>` at the very
top of every `.cpp` file, before any toolchain header is parsed,
so `std::size_t` / `std::ptrdiff_t` are always in scope.

**Long-term fix (tracker).** File an issue against `esphome/core`
to add `#include <cstddef>` to `esphome/core/component.h` (or the
relevant shared header), so the workaround can be removed once
upstream lands a fix.

**Validation.** `scripts/preflight.py` `check_6_cstddef_workaround`
fails if the `-include cstddef` flag is ever removed from
`firmware/livingroom.yaml`.

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
| platformio/espressif8266 | 4.2.1 (default; BL-01's `2.6.3` pin is structurally incompatible, see BL-01a) |
| toolchain-xtensa | 3.x (gcc 10.3.0; see BL-01b for the `<cstddef>` workaround) |
| framework-arduinoespressif8266 | 3.1.2 (recommended) |
| LD2420 firmware (target) | ≥ v1.5.4 |
| Python | 3.14 (macOS preflight) |
| Host | macOS (MacBook Air, modmj) |
