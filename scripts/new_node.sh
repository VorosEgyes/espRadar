#!/usr/bin/env bash
# Clone radar.yaml into a new node config, generate a per-node
# api_encryption_key, and append the key to secrets.yaml.
#
# Usage: scripts/new_node.sh <name>
# Example: scripts/new_node.sh bedroom
#
# All nodes use DHCP. Give each node a stable IP via router-side
# MAC reservation; do NOT bake static IPs into the firmware.
#
# The generated per-node encryption key is REQUIRED (BL-06):
# the seime/openhab-esphome binding identifies each node by the
# (device_name, encryption_key) pair. Sharing a single key
# across multiple nodes causes "handshake failure" / "CONNECTION_CLOSED"
# in the openHAB log.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <name>" >&2
    echo "Example: $0 bedroom" >&2
    exit 64
fi

NAME="$1"

# Reject names that would collide with reserved substitution keys
# (the YAML uses 'device_name', 'friendly_name', 'ld2410_baud', etc.).
case "${NAME}" in
    device_name|friendly_name|log_baud|ld2410_baud|ld2420_baud|ld2420_energy|ld2410)
        echo "ERROR: '${NAME}' is a reserved substitution key name." >&2
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

sed \
    -e "s|^  device_name: radar\b|  device_name: ${NAME}|" \
    -e "s|^  friendly_name: Radar presence\b|  friendly_name: ${TITLE_NAME} presence|" \
    -e "s|^      name: Radar presence\b|      name: ${TITLE_NAME} presence|" \
    -e "s|^    key: !secret api_encryption_key\b|    key: !secret ${SECRET_KEY}|" \
    "${SRC}" > "${DST}"

echo ""
echo "Created ${DST}."
echo "  device_name: ${NAME}"
echo "  friendly_name: ${TITLE_NAME} presence"
echo "  api_encryption_key: ${SECRET_KEY} (in ${SECRETS})"
echo ""
echo "Edit ${DST} to set a non-default Wi-Fi SSID / password"
echo "for this node if you want it on a different network, then:"
echo "  cd firmware && esphome run ${NAME}.yaml"
echo ""
echo "In openHAB, add a new Thing for this node via the Inbox"
echo "(${TITLE_NAME} presence will auto-discover) and paste the"
echo "following into the Thing's encryptionKey field:"
echo "  ${NEW_KEY_VAL}"
