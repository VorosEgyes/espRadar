# LD2420 protocol reference

The HLK-LD2420 uses a proprietary framed UART protocol at 115200 baud (firmware >= v1.5.3) or 256000 baud (older). Frames are **little-endian**, with a fixed 4-byte header `AA AA AA AA` (config-mode only; **the operational mode header is different — see below**) and a 2-byte length + 2-byte footer.

This document is a digest of the upstream community resources. **Do not redistribute** the Hi-Link XLSX datasheet — request it from the vendor.

## Energy data frame (radar → host, 45 bytes, Normal mode)

```
Offset  Type    Meaning
------  ------  --------------------------------------------------
0       u32     frame header = 0xF1F1F2F2 (NOT 0xAAAAAAAA!)
4       u32     timestamp (ms since boot, lower 32 bits)
8       u8      target_state: 0=none, 1=moving, 2=still, 3=both
9       u8      moving_target_distance_cm (0 if no target)
10      u8      still_target_distance_cm
11      u8      reserved (0x00)
12..43  u16×16  gate 0..15 energy values, LE16, 0..65535
```

The ESPHome upstream component parses this frame in `LD2420Component::handle_energy_mode_()` (see `esphome/esphome/components/ld2420/ld2420.cpp`).

## Config mode frames (host → radar)

Command frames are sent **with the address byte 0xFA**, body of variable length, ending with 0xFBFBFCFC. Example for "set min gate to 0":

```
AC 00 00 01 00 00 00 02 00 01 00 02 00 00 FB FB FC FC
```

The upstream component handles all 35 parameter read/write commands.

## Per-gate energy → presence logic

Presence is reported when **either** of these holds:

1. `moving_target_energy[gate] > move_threshold[gate]` for any active gate (default range 0..max_gate)
2. `still_target_energy[gate] > still_threshold[gate]` for any active gate

Thresholds are configured per gate. ESPHome's `ld2420` component exposes them as `select`/`number` entities — same six names as in this README.

## Sources

- Hi-Link XLSX datasheet (request from vendor; mirror at <https://github.com/soubhik-khan/HLK-LD2420>)
- ESPHome upstream component: <https://github.com/esphome/esphome/tree/dev/esphome/components/ld2420>
- Community thread: <https://github.com/esphome/feature-requests/issues/2219>