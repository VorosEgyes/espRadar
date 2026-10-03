# openHAB integration

Detailed companion to the main `README.md`. Targets openHAB 5.1.x
with the **[seime/openhab-esphome](https://github.com/seime/openhab-esphome)**
binding (MIT, `[4.0.0.0;6.0.0.0)` — openHAB 5.1.3 ✓).

The v1.1.0 LD2410 firmware exposes a different set of channels
than the v1.0.0 LD2420 firmware did (no per-gate energy, but
`has_target` / `has_moving_target` / `has_still_target` are
split, and there is a `LD2410 MAC` text_sensor + a
`Engineering mode` switch). The thing / item / sitemap below
matches the v1.1.0 channel set exactly.

## Why the ESPHome Native API and not MQTT

- The openHAB ESPHome binding is **mDNS-aware** and **auto-discovers** the device.
- 2-way keep-alive: openHAB knows within a few seconds if the D1 mini is offline.
- **No MQTT broker** to maintain — Mosquitto is overkill for 4 radar nodes.
- The binding preserves entity icons, units, and device classes defined in the ESPHome YAML.
- The binding is **active on the openHAB community forum** — the author (`@seime`) responds to issues within days.

## Binding install

### Step 1 — Install the openhab-esphome JAR

openHAB 5.1.3 (the latest stable as of 2026-10-02) ships the
ESPHome binding in the Marketplace, so the simplest install
path is via the UI:

> **Settings → Add-ons → Bindings → "ESPHome Native API" → Install.**

If your openHAB version does not list it (older 5.x or 4.x),
fall back to the manual JAR install via the Karaf console:

```text
openhab> feature:install openhab-transport-serial
openhab> bundle:install https://github.com/seime/openhab-esphome/releases/download/latest_oh4/no.seime.openhab.binding.esphome-4.1.0-SNAPSHOT.jar
```

Watch the log:

```text
tail -F /openhab/userdata/logs/openhab.log | grep -i esphome
```

You should see:

```text
[INFO ] [phome.internal.handler.ESPHomeHandler] - Initialised esphome binding.
```

### Step 2 — Install the bluetooth binding (required dependency!)

The ESPHome binding pulls in `org.openhab.binding.bluetooth` as
a hard dependency, even if you do not use Bluetooth on the
D1 mini. Install it once via the UI (**Settings → Add-ons →
Bindings → Bluetooth**). After it starts, restart the
ESPHome binding from the Karaf console:

```text
openhab> bundle:list | grep esphome
# returns something like:
#  235 │ Active │  80 │ 4.1.0.202507291945 │ no.seime.openhab.binding.esphome
openhab> bundle:restart 235
```

The "Could not resolve module" error in the openHAB startup
log is the symptom of skipping this step.

### Step 3 — Verify mDNS

From the openHAB host:

```text
$ avahi-browse -t -r _esphome._tcp
+ wlan0 IPv4 radar                                          _esphome._tcp   local
```

You should see `radar` (the v1.1.0 device name) instead of the
v1.0.0 `livingroom`. If you do not see the device, the most
common cause is the Wi-Fi `static_ip` config in the YAML —
mDNS announcements sometimes lag a static-IP change.
Power-cycle the D1 mini.

## Thing file (manual, optional)

If you would rather configure without mDNS discovery, drop
this into `things/radar.things`:

```
Thing esphome:thing:radar "Radar presence" @ "Living room" [
    deviceName="radar",
    hostName="radar.local",
    port=6053,
    encryptionKey="PASTE_BASE64_32BYTE_HERE="
]
```

The `encryptionKey` is the base64 string from
`firmware/secrets.yaml` (`api_encryption_key:`). Do NOT bake a
different key into a different node's `.things` file — every
node must use the same key as its `firmware/secrets.yaml`.

If the binding cannot connect, the most common cause is a
mismatched `encryptionKey` (regenerate with
`python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`
and update both `secrets.yaml` and the `.things` file).

## Items (v1.1.0 channel set)

The v1.1.0 LD2410 firmware exposes the following channels. The
exact channel names are auto-derived from the ESPHome `name:`
field, with whitespace replaced by underscores (e.g.
`LD2410 MAC` → `ld2410_mac`).

### Presence (binary sensors)

```
Contact  Radar_HasTarget       "Occupied [MAP(presence.map):%s]"     {channel="esphome:thing:radar:has_target"}
Contact  Radar_HasMovingTarget "Moving [MAP(motion.map):%s]"        {channel="esphome:thing:radar:has_moving_target"}
Contact  Radar_HasStillTarget  "Still [MAP(presence.map):%s]"      {channel="esphome:thing:radar:has_still_target"}
```

### Distances and energies (core sensors)

```
Number  Radar_MovingDistance    "Moving distance [%.0f cm]"        {channel="esphome:thing:radar:moving_distance"}
Number  Radar_StillDistance     "Still distance [%.0f cm]"         {channel="esphome:thing:radar:still_distance"}
Number  Radar_DetectionDistance "Detection distance [%.0f cm]"   {channel="esphome:thing:radar:detection_distance"}
Number  Radar_MovingEnergy      "Moving energy [%.0f %%]"          {channel="esphome:thing:radar:moving_energy"}
Number  Radar_StillEnergy       "Still energy [%.0f %%]"           {channel="esphome:thing:radar:still_energy"}
```

### Per-gate energies (engineering-mode sensors)

These are `unknown` unless `Radar_EngineeringMode` is ON. The
LD2410 auto-disables engineering mode after 5 minutes
(Hi-Link firmware spec) to save power — the items revert to
`UNDEF` until the switch is flipped back on.

```
Number  Radar_Gate0MoveEnergy   "Gate 0 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_0_move_energy"}
Number  Radar_Gate0StillEnergy  "Gate 0 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_0_still_energy"}
Number  Radar_Gate1MoveEnergy   "Gate 1 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_1_move_energy"}
Number  Radar_Gate1StillEnergy  "Gate 1 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_1_still_energy"}
Number  Radar_Gate2MoveEnergy   "Gate 2 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_2_move_energy"}
Number  Radar_Gate2StillEnergy  "Gate 2 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_2_still_energy"}
Number  Radar_Gate3MoveEnergy   "Gate 3 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_3_move_energy"}
Number  Radar_Gate3StillEnergy  "Gate 3 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_3_still_energy"}
Number  Radar_Gate4MoveEnergy   "Gate 4 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_4_move_energy"}
Number  Radar_Gate4StillEnergy  "Gate 4 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_4_still_energy"}
Number  Radar_Gate5MoveEnergy   "Gate 5 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_5_move_energy"}
Number  Radar_Gate5StillEnergy  "Gate 5 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_5_still_energy"}
Number  Radar_Gate6MoveEnergy   "Gate 6 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_6_move_energy"}
Number  Radar_Gate6StillEnergy  "Gate 6 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_6_still_energy"}
Number  Radar_Gate7MoveEnergy   "Gate 7 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_7_move_energy"}
Number  Radar_Gate7StillEnergy  "Gate 7 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_7_still_energy"}
Number  Radar_Gate8MoveEnergy   "Gate 8 move energy [%.0f %%]"    {channel="esphome:thing:radar:gate_8_move_energy"}
Number  Radar_Gate8StillEnergy  "Gate 8 still energy [%.0f %%]"   {channel="esphome:thing:radar:gate_8_still_energy"}
```

### Text sensors

```
String  Radar_FwVersion   "Firmware [%s]"          {channel="esphome:thing:radar:fw_version"}
String  Radar_LD2410MAC   "LD2410 MAC [%s]"        {channel="esphome:thing:radar:ld2410_mac"}
```

### Switches

```
Switch  Radar_EngineeringMode  "Engineering mode"  {channel="esphome:thing:radar:engineering_mode"}
Switch  Radar_Restart          "Restart"           {channel="esphome:thing:radar:restart"}
```

### Selects

```
Selection  Radar_DistanceResolution "Distance resolution"  {channel="esphome:thing:radar:distance_resolution"}
Selection  Radar_BaudRate           "UART baud rate"        {channel="esphome:thing:radar:baud_rate"}
Selection  Radar_LightFunction      "Light function"         {channel="esphome:thing:radar:light_function"}
Selection  Radar_OutPinLevel        "OUT pin level"          {channel="esphome:thing:radar:out_pin_level"}
```

### Numbers (tuning knobs)

```
Number  Radar_MaxMoveDistanceGate    "Max move distance gate"     {channel="esphome:thing:radar:max_move_distance_gate"}
Number  Radar_MaxStillDistanceGate   "Max still distance gate"    {channel="esphome:thing:radar:max_still_distance_gate"}
Number  Radar_NoneDuration           "None duration [%.0f s]"     {channel="esphome:thing:radar:none_duration"}
Number  Radar_LightThreshold         "Light threshold [%.0f]"     {channel="esphome:thing:radar:light_threshold"}
Number  Radar_Gate0MoveThreshold     "Gate 0 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_0_move_threshold"}
Number  Radar_Gate0StillThreshold    "Gate 0 still threshold [%.0f]" {channel="esphome:thing:radar:gate_0_still_threshold"}
Number  Radar_Gate1MoveThreshold     "Gate 1 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_1_move_threshold"}
Number  Radar_Gate1StillThreshold    "Gate 1 still threshold [%.0f]" {channel="esphome:thing:radar:gate_1_still_threshold"}
Number  Radar_Gate2MoveThreshold     "Gate 2 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_2_move_threshold"}
Number  Radar_Gate2StillThreshold    "Gate 2 still threshold [%.0f]" {channel="esphome:thing:radar:gate_2_still_threshold"}
Number  Radar_Gate3MoveThreshold     "Gate 3 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_3_move_threshold"}
Number  Radar_Gate3StillThreshold    "Gate 3 still threshold [%.0f]" {channel="esphome:thing:radar:gate_3_still_threshold"}
Number  Radar_Gate4MoveThreshold     "Gate 4 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_4_move_threshold"}
Number  Radar_Gate4StillThreshold    "Gate 4 still threshold [%.0f]" {channel="esphome:thing:radar:gate_4_still_threshold"}
Number  Radar_Gate5MoveThreshold     "Gate 5 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_5_move_threshold"}
Number  Radar_Gate5StillThreshold    "Gate 5 still threshold [%.0f]" {channel="esphome:thing:radar:gate_5_still_threshold"}
Number  Radar_Gate6MoveThreshold     "Gate 6 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_6_move_threshold"}
Number  Radar_Gate6StillThreshold    "Gate 6 still threshold [%.0f]" {channel="esphome:thing:radar:gate_6_still_threshold"}
Number  Radar_Gate7MoveThreshold     "Gate 7 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_7_move_threshold"}
Number  Radar_Gate7StillThreshold    "Gate 7 still threshold [%.0f]" {channel="esphome:thing:radar:gate_7_still_threshold"}
Number  Radar_Gate8MoveThreshold     "Gate 8 move threshold [%.0f]"  {channel="esphome:thing:radar:gate_8_move_threshold"}
Number  Radar_Gate8StillThreshold    "Gate 8 still threshold [%.0f]" {channel="esphome:thing:radar:gate_8_still_threshold"}
```

### Buttons

```
Button  Radar_RestartModule   "Restart module"   {channel="esphome:thing:radar:restart_module"}
Button  Radar_FactoryReset   "Factory reset"     {channel="esphome:thing:radar:factory_reset"}
Button  Radar_QueryParams    "Query params"      {channel="esphome:thing:radar:query_params"}
```

> NB: the ESPHome `name:` field in `firmware/radar.yaml` is
> the source of truth for the channel ID. Spaces become
> underscores, the prefix `Radar_` is derived from the
> `friendly_name: "Radar presence"` substitution. If you
> change the `friendly_name`, the channel prefix changes too
> and the `.items` file must be regenerated.

## Sitemap (minimal example)

```sitemap
sitemap radar label="Radar presence" {
    Frame label="State" {
        Switch item=Radar_HasTarget label="Occupied"
        Text    item=Radar_MovingDistance
        Text    item=Radar_StillDistance
        Text    item=Radar_DetectionDistance
        Text    item=Radar_MovingEnergy
        Text    item=Radar_StillEnergy
        Text    item=Radar_FwVersion
        Text    item=Radar_LD2410MAC
    }
    Frame label="Tuning" {
        Switch item=Radar_EngineeringMode
        Setpoint item=Radar_NoneDuration minValue=0 maxValue=32767 step=1
        Setpoint item=Radar_MaxMoveDistanceGate minValue=2 maxValue=8 step=1
        Setpoint item=Radar_MaxStillDistanceGate minValue=2 maxValue=8 step=1
        Selection item=Radar_DistanceResolution mappings=["0.75m"="0.75m","0.2m"="0.2m"]
    }
    Frame label="Admin" {
        Button  item=Radar_QueryParams
        Button  item=Radar_RestartModule
        Button  item=Radar_FactoryReset
    }
}
```

For a richer Home Assistant card template (with per-gate energy
bars that update when engineering mode is on), see the
**Calibration Process** section of the [LD2410 ESPHome docs](https://esphome.io/components/sensor/ld2410/#calibration-process).

## Rules — turn off the AC when the room is empty

The v1.1.0 firmware uses `Radar_HasTarget` as the primary
presence signal (the same as v1.0.0 did with `Presence_HasTarget`).
The `delayed_off: 5s` filter on the ESPHome side means the
binary sensor stays ON for 5 seconds after the radar goes
quiet, so a 1-second blip does not toggle the AC.

```
rule "AC off when room empty"
when
    Item Radar_HasTarget changed from OPEN to CLOSED
then
    if (LivingRoomAC_Power.state == ON) {
        LivingRoomAC_Power.sendCommand(OFF)
        logInfo("presence", "AC auto-off: no presence for 35 s")
    }
end
```

For finer-grained control (e.g. distinguish "moving" from
"still present" so the AC can stay on while someone is sitting
still at a desk), use the `Radar_HasMovingTarget` channel
in the rule's `when` clause:

```
rule "AC low when only still presence"
when
    Item Radar_HasMovingTarget changed
then
    if (Radar_HasMovingTarget.state == CLOSED && Radar_HasStillTarget.state == OPEN) {
        // Only still target — someone is sitting still
        LivingRoomAC_Power.sendCommand(LOW)
    } else if (Radar_HasMovingTarget.state == OPEN) {
        LivingRoomAC_Power.sendCommand(HIGH)
    }
end
```

## Common gotchas (v1.1.0)

1. **APIClient disconnected immediately** — wrong
   `encryption_key` in the Thing config. Regenerate with
   `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`,
   update `firmware/secrets.yaml`, reflash the D1 mini, and
   paste the new key into the Thing config.
2. **`Radar_HasTarget` flickers every 30 s** — `None duration`
   too low. The `delayed_off: 5s` filter handles blips, but
   if the room has periodic zero-detection events (HVAC
   drafts, fan noise), raise `None duration` to 30-60 s in the
   `Radar_NoneDuration` Setpoint, and lower the per-gate
   `move_threshold` in `Radar_Gate0MoveThreshold` to 20.
3. **`Radar_FwVersion` stays `unknown`** — the LD2410 UART
   is not communicating. Check `Radar_LD2410MAC` first: if
   THAT is also `unknown`, the wiring is bad (5V on VCC, not
   3V3 — see `RELEASE_CHECKLIST.md` BL-05). If the MAC is
   present but the firmware version is `unknown`, the LD2410
   is on a very old firmware; reflashing the LD2410 via the
   Hi-Link PC tool (Windows-only) brings it back.
4. **`Radar_MovingDistance` jumps to 0** every ~0.5 s — wrong
   pin pairing: swap `tx_pin: GPIO15` and `rx_pin: GPIO13` in
   the `uart:` block of `firmware/radar.yaml`. Also check
   that `Radar_LD2410MAC` is populated (otherwise the UART
   is not alive at all).
5. **All sensors `UNDEF` after a reflash** — the openHAB
   binding needs a Thing restart for the new entity set to
   propagate. In MainUI: **Settings → Things → espRadar-radar →
   Delete** (do not unlink — the channel IDs would survive),
   then rediscover via inbox. The v1.0.0 → v1.1.0 channel
   set is incompatible (different number of items, different
   channel names), so a fresh discovery is required after
   the firmware upgrade.
6. **The v1.0.0 firmware (LD2420) and v1.1.0 firmware (LD2410)
   are NOT compatible** with the same `.things` file. The
   channel set is different (`gate_energy_0` does not exist
   on the LD2410, and `has_moving_target` / `has_still_target`
   do not exist on the LD2420). To revert a node to v1.0.0,
   see `docs/RELEASE_NOTES_v1.1.0.md` → "How to revert a node
   to v1.0.0 (LD2420 hardware)".
