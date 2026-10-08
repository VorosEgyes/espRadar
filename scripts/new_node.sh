#!/usr/bin/env bash
# Clone radar.yaml into a new node config, generate a per-node
# api_encryption_key, and append the key to secrets.yaml.
#
# Usage: scripts/new_node.sh <name> <radar_type>
#   name:        device_name for the new node (lowercase ASCII, ^[a-z][a-z0-9_]{0,30}$)
#   radar_type:  REQUIRED. Either `ld2410` (Hi-Link LD2410 / LD2410B /
#                LD2410C) or `ld2420` (Hi-Link LD2420). There is no
#                default — the v1.2.0 dispatcher requires an explicit
#                type so the wrong-platform build is caught at script
#                time, not at first esphome run. (The v1.1.0
#                new_node.sh defaulted to ld2410; that default was
#                removed in v1.2.0 because an LD2420 node silently
#                receiving an LD2410 firmware is a hard-to-diagnose
#                failure mode: the UART is alive, the FW version
#                reads back, but no presence is ever reported.)
# Example: scripts/new_node.sh bedroom ld2410
# Example: scripts/new_node.sh kitchen ld2420
#
# All nodes use DHCP. Give each node a stable IP via router-side
# MAC reservation; do NOT bake static IPs into the firmware.
#
# The generated per-node encryption key is REQUIRED (BL-06):
# the seime/openhab-esphome binding identifies each node by the
# (device_name, encryption_key) pair. Sharing a single key
# across multiple nodes causes "handshake failure" / "CONNECTION_CLOSED"
# in the openHAB log.
#
# v1.2.0 (BL-07): the per-node YAML now also carries a
# `substitutions.radar_type:` field. The preflight
# (`scripts/preflight.py check_4_radar_yaml`) uses this to dispatch
# the schema check. The `radar_type` argument to this script is
# REQUIRED (see the safety note above).

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <name> <radar_type>" >&2
    echo "  radar_type: ld2410 or ld2420 (REQUIRED, no default)" >&2
    echo "Example: $0 bedroom ld2410" >&2
    echo "Example: $0 kitchen ld2420" >&2
    echo "" >&2
    echo "The v1.1.0 default of ld2410 was removed in v1.2.0 because" >&2
    echo "an LD2420 node silently receiving an LD2410 firmware is a" >&2
    echo "hard-to-diagnose failure mode. Pass the radar type" >&2
    echo "explicitly so the dispatcher picks the right schema." >&2
    exit 64
fi

NAME="$1"
RADAR_TYPE="$2"

# Reject names that would collide with reserved substitution keys
# (the YAML uses 'device_name', 'friendly_name', 'radar_type',
# 'ld2410_baud', 'ld2420_baud', etc.).
case "${NAME}" in
    device_name|friendly_name|radar_type|log_baud|ld2410_baud|ld2420_baud|ld2420_energy|ld2410|ld2420)
        echo "ERROR: '${NAME}' is a reserved substitution key name." >&2
        exit 65
        ;;
esac

# Reject an unknown radar_type. The dispatcher supports exactly two
# types; new types need a new radar_ld<type>.yaml include and a new
# preflight check_4 branch, so adding one without code changes would
# silently produce a build that compiles but never reports.
case "${RADAR_TYPE}" in
    ld2410) ;;
    ld2420) ;;
    *)
        echo "ERROR: radar_type='${RADAR_TYPE}' is not supported. Use 'ld2410' or 'ld2420'." >&2
        exit 65
        ;;
esac

# Disallow characters that would break the YAML substitution syntax
# (the generated `api_encryption_key_<név>` must be a valid !secret key).
if [[ ! "${NAME}" =~ ^[a-z][a-z0-9_]{0,30}$ ]]; then
    echo "ERROR: node name must match ^[a-z][a-z0-9_]{0,30}$ (lowercase ASCII, optional digits and underscores, starting with a letter)." >&2
    echo "       Got: '${NAME}'" >&2
    exit 65
fi

SECRETS="firmware/secrets.yaml"
SRC="firmware/radar.yaml"
DST="firmware/${NAME}.yaml"
SECRET_KEY="api_encryption_key_${NAME}"

if [[ ! -f "${SECRETS}" ]]; then
    echo "ERROR: ${SECRETS} not found — copy secrets.yaml.example to secrets.yaml first." >&2
    exit 66
fi
if [[ ! -f "${SRC}" ]]; then
    echo "ERROR: ${SRC} not found — run this from the repo root." >&2
    exit 66
fi
if [[ -f "${DST}" ]]; then
    # The destination firmware YAML already exists. Decide whether
    # to refuse (and exit 73) based on whether the file is tracked
    # in git:
    #   - Tracked (in git history): refuse. The file was committed
    #     intentionally, and overwriting it would silently lose the
    #     commit. The user should `git checkout` to revert or
    #     delete the file explicitly with `git rm`.
    #   - Untracked: overwrite. The file is a leftover from a
    #     previous test run or a manual `cp` that the user did
    #     not commit. The new_node.sh script's purpose is exactly
    #     to generate this file from a known-good template (radar.yaml),
    #     so overwriting an untracked copy is the desired behavior.
    if git ls-files --error-unmatch "${DST}" >/dev/null 2>&1; then
        echo "ERROR: ${DST} is tracked in git (committed). To regenerate, run" >&2
        echo "       'git rm ${DST} && ${0} ${NAME}' (or move it aside and" >&2
        echo "       re-run). The script will not overwrite a committed file." >&2
        exit 73
    else
        echo "NOTE: ${DST} exists but is untracked — overwriting with the"
        echo "      new node config from ${SRC}."
    fi
fi

# Generate a fresh 32-byte random key and base64-encode it.
# 32 bytes → 44-char base64 string (with the trailing '=').
NEW_KEY_VAL="$(python3 -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())')"

# Update secrets.yaml: replace the line if it already exists (re-run case),
# otherwise append a new commented block.
if grep -qE "^${SECRET_KEY}:" "${SECRETS}"; then
    # The BSD/GNU sed -i difference: use -i.bak and rm for cross-platform
    # safety (macOS BSD sed needs a backup suffix argument; GNU sed doesn't).
    sed -i.bak "s|^${SECRET_KEY}:.*|${SECRET_KEY}: \"${NEW_KEY_VAL}\"|" "${SECRETS}"
    rm -f "${SECRETS}.bak"
    echo "Replaced existing ${SECRET_KEY} in ${SECRETS}."
else
    {
        echo ""
        echo "# Per-node API encryption key for the '${NAME}' node (added by new_node.sh on $(date -I))"
        echo "${SECRET_KEY}: \"${NEW_KEY_VAL}\""
    } >> "${SECRETS}"
    echo "Appended ${SECRET_KEY} to ${SECRETS}."
fi

TITLE_NAME="$(tr '[:lower:]' '[:upper:]' <<< "${NAME:0:1}")${NAME:1}"

# v1.2.0 (BL-07): the per-node YAML is in `packages:` form, with
# the `radar:` value pointing to the radar-specific include file.
# The dispatcher picks the include target based on `radar_type`.
# Both substitutions and the packages: block are edited.
sed \
    -e "s|^  device_name: radar$|  device_name: ${NAME}|" \
    -e "s|^  friendly_name: Radar presence$|  friendly_name: ${TITLE_NAME} presence|" \
    -e "s|^    key: !secret api_encryption_key.*$|    key: !secret ${SECRET_KEY}|" \
    -e "s|^  radar_type: ld2410$|  radar_type: ${RADAR_TYPE}|" \
    -e "s|^  radar: !include radar_ld2410.yaml$|  radar: !include radar_${RADAR_TYPE}.yaml|" \
    "${SRC}" > "${DST}"

echo ""
echo "Created ${DST}."
echo "  device_name: ${NAME}"
echo "  friendly_name: ${TITLE_NAME} presence"
echo "  radar_type:   ${RADAR_TYPE}"
echo "  api_encryption_key: ${SECRET_KEY} (in ${SECRETS})"
echo ""
echo "To flash this node, run esphome from the REPO ROOT (not from"
echo "firmware/) — the LD2420 build's external_components path is"
echo "relative to the repo root, and the firmware/ subdirectory does"
echo "not contain a components/ folder:"
echo "  esphome run firmware/${NAME}.yaml"
echo ""
echo "In openHAB, add a new Thing for this node via the Inbox"
echo "(${TITLE_NAME} presence will auto-discover) and paste the"
echo "following into the Thing's encryptionKey field:"
echo "  ${NEW_KEY_VAL}"
