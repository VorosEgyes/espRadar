#!/usr/bin/env python3
"""Pre-flight smoke check before `esphome run`.

Run from the repo root. Exits non-zero on the first failure so it can be
wired into CI later.

Checks:
  1. firmware/secrets.yaml exists (not the .example).
  2. secrets.yaml has no `PASTE_BASE64_32BYTE_HERE=` placeholders left in.
  3. firmware/livingroom.yaml parses as YAML.
  4. The 16 gate_energy_N keys are present in the YAML.
  5. components/ld2420_energy/ contains all three source files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


# ESPHome extends YAML with `!secret` tags — load them as plain strings so
# preflight does not require the ESPHome Python environment to parse the
# configuration files.
class _SecretLoader(yaml.SafeLoader):
    pass


_SecretLoader.add_constructor(
    "!secret", lambda loader, node: loader.construct_scalar(node)
)


REPO = Path(__file__).resolve().parent.parent
FIRMWARE = REPO / "firmware"
SECRETS = FIRMWARE / "secrets.yaml"
MAIN_YAML = FIRMWARE / "livingroom.yaml"
COMPONENT = REPO / "components" / "ld2420_energy"


def fail(msg: str) -> None:
    print(f"PRE-FLIGHT FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check_1_secrets() -> None:
    if not SECRETS.exists():
        fail("firmware/secrets.yaml is missing — copy secrets.yaml.example.")


def check_2_no_placeholders() -> None:
    if not SECRETS.exists():
        return
    text = SECRETS.read_text(encoding="utf-8")
    if "PASTE_BASE64_32BYTE_HERE" in text:
        fail("firmware/secrets.yaml still contains placeholder api_encryption_key.")
    if "YOUR_SSID" in text or "YOUR_PASSWORD" in text:
        fail("firmware/secrets.yaml still contains placeholder Wi-Fi credentials.")


def check_3_yaml_parses() -> None:
    if not MAIN_YAML.exists():
        fail(f"{MAIN_YAML} not found.")
    try:
        yaml.load(MAIN_YAML.read_text(encoding="utf-8"), Loader=_SecretLoader)
    except yaml.YAMLError as e:
        fail(f"firmware/livingroom.yaml does not parse: {e}")


def check_4_gate_keys() -> None:
    text = MAIN_YAML.read_text(encoding="utf-8")
    missing = [f"gate_energy_{i}:" for i in range(16) if f"gate_energy_{i}:" not in text]
    if missing:
        fail(f"Missing gate_energy_N entries: {missing[:3]}…")


def check_5_component_files() -> None:
    required = ["__init__.py", "sensor.py", "sensor.h", "sensor.cpp"]
    missing = [f for f in required if not (COMPONENT / f).exists()]
    if missing:
        fail(f"components/ld2420_energy/ missing: {missing}")


def check_6_cstddef_workaround() -> None:
    """Guard the BL-01b toolchain-xtensa@3.x libstdc++ workaround.

    ESPHome 2026.9.1 hard-codes `cg.set_cpp_standard("gnu++20")` and
    rejects any framework < 3.0.0, so the toolchain pin from BL-01
    (espressif8266@2.6.3, gcc 5.2) is structurally incompatible
    with the current ESPHome. The default espressif8266@4.2.1 +
    toolchain-xtensa@3.x (gcc 10.3.0) supports gnu++20 but its
    libstdc++10 <tuple> / <hashtable_policy.h> assume `std::size_t`
    is in scope by the time they are first parsed, which the
    ESPHome <functional> include chain does not guarantee. The
    `-include cstddef` flag puts `std::size_t` in scope before
    any toolchain header is parsed.

    If the flag is ever removed, the build dies with the same
    "std::size_t has not been declared" cascade that the original
    BL-01 was trying to avoid.
    """
    text = MAIN_YAML.read_text(encoding="utf-8")
    if "-include cstddef" not in text:
        fail(
            "firmware/livingroom.yaml is missing the BL-01b toolchain-xtensa@3.x "
            "workaround. The `esphome:` block must set "
            "`platformio_options.build_flags: [-include cstddef]` to keep "
            "`std::size_t` / `std::ptrdiff_t` in scope before any toolchain "
            "header is parsed. Without it, the build dies with the "
            "'std::size_t has not been declared' cascade in <hashtable_policy.h> "
            "and <tuple>. See the long comment in firmware/livingroom.yaml "
            "and RELEASE_CHECKLIST.md BL-01b."
        )


def check_6b_platformio_options_structure() -> None:
    """Structural validation of the BL-01b `platformio_options` block.

    Verifies that:
    - the YAML parses,
    - the top-level `esphome:` block has a `platformio_options` mapping,
    - `platformio_options.build_flags` is a list (not a string),
    - the list contains the literal "-include cstddef".

    Catches the "looks right, but wrong YAML type" failure mode
    where e.g. `build_flags: -include cstddef` (string, not list)
    passes the substring check in check_6 but is rejected by the
    ESPHome 2026.9.1 `esphome.config.CONFIG_SCHEMA` validator
    (`cv.Schema({cv.string_strict: cv.Any([cv.string], cv.string)})`).
    """
    try:
        import yaml  # noqa: F401  (PyYAML is on the Mac where this runs)
    except ImportError:
        # PyYAML not available (NAS / CI without it) — fall back to the
        # substring check in check_6_cstddef_workaround. A NAS-side
        # limitation, not a project defect.
        return
    import yaml  # type: ignore[no-redef]

    cfg = None
    try:
        cfg = yaml.load(MAIN_YAML.read_text(encoding="utf-8"), Loader=_SecretLoader)
    except yaml.YAMLError as e:
        fail(f"firmware/livingroom.yaml does not parse: {e}")

    if cfg is None:
        fail("firmware/livingroom.yaml is empty or null after parsing.")

    esphome = cfg.get("esphome") if isinstance(cfg, dict) else None
    if not isinstance(esphome, dict):
        fail("firmware/livingroom.yaml is missing the top-level `esphome:` mapping.")

    pio_opts = esphome.get("platformio_options") if isinstance(esphome, dict) else None
    if not isinstance(pio_opts, dict):
        fail(
            "firmware/livingroom.yaml is missing "
            "`esphome.platformio_options:` (a mapping). The BL-01b workaround "
            "must be a `platformio_options.build_flags:` list, not a string."
        )

    build_flags = pio_opts.get("build_flags") if isinstance(pio_opts, dict) else None
    if not isinstance(build_flags, list):
        fail(
            "`esphome.platformio_options.build_flags` must be a YAML list "
            "(`- -include cstddef`), not a scalar string. The ESPHome 2026.9.1 "
            "schema requires `dict[string, list[string] | str]` and a scalar "
            "is silently dropped at codegen time."
        )

    if "-include cstddef" not in build_flags:
        fail(
            "`esphome.platformio_options.build_flags` does not contain "
            "`-include cstddef`. The BL-01b toolchain-xtensa@3.x workaround "
            "must be in the list (alongside any other flags)."
        )


def check_7_register_listener() -> None:
    """Guard the Python binding against the add_listener() typo.

    The upstream LD2420Component exposes `register_listener(...)` (since
    2023-11 merge, stable through 2026.9.1). The old `add_listener` name
    is a build-breaking typo that compiles to a non-existent method call.
    """
    py = COMPONENT / "sensor.py"
    if not py.exists():
        return
    text = py.read_text(encoding="utf-8")
    if "hub.add_listener(" in text or "cg.add(hub.add_listener(" in text:
        fail(
            f"{py} still calls `hub.add_listener(...)` — the upstream "
            "LD2420Component method is `register_listener` (verified "
            "against esphome@2026.9.1 esphome/components/ld2420/ld2420.h:102)."
        )


def main() -> int:
    check_1_secrets()
    check_2_no_placeholders()
    check_3_yaml_parses()
    check_4_gate_keys()
    check_5_component_files()
    check_6_cstddef_workaround()
    check_6b_platformio_options_structure()
    check_7_register_listener()
    print("PRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())