#!/usr/bin/env python3
"""Pre-flight smoke check before `esphome run`.

Run from the repo root. Exits non-zero on the first failure so it can be
wired into CI later.

Checks:
  1. firmware/secrets.yaml exists (not the .example).
  2. secrets.yaml has no `PASTE_BASE64_32BYTE_HERE=` placeholders left in.
  3. firmware/radar.yaml parses as YAML.
  4. firmware/radar.yaml is a v1.1.0 LD2410 config
     (`check_4_ld2410_yaml`).
  5. components/ld2420_energy/ contains all four source files
     (v1.0.0 archive — kept on disk for the LD2420 firmware).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# PyYAML is always available where `esphome` is installed (the
# Mac). The preflight is also run from the NAS for a structural
# sanity check before committing, and the NAS does not have
# PyYAML. The import is therefore wrapped in a try/except: the
# bare-minimum check (check_3) still works without PyYAML, and
# the structural check (check_6b) is a no-op when PyYAML is
# missing.
try:
    import yaml  # type: ignore[import-not-found]
    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


# ESPHome extends YAML with `!secret` tags — load them as plain strings so
# preflight does not require the ESPHome Python environment to parse the
# configuration files.
class _SecretLoader(yaml.SafeLoader if _HAS_YAML else object):  # type: ignore[misc]
    pass


if _HAS_YAML:
    _SecretLoader.add_constructor(  # type: ignore[attr-defined]
        "!secret", lambda loader, node: loader.construct_scalar(node)
    )


REPO = Path(__file__).resolve().parent.parent
FIRMWARE = REPO / "firmware"
SECRETS = FIRMWARE / "secrets.yaml"
MAIN_YAML = FIRMWARE / "radar.yaml"
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


def check_2b_per_node_api_key() -> None:
    """Guard the BL-06 per-node API encryption key.

    Every `firmware/<név>.yaml` references a `!secret
    api_encryption_key_<név>` key (set by `scripts/new_node.sh
    <név>`). If the radar.yaml references a key that is not
    defined in secrets.yaml, `esphome run` will fail with a
    substitution error. This check parses radar.yaml and
    verifies that every `!secret api_encryption_key_...`
    reference has a matching `api_encryption_key_...:` entry in
    secrets.yaml.
    """
    if not _HAS_YAML:
        return
    if not SECRETS.exists():
        return
    try:
        cfg = yaml.load(MAIN_YAML.read_text(encoding="utf-8"), Loader=_SecretLoader)  # type: ignore[union-attr]
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        return  # let check_3_yaml_parses handle parse errors
    if not isinstance(cfg, dict):
        return

    secrets_text = SECRETS.read_text(encoding="utf-8")
    # Walk the YAML and collect every `!secret <key>` reference.
    # The `_SecretLoader` resolves `!secret` to the literal string
    # after the tag, so values like `api_encryption_key_radar` are
    # plain strings in the parsed dict.
    referenced_secrets: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            # `!secret` was resolved to the literal string. We do not
            # distinguish `!secret api_encryption_key_radar` from
            # the literal string `"api_encryption_key_radar"`, so we
            # only flag keys that match the `api_encryption_key_*`
            # pattern.
            if node.startswith("api_encryption_key_"):
                referenced_secrets.add(node)

    walk(cfg)

    for ref in sorted(referenced_secrets):
        # The secrets.yaml format is `api_encryption_key_<név>:
        # "base64..."`. The key is a YAML key at the start of a line.
        if not re.search(
            rf"^{re.escape(ref)}:", secrets_text, re.MULTILINE
        ):
            fail(
                f"firmware/radar.yaml references `!secret {ref}` but "
                f"`{ref}` is not defined in firmware/secrets.yaml. "
                f"Run `scripts/new_node.sh <név>` to generate a fresh "
                f"per-node API encryption key, or manually append "
                f"`{ref}: \"<32-byte-base64>\"` to secrets.yaml."
            )


def check_3_yaml_parses() -> None:
    """Quick syntax check: the YAML must parse.

    The full structural validation happens in
    `check_6b_platformio_options_structure` (PyYAML parse +
    `platformio_options.build_flags` schema check). This check is
    a fast early-exit so a parse error in the YAML gets a clear
    error message before the more expensive PyYAML walk.

    When PyYAML is not available (NAS fallback), this check is
    a no-op — the YAML structure is not validated, but the
    substring checks in `check_4_ld2410_yaml` still run.
    """
    if not _HAS_YAML:
        return
    if not MAIN_YAML.exists():
        fail(f"{MAIN_YAML} not found.")
    try:
        yaml.load(MAIN_YAML.read_text(encoding="utf-8"), Loader=_SecretLoader)  # type: ignore[union-attr]
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        fail(f"firmware/radar.yaml does not parse: {e}")


def _strip_yaml_comments(text: str) -> str:
    """Drop YAML comments from a string.

    A line starting with `#` (after optional whitespace) is a
    full-line comment. A `#` after non-whitespace starts a trailing
    comment. We strip everything from the first unquoted `#` to
    the end of the line. The state machine is simple; YAML
    strings rarely embed unquoted `#` in this firmware.

    Used by check_4_ld2410_yaml to avoid substring false-positives
    where the docs/comment text mentions `ld2420` / `ld2420_energy`
    for historical context.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        in_single = False
        in_double = False
        cut = -1
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                cut = i
                break
        if cut >= 0:
            line = line[:cut].rstrip()
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def check_4_ld2410_yaml() -> None:
    """Guard the v1.1.0 LD2410 configuration.

    Verifies that the v1.1.0 firmware/radar.yaml targets the
    LD2410 sensor (not the v1.0.0 LD2420). The check is named
    `check_4_ld2410_yaml` (replaces the old `check_4_gate_keys`
    that asserted 16 `gate_energy_N:` keys for the LD2420 build).

    Verifies that:
    - the YAML contains an `ld2410:` block (hub)
    - the YAML contains a `binary_sensor: - platform: ld2410` block
    - the YAML contains a `sensor: - platform: ld2410` block
    - the `uart.baud_rate:` substitution is `${ld2410_baud}` (NOT
      `${ld2420_baud}`), and the substitution defaults to `256000`
    - there is at least one `has_target:`/`has_moving_target:`/
      `has_still_target:` binary sensor
    - the legacy `ld2420:` / `platform: ld2420` strings are
      NOT present (would silently compile but produce a sensor
      that never reports anything because no LD2420 is attached)
    - the legacy `external_components: ... [ld2420_energy]` block
      is NOT loaded (the LD2410 build does not need the local
      component; the directory stays in the repo for v1.0.0
      archives only)
    """
    raw_text = MAIN_YAML.read_text(encoding="utf-8")
    text = _strip_yaml_comments(raw_text)
    failures: list[str] = []

    if "ld2410:" not in text:
        failures.append("missing top-level `ld2410:` hub block")
    if "platform: ld2410" not in text:
        failures.append(
            "missing any `platform: ld2410` block (binary_sensor / "
            "sensor / number / select / button / switch)"
        )
    if "uart.baud_rate: ${ld2410_baud}" not in text and "baud_rate: ${ld2410_baud}" not in text:
        failures.append(
            "uart baud rate is not bound to ${ld2410_baud} — "
            "should be `256000` (LD2410 out-of-the-box), not "
            "`115200` (LD2420)"
        )
    if "256000" not in text:
        failures.append(
            "LD2410 default baud `256000` not referenced anywhere "
            "in the YAML (expected as the substitution default)"
        )
    if not any(
        keyword in text for keyword in ("has_target:", "has_moving_target:", "has_still_target:")
    ):
        failures.append(
            "no `has_target:` / `has_moving_target:` / `has_still_target:` "
            "binary sensor defined (LD2410 hub needs at least one)"
        )
    # text_sensor: in ESPHome 2026.9.1 the LD2410 schema key is
    # `version:` (CONF_VERSION), NOT `fw_version:`. The doksi
    # page (esphome.io/components/sensor/ld2410/) still shows
    # `fw_version:` which is misleading. Verified against
    # esphome/esphome@2026.9.1 esphome/components/ld2410/text_sensor.py
    #
    # The check is anchored on `fw_version:` (with the trailing
    # colon — the YAML key) to avoid false positives on words
    # like `fw_version_changed` or text content like
    # "fw_version error message".
    if re.search(r"^\s*fw_version:\s*$", text, re.MULTILINE):
        failures.append(
            "the YAML still contains `fw_version:` (as a YAML key) — "
            "the LD2410 text_sensor schema key in ESPHome 2026.9.1 is "
            "`version:` (verified against esphome@2026.9.1 "
            "esphome/components/ld2410/text_sensor.py). The doksi "
            "page (esphome.io) is out of date; the code is the source "
            "of truth."
        )
    # button: in ESPHome 2026.9.1 the LD2410 button schema key
    # is `query_params` (CONF_QUERY_PARAMS), NOT `query`. The
    # doksi page (esphome.io) shows `query` which is misleading.
    # Verified against esphome/esphome@2026.9.1
    # esphome/components/ld2410/button/__init__.py.
    #
    # The check is scoped to the `button:` block to avoid false
    # positives on `name:` or `id:` fields in other platform blocks
    # that happen to contain the substring "query".
    button_match = re.search(
        r"^button:\n((?:  - .*?\n)*?)(?=^[^ ]|\Z)", text, re.MULTILINE | re.DOTALL
    )
    if button_match:
        button_block = button_match.group(1)
        if re.search(r"^    query:\s*$", button_block, re.MULTILINE):
            failures.append(
                "the LD2410 button block uses `query:` — the schema "
                "key in ESPHome 2026.9.1 is `query_params:` (CONF_QUERY_PARAMS). "
                "Verified against esphome@2026.9.1 "
                "esphome/components/ld2410/button/__init__.py."
            )
    if "ld2420:" in text or "platform: ld2420" in text:
        failures.append(
            "the YAML still contains `ld2420:` / `platform: ld2420` "
            "references — for a node with an LD2420 module, use the "
            "v1.0.0 firmware instead (or restore the v1.0.0 YAML)"
        )
    # The legacy `external_components: ... [ld2420_energy]` block is
    # NOT loaded by v1.1.0 (LD2410 is upstream-native). The check
    # looks for the *active* (comment-stripped) string, so the
    # v1.0.0-history references in YAML comments do not trip it.
    if re.search(r"^\s*external_components:\s*$", text, re.MULTILINE):
        # There is an `external_components:` block; verify it does
        # not load the legacy `ld2420_energy` component. (v1.1.0
        # does not need any external_components; the LD2410
        # component is upstream-native.)
        if "ld2420_energy" in text:
            failures.append(
                "the YAML's `external_components:` block loads "
                "`ld2420_energy` — the LD2410 firmware does not need "
                "it and it will fail to build because "
                "`components/ld2420_energy/sensor.py` references the "
                "upstream LD2420Component which is not present in "
                "the LD2410 hub context"
            )
    if "ld2420_baud" in text:
        failures.append(
            "the `ld2420_baud` substitution is still present — the "
            "LD2410 build uses `ld2410_baud: 256000`"
        )

    if failures:
        joined = "; ".join(failures)
        fail(
            f"firmware/radar.yaml is not a valid v1.1.0 LD2410 "
            f"config. {joined}. See the v1.0.0 firmware tag and the "
            f"docs/RELEASE_NOTES_v1.0.0.md for the LD2420 layout, or "
            f"the docs/RELEASE_NOTES_v1.1.0.md draft for the LD2410 "
            f"layout."
        )


def check_5_component_files() -> None:
    """Verify the legacy `components/ld2420_energy/` directory is
    still present (v1.0.0 archive).

    The v1.1.0 LD2410 build does not need the local component, but
    the directory must remain on disk for `git checkout v1.0.0 --`
    to work when reverting a node from v1.1.0 to v1.0.0. (See
    `docs/RELEASE_NOTES_v1.1.0.md` → "How to revert a node to
    v1.0.0 (LD2420 hardware)".) It is unrelated to `git status`
    hygiene — the `clean.sh` script and `firmware/.gitignore`
    (added by ESPHome on first build) handle the build-cache
    files that pollute `git status` (e.g. `firmware/.esphome/`,
    `firmware/components/`).
    """
    required = ["__init__.py", "sensor.py", "sensor.h", "sensor.cpp"]
    missing = [f for f in required if not (COMPONENT / f).exists()]
    if missing:
        fail(
            f"components/ld2420_energy/ missing: {missing} — the "
            "directory is a v1.0.0 archive (LD2420 16-gate energy) "
            "and must be kept on disk for `git checkout v1.0.0 --` to "
            "revert a node to the LD2420 firmware."
        )


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
    `-include stddef.h` flag puts `std::size_t` / `std::ptrdiff_t`
    in scope before any toolchain header is parsed.

    `stddef.h` is valid in both C and C++; `cstddef` would have
    been C++-only and would have failed on the .c files in
    ESPAsyncTCP / noise-c with "cstddef: No such file or
    directory" (first caught on
    .pioenvs/radar/libe9a/ESPAsyncTCP/tcp_axtls.c).

    If the flag is ever removed, the build dies with the same
    "std::size_t has not been declared" cascade that the original
    BL-01 was trying to avoid. If `cstddef` is substituted for
    `stddef.h`, the C TUs fail to compile.

    This check is the **substring fallback** — it only verifies
    that the literal string `-include stddef.h` appears in the
    YAML. The full structural validation (YAML list, no `cstddef`
    typo) happens in `check_6b_platformio_options_structure`.
    On the Mac (where PyYAML is always available) both run; on
    the NAS (where PyYAML is not installed) only this check
    runs and the structural validation is skipped. The redundancy
    is intentional: the substring check works everywhere and
    catches the common typo; the PyYAML check catches the rare
    "list-vs-string" YAML type mismatch.
    """
    text = MAIN_YAML.read_text(encoding="utf-8")
    if "-include stddef.h" not in text:
        fail(
            "firmware/radar.yaml is missing the BL-01b toolchain-xtensa@3.x "
            "workaround. The `esphome:` block must set "
            "`platformio_options.build_flags: [-include stddef.h]` to keep "
            "`std::size_t` / `std::ptrdiff_t` in scope before any toolchain "
            "header is parsed. NB: use `stddef.h`, NOT `cstddef` — the "
            "build also compiles .c files (ESPAsyncTCP/tcp_axtls.c) which "
            "only have the C standard library. Without it, the build dies "
            "with the 'std::size_t has not been declared' cascade in "
            "<hashtable_policy.h> and <tuple>, or — if `cstddef` is used — "
            "with 'cstddef: No such file or directory' on the .c files. "
            "See the long comment in firmware/radar.yaml and "
            "RELEASE_CHECKLIST.md BL-01b."
        )


def check_6b_platformio_options_structure() -> None:
    """Structural validation of the BL-01b `platformio_options` block.

    Verifies that:
    - the YAML parses,
    - the top-level `esphome:` block has a `platformio_options` mapping,
    - `platformio_options.build_flags` is a list (not a string),
    - the list contains the literal "-include stddef.h" (NOT cstddef).

    Catches the "looks right, but wrong YAML type" failure mode
    where e.g. `build_flags: -include stddef.h` (string, not list)
    passes the substring check in check_6 but is rejected by the
    ESPHome 2026.9.1 `esphome.config.CONFIG_SCHEMA` validator
    (`cv.Schema({cv.string_strict: cv.Any([cv.string], cv.string)})`).

    Also catches the "cstddef vs stddef.h" failure mode that
    would compile the .cpp translation units but fail on the .c
    ones in ESPAsyncTCP / noise-c.

    No-op when PyYAML is not available (NAS / CI without it).
    The substring fallback `check_6_cstddef_workaround` still
    runs in that case.
    """
    if not _HAS_YAML:
        return

    cfg = None
    try:
        cfg = yaml.load(MAIN_YAML.read_text(encoding="utf-8"), Loader=_SecretLoader)  # type: ignore[union-attr]
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        fail(f"firmware/radar.yaml does not parse: {e}")

    if cfg is None:
        fail("firmware/radar.yaml is empty or null after parsing.")

    esphome = cfg.get("esphome") if isinstance(cfg, dict) else None
    if not isinstance(esphome, dict):
        fail("firmware/radar.yaml is missing the top-level `esphome:` mapping.")

    pio_opts = esphome.get("platformio_options") if isinstance(esphome, dict) else None
    if not isinstance(pio_opts, dict):
        fail(
            "firmware/radar.yaml is missing "
            "`esphome.platformio_options:` (a mapping). The BL-01b workaround "
            "must be a `platformio_options.build_flags:` list, not a string."
        )

    build_flags = pio_opts.get("build_flags") if isinstance(pio_opts, dict) else None
    if not isinstance(build_flags, list):
        fail(
            "`esphome.platformio_options.build_flags` must be a YAML list "
            "(`- -include stddef.h`), not a scalar string. The ESPHome 2026.9.1 "
            "schema requires `dict[string, list[string] | str]` and a scalar "
            "is silently dropped at codegen time."
        )

    # Pyright cannot narrow `build_flags` from Any to list[str] through
    # the isinstance check above, so it still sees `list[Unknown] | None`
    # for the `in` / `not in` checks below. Re-assert the type to give
    # both the type-checker and human readers a clear local assumption.
    assert isinstance(build_flags, list)

    if "-include stddef.h" not in build_flags:
        fail(
            "`esphome.platformio_options.build_flags` does not contain "
            "`-include stddef.h`. The BL-01b toolchain-xtensa@3.x workaround "
            "must be in the list (alongside any other flags). NB: use "
            "`stddef.h`, NOT `cstddef` — the .c TUs would fail."
        )

    if "-include cstddef" in build_flags:
        fail(
            "`esphome.platformio_options.build_flags` contains "
            "`-include cstddef`. The build also compiles .c files "
            "(e.g. ESPAsyncTCP/tcp_axtls.c) which only have the C "
            "standard library; `cstddef` is C++-only and those TUs "
            "would fail with 'cstddef: No such file or directory'. "
            "Use `-include stddef.h` (valid in both C and C++)."
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
    check_2b_per_node_api_key()
    check_3_yaml_parses()
    check_4_ld2410_yaml()
    check_5_component_files()
    check_6_cstddef_workaround()
    check_6b_platformio_options_structure()
    check_7_register_listener()
    print("PRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())