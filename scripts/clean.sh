#!/usr/bin/env bash
# Wipe the ESPHome + PlatformIO caches so a stale toolchain (xtensa-lx106-elf
# 3.x / gcc 10.3.0, paired with platformio/espressif8266@4.2.1) cannot be
# picked up by a build that was started on the old toolchain.
#
# After this runs, the next `esphome run firmware/livingroom.yaml` will
# re-download:
#   - platformio/espressif8266@2.6.3    (pinned in livingroom.yaml)
#   - toolchain-xtensa@~2.100100.0      (gcc 5.2 — no std::size_t cascade)
#   - framework-arduinoespressif8266@~3.30102.0
#
# Run from the repo root:
#   scripts/clean.sh
#
# Optional: pass `--all` to also wipe ~/.platformio/packages so the next
# build re-downloads every package from scratch (slower; usually not needed).
#
# Safe to run while a build is in progress — it will fail loudly instead of
# silently producing a half-built firmware.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

echo "== Stopping any running esphome / platformio processes =="
pkill -f "esphome run" 2>/dev/null || true
pkill -f "platformio"  2>/dev/null || true
sleep 1

echo "== Wiping firmware/.esphome/build/ =="
rm -rf firmware/.esphome/build/

echo "== Wiping firmware/.esphome/storage/ =="
rm -rf firmware/.esphome/storage/

if [[ "${1:-}" == "--all" ]]; then
    echo "== Wiping ~/.platformio (--all requested) =="
    rm -rf "${HOME}/.platformio"
else
    echo "== Wiping only the toolchain + espressif8266 platform (NOT --all) =="
    rm -rf "${HOME}/.platformio/packages/toolchain-xtensa@"* \
           "${HOME}/.platformio/packages/framework-arduinoespressif8266@"* \
           "${HOME}/.platformio/platforms/espressif8266@"*
    echo "   (other packages like ESP8266WiFi, ESPAsyncTCP, etc. are kept)"
fi

echo ""
echo "== Done. Next step: =="
echo "   cd firmware && esphome run livingroom.yaml"
echo ""
echo "If the next build still pulls gcc 10.3.0 (xtensa-lx106-elf@3.x), then"
echo "the platform_version pin in firmware/livingroom.yaml is not being"
echo "honoured — verify with:"
echo "   grep platform_version firmware/livingroom.yaml"
