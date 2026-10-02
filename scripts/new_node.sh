#!/usr/bin/env bash
# Clone radar.yaml into a new node config and substitute the device name
# and friendly name. Edit the resulting file before flashing.
#
# Usage: scripts/new_node.sh <name>
# Example: scripts/new_node.sh bedroom
#
# All nodes use DHCP. Give each node a stable IP via router-side MAC
# reservation; do NOT bake static IPs into the firmware.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <name>" >&2
    echo "Example: $0 bedroom" >&2
    exit 64
fi

NAME="$1"

SRC="firmware/radar.yaml"
DST="firmware/${NAME}.yaml"

if [[ ! -f "${SRC}" ]]; then
    echo "ERROR: ${SRC} not found — run this from the repo root." >&2
    exit 66
fi

if [[ -f "${DST}" ]]; then
    echo "ERROR: ${DST} already exists." >&2
    exit 73
fi

TITLE_NAME="$(tr '[:lower:]' '[:upper:]' <<< "${NAME:0:1}")${NAME:1}"

sed \
    -e "s|^  device_name: radar\b|  device_name: ${NAME}|" \
    -e "s|^  friendly_name: Radar presence\b|  friendly_name: ${TITLE_NAME} presence|" \
    -e "s|^      name: Radar presence\b|      name: ${TITLE_NAME} presence|" \
    "${SRC}" > "${DST}"

echo "Created ${DST}. Edit it, then:"
echo "  cd firmware && esphome run ${NAME}.yaml"