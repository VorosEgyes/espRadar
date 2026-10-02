#!/usr/bin/env bash
# Wipe the ESPHome + PlatformIO caches so a stale toolchain cannot be
# picked up by a build that was started on an old toolchain.
#
# After this runs, the next `esphome run firmware/livingroom.yaml` will
# re-download:
#   - platformio/espressif8266@4.2.1    (default; BL-01's 2.6.3 pin was
#                                         structurally incompatible with
#                                         ESPHome 2026.9.1, see BL-01a)
#   - toolchain-xtensa@3.x              (gcc 10.3.0)
#   - framework-arduinoespressif8266@3.1.2
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
echo "If the build dies with the 'std::size_t has not been declared' cascade,"
echo "or with 'cstddef: No such file or directory' on a .c file, the BL-01b"
echo "-include stddef.h workaround in firmware/livingroom.yaml is missing or"
echo "has been replaced with `-include cstddef` — verify with:"
echo "   grep -A1 platformio_options firmware/livingroom.yaml"
