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


def main() -> int:
    check_1_secrets()
    check_2_no_placeholders()
    check_3_yaml_parses()
    check_4_gate_keys()
    check_5_component_files()
    print("PRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())