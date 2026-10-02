# espRadar — D1 mini + HLK-LD2420 mmWave radar for openHAB

Hi-Link HLK-LD2420 24 GHz mmWave human-presence radar wired to a **Wemos D1 mini (ESP8266)** and exposed to **openHAB 5.x** via the ESPHome Native API. No MQTT broker required.

This is the home-automation companion to the `BirdNest` / `RaisedGarden` VorosEgyes project family — same firmware + device-class conventions, no separate cloud, fully local.

---

## Features

- **Presence detection** (moving + still targets, 16 configurable gates)
- **Moving distance** in centimetres
- **Per-gate energy sensors** (`gate_energy_0`…`gate_energy_15`) for fine tuning
- **Dynamic calibration** (Normal / Calibrate / Simple modes; firmware ≥ v1.5.4 required)
- **Calibration UI** in openHAB (select, number, button entities) — no manual UART poking
- **Firmware version** reporting
- **OTA updates** through ESPHome dashboard
- **USB powered** — no deep-sleep, always-on.
- **DHCP networking** — router-side MAC reservation gives every node a stable IP without baking per-node config into the binary.

---

## Hardware

| Part | Notes |
|---|---|
| Wemos D1 mini (ESP8266, 4 MB flash) | the MCU |
| Hi-Link HLK-LD2420 | 24 GHz FMCW mmWave radar, 16 gates × 0.70 m |
| USB 5 V / 1 A supply | powers the D1 mini, the LD2420 draws 3V3 from the on-board regulator |
| 4 jumper wires | TX / RX / VCC / GND |

**Wiring table** (D1 mini `D7`/`D8` is GPIO13/GPIO15 — kept off UART0 so the logger can use it):

```
LD2420  →  D1 mini
─────      ──────
TX       →  D7   (GPIO13)   ESP-side RX
RX       →  D8   (GPIO15)   ESP-side TX
VCC      →  3V3
GND      →  GND
```

The D1 mini `3V3` rail can source ≈ 400 mA. The LD2420 averages 50 mA, peak 100 mA — safe.

## Network setup

Every node uses **DHCP**. To give each node a stable IP, set a **MAC reservation on the DHCP server** (your router, or a Pi-hole, or whatever) — do not bake static IPs into the firmware. Re-flashing a node will then never collide with another node's IP, and every firmware file looks identical.

The D1 mini MAC is printed on the silkscreen under the USB connector. Bind each MAC to the IP you want the node to live on.

---

## Firmware

Built with **ESPHome 2025.11+** (the upstream `ld2420` component has been merged since 2023-11 and gets the maintenance fixes every release, e.g. 2025-11.0 `[ld2420] Eliminate substr() allocation in firmware version parsing`).

The YAML lives in `firmware/livingroom.yaml`. Copy `firmware/secrets.yaml.example` to `firmware/secrets.yaml` and fill in Wi-Fi + openHAB `api:` encryption key before flashing.

```bash
cd firmware
esphome run livingroom.yaml     # first flash via USB
esphome run livingroom.yaml      # later: OTA after Wi-Fi is up
```

The custom component `components/ld2420_energy/` adds the 16 gate-energy sensors. It hooks into the upstream `LD2420Component` through the `LD2420Listener::on_energy()` interface that the parent already calls on every parsed energy frame (Normal mode, firmware ≥ v1.5.4, ~10 Hz). **No upstream fork is required.**

---

## openHAB integration

Uses the third-party **[seime/openhab-esphome](https://github.com/seime/openhab-esphome)** binding (MIT, currently `[4.0.0.0;6.0.0.0)` — openHAB 5.1.3 ✓).

### 1. Install the binding

The binding has an **unmet dependency** on the `bluetooth` binding even if you do not use it; install both:

```text
openhab> feature:install openhab-transport-serial
openhab> bundle:install https://github.com/seime/openhab-esphome/releases/download/latest_oh4/no.seime.openhab.binding.esphome-4.1.0-SNAPSHOT.jar
```

(or drop the JAR into `$OPENHAB_ADDONS` and install the `bluetooth` add-on through the UI).

### 2. Discover the device

The binding discovers the ESPHome node over mDNS as `livingroom.local` (or whatever `name:` you set in the YAML). You will see it appear in **Settings → Things → Inbox** within a few seconds. Add it, paste the `api.encryption.key` from `firmware/secrets.yaml` into the Thing configuration.

The Thing auto-creates the following Channels:

| Type | Name |
|---|---|
| Switch | `restart_device` |
| Select | `operating_mode` (Normal / Calibrate / Simple) |
| Number | `presence_timeout`, `min_gate_distance`, `max_gate_distance`, `gate_select`, `still_threshold`, `move_threshold` |
| Sensor | `moving_distance`, `gate_energy_0` … `gate_energy_15` |
| Text Sensor | `fw_version` |
| Binary Sensor | `has_target` (presence) |
| Button | `apply_config`, `factory_reset`, `restart_module`, `revert_config` |

### 3. Items & Sitemap (minimal example)

```text
// items/presence.items
Number  Presence_MovingDistance   "Moving distance [%.1f cm]"  {channel="esphome:thing:livingroom:moving_distance"}
Number  Presence_Gate0Energy      "Gate 0 energy [%.0f]"       {channel="esphome:thing:livingroom:gate_energy_0"}
Contact Presence_HasTarget        "Room occupied [MAP(presence.map):%s]"  {channel="esphome:thing:livingroom:has_target"}
String  Presence_FwVersion        "Firmware [%s]"              {channel="esphome:thing:livingroom:fw_version"}
```

```text
// sitemaps/presence.sitemap
sitemap presence label="Living room presence" {
    Frame label="State" {
        Switch item=Presence_HasTarget label="Occupied"
        Text    item=Presence_MovingDistance
        Text    item=Presence_FwVersion
    }
    Frame label="Tuning" {
        Setpoint item=Presence_PresenceTimeout minValue=5 maxValue=600 step=5
        Setpoint item=Presence_MaxGateDistance minValue=1 maxValue=15 step=1
        Selection item=Presence_OperatingMode mappings=["Normal"="Normal","Calibrate"="Calibrate","Simple"="Simple"]
    }
}
```

---

## Calibration

1. Set `operating_mode` to **Calibrate** through the openHAB Thing or the ESPHome device page.
2. Leave the room empty for ≥ 30 s.
3. Press the **apply_config** button. The LD2420 computes per-gate noise-floor thresholds and writes them to flash. It returns to Normal mode automatically.

For best results with a 6 m room on wall mounting:
- `max_gate_distance: 9` (≈ 6.3 m physical)
- `min_gate_distance: 0`
- `presence_timeout: 30s` is a reasonable default; raise it for still-presence reliability.

---

## Project layout

```
.
├── firmware/
│   ├── livingroom.yaml           ESPHome configuration for the D1 mini + LD2420
│   └── secrets.yaml.example      Template — copy to secrets.yaml and fill in
├── components/ld2420_energy/     Local ESPHome component: 16 gate-energy sensors
│   ├── __init__.py
│   ├── sensor.py
│   └── sensor.h
├── docs/
│   ├── openhab.md                Detailed openHAB thing / item / rules examples
│   ├── hardware.md               Wiring diagram, photos, BOM
│   └── protocol.md               LD2420 UART frame reference (V2.x protocol)
├── scripts/
│   ├── new_node.sh               Clone livingroom.yaml for a 2nd / 3rd / 4th node
│   └── preflight.py              Smoke-check before `esphome run` (pinned versions, syntax)
├── .github/workflows/
│   └── lint.yaml                 yaml-lint on PR
├── LICENSE                       MIT
└── README.md                     (this file)
```

---

## License

MIT — see [LICENSE](./LICENSE).

ESPHome itself is GPL-3.0; the upstream `ld2420` component is GPL-3.0. This project's local component is MIT; consumers must accept the GPL-3.0 dependency if they use ESPHome.