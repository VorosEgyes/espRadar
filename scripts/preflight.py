#!/usr/bin/env python3
"""Pre-flight smoke check before `esphome run`.

Run from the repo root. Exits non-zero on the first failure so it can be
wired into CI later.

v1.2.0 changes (BL-07, dual-radar dispatcher):
  - `MAIN_YAML` (singular) is replaced with `NODE_YAMLS` — every
    `firmware/*.yaml` file that is not `_common.yaml.include`,
    `radar_ld2410.yaml`, `radar_ld2420.yaml`, or `secrets.yaml(.example)`
    is a per-node firmware YAML and is checked.
  - `check_4` is now type-aware: it dispatches on the YAML's
    `substitutions.radar_type` value. An LD2410 build is validated
    against the LD2410 schema; an LD2420 build against the LD2420
    schema. A mixed build (e.g. radar_type=ld2410 with an `ld2420:`
    block) is rejected.
  - `check_6` (BL-01b toolchain workaround) runs on every per-node
    YAML AND on `_common.yaml.include` (the workaround lives in
    the common file, not in the per-node file).

v1.1.0 changes (kept):
  - check_2b_per_node_api_key: every per-node YAML references a
    `!secret api_encryption_key_<név>` key that must exist in
    secrets.yaml (BL-06).
  - check_6b_platformio_options_structure: structural PyYAML parse of
    the platformio_options block (list, not string; -include stddef.h,
    not cstddef).
  - check_7_register_listener: components/ld2420_energy/sensor.py
    uses register_listener, not add_listener.

Checks (v1.2.0):
  1.  firmware/secrets.yaml exists.
  2.  secrets.yaml has no placeholder values left in.
  2b. Every per-node YAML's `!secret api_encryption_key_<név>` is
      defined in secrets.yaml.
  3.  Every per-node YAML parses as YAML.
  4.  Per-node YAMLs are valid LD2410 or LD2420 configs (dispatched
      on `substitutions.radar_type`).
  5.  components/ld2420_energy/ contains all four source files
      (v1.0.0 archive).
  6.  BL-01b `-include stddef.h` workaround is present in every
      per-node YAML and in `_common.yaml.include`.
  6b. The `platformio_options.build_flags` list is structurally
      valid (-include stddef.h, not cstddef).
  7.  The legacy `components/ld2420_energy/sensor.py` does not use
      the add_listener typo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


# PyYAML is always available where `esphome` is installed (the
# Mac). The preflight is also run from the NAS for a structural
# sanity check before committing, and the NAS does not have
# PyYAML. The import is therefore wrapped in a try/except: the
# bare-minimum checks (e.g. check_1, check_2) still work without
# PyYAML, and the structural checks (check_3, check_4, check_6b)
# are no-ops when PyYAML is missing.
try:
    import yaml  # type: ignore[import-not-found]
    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


# ESPHome extends YAML with `!secret` tags — load them as plain strings so
# preflight does not require the ESPHome Python environment to parse the
# configuration files.
#
# v1.2.0 (BL-07): also recognise `!include { file: ... }` tags. The
# `!include` tag appears under the `packages:` block in a per-node
# YAML (e.g. `radar: !include radar_ld2410.yaml`). The
# `_resolve_includes` walker (below) walks the parsed YAML tree and
# recursively loads any `!include` reference; the resolved YAML is
# then used for the structural checks (check_2b, check_4, check_6b).
if _HAS_YAML:
    class _SecretLoader(yaml.SafeLoader):  # type: ignore[misc]
        pass

    _SecretLoader.add_constructor(  # type: ignore[attr-defined]
        "!secret",
        # type: ignore[no-untyped-def]
        lambda loader, node: loader.construct_scalar(node),
    )

    def _include_constructor(loader, node):  # type: ignore[no-untyped-def]
        """Handle `!include { file: ..., vars: ... }` tags.

        Returns a dict `{"__include__": file, "vars": vars}` so the
        `!include` directive is preserved as a marker in the parsed
        tree; `_resolve_includes` later walks the tree and substitutes
        the marker with the file's contents.

        ESPHome's `!include` accepts three forms:
          1. `!include filename.yaml` (scalar)
          2. `!include { file: filename.yaml }` (inline mapping)
          3. `!include` on its own line followed by `file: ...` and
             `vars: ...` keys (block mapping — same as form 2 here)
        The `!include` may also carry a `vars:` mapping that provides
        per-include substitution overrides; we capture but do not
        apply them (the check is structural, not substitution-aware).
        """
        if isinstance(node, yaml.ScalarNode):  # type: ignore[union-attr]
            return {"__include__": loader.construct_scalar(node), "vars": {}}
        if isinstance(node, yaml.MappingNode):  # type: ignore[union-attr]
            mapping = loader.construct_mapping(node, deep=True)
            return {
                "__include__": mapping.get("file", ""),
                "vars": mapping.get("vars", {}) or {},
            }
        raise yaml.YAMLError(  # type: ignore[union-attr]
            f"unsupported !include node: {node!r}"
        )

    _SecretLoader.add_constructor(  # type: ignore[attr-defined]
        "!include", _include_constructor
    )
else:
    _SecretLoader = None  # type: ignore[assignment]


def _resolve_includes(node: object, base_dir: Path) -> object:
    """Walk a parsed YAML tree and substitute `!include` markers with
    the file contents.

    ESPHome uses `!include { file: ... }` under the `packages:`
    block to pull in shared configuration fragments. This walker
    mirrors the relevant subset of that behaviour for preflight:
    any mapping `{"__include__": file, "vars": ...}` is replaced
    with the parsed YAML of `base_dir / file`. Cyclic includes
    (A includes B includes A) are caught via the `seen` set and
    reported as a preflight failure.

    `vars:` overrides are applied to the included file's
    `substitutions:` block if it has one; this is a best-effort
    emulation of ESPHome's per-include substitution override. The
    preflight does NOT enforce that the override keys exist in the
    included file's substitutions (ESPHome does that at codegen).
    """
    if isinstance(node, dict):
        if "__include__" in node:
            rel = str(node["__include__"])
            target = (base_dir / rel).resolve()
            # Cycle guard: each include file is loaded at most once per
            # top-level resolve_includes call.
            cycle_key = str(target)
            if cycle_key in _resolve_includes._seen:  # type: ignore[attr-defined]
                fail(
                    f"cyclic !include detected: {rel} is included "
                    f"more than once in the same resolution path"
                )
            _resolve_includes._seen.add(cycle_key)  # type: ignore[attr-defined]
            if not target.is_file():
                fail(
                    f"!include references missing file: {rel} "
                    f"(resolved: {target})"
                )
            included = None
            try:
                included = yaml.load(  # type: ignore[union-attr]
                    target.read_text(encoding="utf-8"), Loader=_SecretLoader
                )
            except yaml.YAMLError as e:  # type: ignore[union-attr]
                fail(f"!include target {rel} does not parse: {e}")
            assert included is not None
            # Apply vars to the included file's substitutions if any.
            vars_override = node.get("vars") or {}
            if vars_override and isinstance(included, dict):
                included_sub = included.get("substitutions")
                if isinstance(included_sub, dict):
                    included_sub.update(vars_override)
            included = _resolve_includes(included, base_dir.parent)
            _resolve_includes._seen.discard(cycle_key)  # type: ignore[attr-defined]
            return included
        return {
            k: _resolve_includes(v, base_dir)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_resolve_includes(v, base_dir) for v in node]
    return node


# Initialise the cycle-guard set on the function (used as a
# per-call context). The set is mutated by `_resolve_includes` and
# discarded at the end of each top-level call.
_resolve_includes._seen = set()  # type: ignore[attr-defined]


REPO = Path(__file__).resolve().parent.parent
FIRMWARE = REPO / "firmware"
SECRETS = FIRMWARE / "secrets.yaml"
COMMON_INCLUDE = FIRMWARE / "_common.yaml.include"
RADAR_TEMPLATES = ("radar_ld2410.yaml", "radar_ld2420.yaml")
COMPONENT = REPO / "components" / "ld2420_energy"


def _is_per_node_yaml(path: Path) -> bool:
    """True if `path` is a per-node firmware YAML (not a template).

    A per-node YAML is:
    - inside `firmware/`,
    - has a `.yaml` extension,
    - is not `secrets.yaml` (and not the `.example`),
    - is not `radar.yaml` (the BL-07 template from which
      `scripts/new_node.sh` clones new nodes),
    - is not a template include (`_common.yaml.include` or one of
      the `radar_ld*.yaml` include files).
    """
    if path.parent != FIRMWARE:
        return False
    if path.suffix != ".yaml":
        return False
    if path.name == "secrets.yaml":
        return False
    if path.name in RADAR_TEMPLATES:
        return False
    if path.name == "radar.yaml":
        return False
    return True


def _per_node_yamls() -> list[Path]:
    if not FIRMWARE.is_dir():
        return []
    return sorted(p for p in FIRMWARE.iterdir() if _is_per_node_yaml(p))


def fail(msg: str) -> None:
    print(f"PRE-FLIGHT FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# check_1 / check_2 — secrets.yaml presence + placeholder detection
# ============================================================================


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


# ============================================================================
# check_2b — every per-node YAML's !secret api_encryption_key_<név>
# ============================================================================


def _walk_api_secrets(node: object, out: set[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _walk_api_secrets(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_api_secrets(v, out)
    elif isinstance(node, str):
        if node.startswith("api_encryption_key_"):
            out.add(node)


def _per_node_referenced_secrets(path: Path) -> set[str]:
    """Return the set of `api_encryption_key_*` strings referenced in `path`.

    Walks the parsed YAML and collects every string value that starts
    with `api_encryption_key_`. The `!secret` tag was resolved to the
    literal string by `_SecretLoader`, so the string we see is the key
    name (e.g. `api_encryption_key_radar`).

    v1.2.0 (BL-07): the YAML is first walked through
    `_resolve_includes` so `!include` references in the per-node
    YAML's `packages:` block are substituted with the included
    file's contents. This catches `!secret` references in
    `_common.yaml.include` (e.g. `api_encryption_key_${device_name}`)
    and in `radar_ld<type>.yaml`.

    Returns an empty set if PyYAML is unavailable or the YAML is
    unparseable (in that case the caller's check_3 will report the
    parse error).
    """
    if not _HAS_YAML:
        return set()
    try:
        cfg = yaml.load(  # type: ignore[union-attr]
            path.read_text(encoding="utf-8"), Loader=_SecretLoader
        )
    except yaml.YAMLError:  # type: ignore[union-attr]
        return set()
    if cfg is None:
        return set()
    cfg = _resolve_includes(cfg, path.parent)
    out: set[str] = set()
    _walk_api_secrets(cfg, out)
    return out


def check_2b_per_node_api_key() -> None:
    """Guard BL-06 per-node API encryption keys across all per-node YAMLs."""
    if not _HAS_YAML:
        return
    if not SECRETS.exists():
        return
    secrets_text = SECRETS.read_text(encoding="utf-8")

    for node_yaml in _per_node_yamls():
        referenced = _per_node_referenced_secrets(node_yaml)
        for ref in sorted(referenced):
            if not re.search(rf"^{re.escape(ref)}:", secrets_text, re.MULTILINE):
                fail(
                    f"{node_yaml.relative_to(REPO)} references "
                    f"`!secret {ref}` but `{ref}` is not defined in "
                    f"firmware/secrets.yaml. Run `scripts/new_node.sh "
                    f"<név>` to generate a fresh per-node API encryption "
                    f"key, or manually append `{ref}: \"<32-byte-base64>\"` "
                    f"to secrets.yaml."
                )


# ============================================================================
# check_3 — every per-node YAML parses
# ============================================================================


def check_3_yaml_parses() -> None:
    if not _HAS_YAML:
        return
    for node_yaml in _per_node_yamls():
        try:
            yaml.load(  # type: ignore[union-attr]
                node_yaml.read_text(encoding="utf-8"), Loader=_SecretLoader
            )
        except yaml.YAMLError as e:  # type: ignore[union-attr]
            fail(f"{node_yaml.relative_to(REPO)} does not parse: {e}")


# ============================================================================
# check_4 — per-node YAML is a valid LD2410 or LD2420 config
# ============================================================================


def _strip_yaml_comments(text: str) -> str:
    """Drop YAML comments from a string.

    A line starting with `#` (after optional whitespace) is a
    full-line comment. A `#` after non-whitespace starts a trailing
    comment. We strip everything from the first unquoted `#` to
    the end of the line. The state machine is simple; YAML
    strings rarely embed unquoted `#` in this firmware.
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


def _detect_radar_type(text: str) -> str | None:
    """Detect the radar_type from a per-node YAML.

    The substitutions block looks like:
        substitutions:
          device_name: bedroom
          radar_type: ld2410

    We look for the literal `radar_type:` key and read the value
    on the same line. Returns None if the substitution is missing.
    """
    m = re.search(
        r"^\s*radar_type:\s*(\S+)\s*$", text, re.MULTILINE
    )
    return m.group(1) if m else None


def _check_ld2410_text(text: str) -> list[str]:
    """Return a list of human-readable failure messages for an LD2410 build."""
    failures: list[str] = []
    if "ld2410:" not in text:
        failures.append("missing top-level `ld2410:` hub block")
    if "platform: ld2410" not in text:
        failures.append(
            "missing any `platform: ld2410` block (binary_sensor / "
            "sensor / number / select / button / switch)"
        )
    if "ld2420:" in text or "platform: ld2420" in text:
        failures.append(
            "the YAML still contains `ld2420:` / `platform: ld2420` "
            "references — radar_type is `ld2410`; remove them or use "
            "the v1.0.0 firmware / the radar_ld2420.yaml include for "
            "LD2420 nodes"
        )
    # v1.2.0 (BL-07): the per-node YAML defines BOTH `ld2410_baud`
    # and `ld2420_baud` substitutions (the dispatcher picks the
    # right one based on `radar_type`; the other is ignored). The
    # presence of `ld2420_baud` is therefore NOT a violation; what
    # matters is which baud the `uart.baud_rate:` line actually
    # references.
    if "ld2420_energy" in text:
        failures.append(
            "the YAML references `ld2420_energy` (the local listener "
            "for the v1.0.0 LD2420 build) — radar_type is `ld2410`; "
            "the LD2410 build does not need it and it would fail to "
            "compile because sensor.py references the upstream "
            "LD2420Component which is not present in the LD2410 hub"
        )
    if not any(
        keyword in text
        for keyword in ("has_target:", "has_moving_target:", "has_still_target:")
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
    # is `query_params` (CONF_QUERY_PARAMS), NOT `query`.
    button_match = re.search(
        r"^button:\n((?:  - .*?\n)*?)(?=^[^ ]|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if button_match:
        button_block = button_match.group(1)
        if re.search(r"^    query:\s*$", button_block, re.MULTILINE):
            failures.append(
                "the LD2410 button block uses `query:` — the schema "
                "key in ESPHome 2026.9.1 is `query_params:` (CONF_QUERY_PARAMS)."
            )
    return failures


def _check_ld2420_text(text: str) -> list[str]:
    """Return a list of human-readable failure messages for an LD2420 build."""
    failures: list[str] = []
    if "ld2420:" not in text:
        failures.append("missing top-level `ld2420:` hub block")
    if "platform: ld2420" not in text:
        failures.append(
            "missing any `platform: ld2420` block (binary_sensor / "
            "sensor / number / select / button / switch)"
        )
    if "ld2410:" in text or "platform: ld2410" in text:
        failures.append(
            "the YAML still contains `ld2410:` / `platform: ld2410` "
            "references — radar_type is `ld2420`; remove them or use "
            "the radar_ld2410.yaml include for LD2410 nodes"
        )
    # v1.2.0 (BL-07): the per-node YAML defines BOTH `ld2410_baud`
    # and `ld2420_baud` substitutions (the dispatcher picks the
    # right one based on `radar_type`; the other is ignored). The
    # presence of `ld2410_baud` is therefore NOT a violation; what
    # matters is which baud the `uart.baud_rate:` line actually
    # references.
    if "engineering_mode" in text:
        # Engineering mode is an LD2410-only concept (auto-disables
        # after 5 min). The LD2420 exposes operating_mode (Normal /
        # Calibrate / Simple) instead.
        failures.append(
            "the YAML references `engineering_mode:` — that is an "
            "LD2410-only switch; the LD2420 build uses `operating_mode:` "
            "(Normal / Calibrate / Simple) under `select:`"
        )
    if "g0:\n      move_threshold:" in text or "g0:\n      still_threshold:" in text:
        # The LD2420 exposes per-gate thresholds through a single
        # `gate_select` number (which gate to set) plus a single
        # `move_threshold` / `still_threshold` pair. The LD2410 has
        # g0..g8 move_threshold / still_threshold directly.
        failures.append(
            "the YAML has per-gate `g0..g8` move/still_threshold "
            "blocks — that is the LD2410 schema; the LD2420 uses a "
            "single `gate_select` number + `move_threshold` / "
            "`still_threshold` pair (one gate at a time)"
        )
    if not re.search(r"^\s*has_target:\s*$", text, re.MULTILINE):
        failures.append(
            "no `has_target:` binary sensor defined (LD2420 hub needs "
            "at least one)"
        )
    return failures


def check_4_radar_yaml() -> None:
    """Per-node YAMLs are valid LD2410 or LD2420 configs.

    Dispatches on `substitutions.radar_type`. A build without a
    `radar_type` substitution (or with a value other than `ld2410` /
    `ld2420`) is rejected — the dispatcher requires an explicit
    type so the wrong-platform build is caught at preflight time
    rather than producing a node that compiles but never reports.

    v1.2.0 (BL-07): the per-node YAML's `!include` directives are
    resolved before the schema check, so the LD2410 / LD2420
    detection sees the include-olt blocks (radar_ld<type>.yaml)
    instead of the bare `!include` marker. This means the check
    can dispatch on the actual radar component (`ld2410:` vs
    `ld2420:`) rather than on the include target.
    """
    for node_yaml in _per_node_yamls():
        if not _HAS_YAML:
            # Without PyYAML, fall back to the raw-text check: read
            # the radar_type substitution directly from the file.
            raw_text = node_yaml.read_text(encoding="utf-8")
            text = _strip_yaml_comments(raw_text)
            radar_type = _detect_radar_type(text)
            # Append the include-olt block contents so the schema
            # checks below see the actual `ld2410:` / `ld2420:`
            # blocks (not just the `!include` markers in the per-node
            # YAML). The PyYAML branch above does the same via
            # `_resolve_includes`; the substring branch has to do
            # it by file concatenation because `_resolve_includes`
            # requires PyYAML.
            common_inc = node_yaml.parent / "_common.yaml.include"
            if common_inc.is_file():
                text += "\n" + _strip_yaml_comments(
                    common_inc.read_text(encoding="utf-8")
                )
            if radar_type in ("ld2410", "ld2420"):
                radar_inc = node_yaml.parent / f"radar_{radar_type}.yaml"
                if radar_inc.is_file():
                    text += "\n" + _strip_yaml_comments(
                        radar_inc.read_text(encoding="utf-8")
                    )
        else:
            cfg = None
            try:
                cfg = yaml.load(  # type: ignore[union-attr]
                    node_yaml.read_text(encoding="utf-8"),
                    Loader=_SecretLoader,
                )
            except yaml.YAMLError as e:  # type: ignore[union-attr]
                fail(f"{node_yaml.relative_to(REPO)} does not parse: {e}")
            if cfg is None:
                fail(f"{node_yaml.relative_to(REPO)} is empty or null after parsing.")
            cfg = _resolve_includes(cfg, node_yaml.parent)
            substitutions = (
                cfg.get("substitutions")
                if isinstance(cfg, dict) and isinstance(cfg.get("substitutions"), dict)
                else {}
            )
            radar_type = substitutions.get("radar_type") if isinstance(substitutions, dict) else None
            # The structural text check is still useful (catches
            # typos in the included files). Re-read the raw text for
            # the substring / regex checks; the dispatch is on the
            # resolved `radar_type`.
            text = _strip_yaml_comments(node_yaml.read_text(encoding="utf-8"))
            # Append the include-olt block contents so the schema
            # checks below see the actual `ld2410:` / `ld2420:`
            # blocks, the per-gate numbers, the engineering_mode
            # switch, etc. — not just the `!include` markers. We
            # append `_common.yaml.include` (always) and the
            # radar-specific include that matches the resolved
            # `radar_type`. The other radar's include is
            # intentionally NOT appended, because its presence in
            # the text would cause false positives in the schema
            # checks (e.g. the LD2410 check would see `has_target:`
            # in the LD2420 block and silently pass on a build
            # that has neither the LD2410 nor the LD2420 hub).
            common_inc = node_yaml.parent / "_common.yaml.include"
            if common_inc.is_file():
                text += "\n" + _strip_yaml_comments(
                    common_inc.read_text(encoding="utf-8")
                )
            if radar_type in ("ld2410", "ld2420"):
                radar_inc = node_yaml.parent / f"radar_{radar_type}.yaml"
                if radar_inc.is_file():
                    text += "\n" + _strip_yaml_comments(
                        radar_inc.read_text(encoding="utf-8")
                    )

        if radar_type is None:
            fail(
                f"{node_yaml.relative_to(REPO)} is missing "
                f"`substitutions.radar_type:` — the v1.2.0 dispatcher "
                f"requires every per-node YAML to declare its radar "
                f"type. Set `radar_type: ld2410` or `radar_type: ld2420` "
                f"in the `substitutions:` block at the top of the file."
            )
        if radar_type == "ld2410":
            failures = _check_ld2410_text(text)
            kind = "LD2410"
        elif radar_type == "ld2420":
            failures = _check_ld2420_text(text)
            kind = "LD2420"
        else:
            fail(
                f"{node_yaml.relative_to(REPO)} has "
                f"`substitutions.radar_type: {radar_type}` — only "
                f"`ld2410` and `ld2420` are supported. Use "
                f"`radar_ld2410.yaml` / `radar_ld2420.yaml` includes."
            )
            continue  # unreachable, but keeps type-narrowing happy
        if failures:
            joined = "; ".join(failures)
            fail(
                f"{node_yaml.relative_to(REPO)} is not a valid v1.2.0 "
                f"{kind} config. {joined}."
            )


# ============================================================================
# check_5 — components/ld2420_energy/ archive
# ============================================================================


def check_5_component_files() -> None:
    """Verify the legacy `components/ld2420_energy/` directory is
    still present (v1.0.0 archive).

    The v1.1.0+ LD2410 builds do not need the local component, but
    the directory must remain on disk for `git checkout v1.0.0 --`
    to work when reverting a node from v1.2.0 to v1.0.0. It is
    unrelated to `git status` hygiene — the `clean.sh` script and
    `firmware/.gitignore` (added by ESPHome on first build) handle
    the build-cache files that pollute `git status`.
    """
    required = ["__init__.py", "sensor.py", "sensor.h", "sensor.cpp"]
    missing = [f for f in required if not (COMPONENT / f).exists()]
    if missing:
        fail(
            f"components/ld2420_energy/ missing: {missing} — the "
            f"directory is a v1.0.0 archive (LD2420 16-gate energy) "
            f"and must be kept on disk for `git checkout v1.0.0 --` to "
            f"revert a node to the LD2420 firmware."
        )


# ============================================================================
# check_6 / check_6b — BL-01b toolchain workaround
# ============================================================================


def _check_bl01b_text(path: Path, text: str) -> list[str]:
    """Check the BL-01b workaround in `text` (raw, comment-stripped
    is the caller's choice). Returns a list of failure messages.

    The text is stripped of YAML comments before the substring
    checks: the v1.1.0 `radar.yaml` has a long BL-01b rationale
    comment that mentions both `-include cstddef` (the bad
    alternative) and `-include stddef.h` (the right one) for
    historical context. A naive substring check on the raw text
    would flag the comment as a violation.
    """
    active = _strip_yaml_comments(text)
    failures: list[str] = []
    if "-include stddef.h" not in active:
        failures.append(
            f"{path.relative_to(REPO)} is missing the BL-01b "
            f"toolchain-xtensa@3.x workaround. The `esphome:` block "
            f"must set `platformio_options.build_flags: "
            f"[-include stddef.h]`. See the comment in "
            f"firmware/_common.yaml.include and RELEASE_CHECKLIST.md "
            f"BL-01b for the full diagnosis."
        )
    if "-include cstddef" in active:
        failures.append(
            f"{path.relative_to(REPO)} contains `-include cstddef` — "
            f"the build also compiles .c files (e.g. "
            f"ESPAsyncTCP/tcp_axtls.c) which only have the C standard "
            f"library; `cstddef` is C++-only and those TUs would fail "
            f"with 'cstddef: No such file or directory'. Use "
            f"`-include stddef.h` (valid in both C and C++)."
        )
    return failures


def check_6_cstddef_workaround() -> None:
    """Guard the BL-01b toolchain-xtensa@3.x libstdc++ workaround.

    v1.2.0 (BL-07): the workaround lives in
    `firmware/_common.yaml.include` (not in the per-node YAMLs,
    which only !include the common file). The check therefore
    runs only on `_common.yaml.include` — running it on per-node
    YAMLs would fail because the per-node YAMLs do not contain
    the literal string `-include stddef.h` (they pull it in via
    `!include`). The check still catches a missing
    `_common.yaml.include` (the file is gone → check_6 fails)
    and a wrong content (e.g. `-include cstddef` typo).
    """
    if not COMMON_INCLUDE.exists():
        fail(
            f"firmware/_common.yaml.include is missing — the v1.2.0 "
            f"dispatcher requires the common include file (it carries "
            f"the BL-01b toolchain-xtensa@3.x workaround, the per-node "
            f"API encryption key binding, and the wifi/api/ota blocks)."
        )
    text = COMMON_INCLUDE.read_text(encoding="utf-8")
    for f in _check_bl01b_text(COMMON_INCLUDE, text):
        fail(f)


def _check_bl01b_structure(path: Path) -> None:
    """Structural PyYAML parse of the platformio_options block."""
    if not _HAS_YAML:
        return
    cfg = None
    try:
        cfg = yaml.load(  # type: ignore[union-attr]
            path.read_text(encoding="utf-8"), Loader=_SecretLoader
        )
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        fail(f"{path.relative_to(REPO)} does not parse: {e}")
    if cfg is None:
        fail(f"{path.relative_to(REPO)} is empty or null after parsing.")

    esphome_block = cfg.get("esphome") if isinstance(cfg, dict) else None
    if not isinstance(esphome_block, dict):
        fail(
            f"{path.relative_to(REPO)} is missing the top-level "
            f"`esphome:` mapping."
        )

    pio_opts = (
        esphome_block.get("platformio_options")
        if isinstance(esphome_block, dict)
        else None
    )
    if not isinstance(pio_opts, dict):
        fail(
            f"{path.relative_to(REPO)} is missing "
            f"`esphome.platformio_options:` (a mapping). The BL-01b "
            f"workaround must be a "
            f"`platformio_options.build_flags:` list, not a string."
        )

    build_flags = (
        pio_opts.get("build_flags") if isinstance(pio_opts, dict) else None
    )
    if not isinstance(build_flags, list):
        fail(
            f"`esphome.platformio_options.build_flags` in "
            f"{path.relative_to(REPO)} must be a YAML list "
            f"(`- -include stddef.h`), not a scalar string. The "
            f"ESPHome 2026.9.1 schema requires "
            f"`dict[string, list[string] | str]` and a scalar is "
            f"silently dropped at codegen time."
        )

    assert isinstance(build_flags, list)
    if "-include stddef.h" not in build_flags:
        fail(
            f"`esphome.platformio_options.build_flags` in "
            f"{path.relative_to(REPO)} does not contain "
            f"`-include stddef.h`. See RELEASE_CHECKLIST.md BL-01b."
        )


def check_6b_platformio_options_structure() -> None:
    """Structural validation of the BL-01b `platformio_options` block.

    v1.2.0 (BL-07): runs only on `_common.yaml.include` (where the
    workaround actually lives). The per-node YAMLs do not define
    `platformio_options` — they pull it in via `!include`. Running
    the check on per-node YAMLs would fail because the per-node
    YAMLs do not have a `platformio_options:` key.
    """
    if not COMMON_INCLUDE.exists():
        return  # check_6 already reported the missing file
    _check_bl01b_structure(COMMON_INCLUDE)


# ============================================================================
# check_7 — components/ld2420_energy/sensor.py uses register_listener
# ============================================================================


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
            f"LD2420Component method is `register_listener` (verified "
            f"against esphome@2026.9.1 esphome/components/ld2420/ld2420.h:102)."
        )


# ============================================================================
# main
# ============================================================================


def main() -> int:
    check_1_secrets()
    check_2_no_placeholders()
    check_2b_per_node_api_key()
    check_3_yaml_parses()
    check_4_radar_yaml()
    check_5_component_files()
    check_6_cstddef_workaround()
    check_6b_platformio_options_structure()
    check_7_register_listener()
    print("PRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
