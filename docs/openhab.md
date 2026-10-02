# openHAB integration

Detailed companion to the main `README.md`. Targets openHAB 5.1.x with the
**seime/openhab-esphome** binding.

## Why the ESPHome Native API and not MQTT

- The openHAB ESPHome binding is **mDNS-aware** and **auto-discovers** the device.
- 2-way keep-alive: openHAB knows within a few seconds if the D1 mini is offline.
- **No MQTT broker** to maintain — Mosquitto is overkill for 4 radar nodes.
- The binding preserves entity icons, units, and device classes defined in the ESPHome YAML.

## Binding install

### Step 1 — Install the openhab-esphome JAR

```text
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

The ESPHome binding pulls in `org.openhab.binding.bluetooth` even if you do not use it. Install it once via the UI (**Settings → Add-ons → Bindings → Bluetooth**). After it starts, restart the ESPHome binding from the Karaf console (`bundle:restart <id>`).

### Step 3 — Verify mDNS

From the openHAB host:

```text
$ avahi-browse -t -r _esphome._tcp
+ wlan0 IPv4 livingroom                                          _esphome._tcp   local
```

If you do not see the device, the most common cause is the Wi-Fi `static_ip` config in the YAML — mDNS announcements sometimes lag a static-IP change. Power-cycle the D1 mini.

## Thing file (manual, optional)

If you would rather configure without mDNS discovery, drop this into `things/presence.things`:

```
Thing esphome:thing:livingroom "Livingroom presence" @ "Living room" [
    deviceName="livingroom",
    hostName="livingroom.local",
    port=6053,
    encryptionKey="PASTE_BASE64_32BYTE_HERE="
]
```

Then `Items` (matching the channels):

```
Number Presence_MovingDistance   "Moving distance [%.1f cm]"  {channel="esphome:thing:livingroom:moving_distance"}
Contact Presence_HasTarget        "Room occupied [%s]"        {channel="esphome:thing:livingroom:has_target"}
String  Presence_FwVersion        "Firmware [%s]"              {channel="esphome:thing:livingroom:fw_version"}
```

## Rules — turn off the AC when the room is empty

```
rule "AC off when room empty"
when
    Item Presence_HasTarget changed from OPEN to CLOSED
then
    if (LivingRoomAC_Power.state == ON) {
        LivingRoomAC_Power.sendCommand(OFF)
        logInfo("presence", "AC auto-off: no presence for 35 s")
    }
end
```

## Common gotchas

1. **APIClient disconnected immediately** — wrong `encryption_key` in the Thing config. Regenerate with `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`.
2. **`has_target` flickers every 30 s** — `presence_timeout` too low. Raise to 60s for still-presence reliability.
3. **`fw_version` stays `unknown`** — the LD2420 is on firmware < v1.5.3. The baud rate auto-detection assumes `115200`. Set `baud_rate: 256000` in the YAML if needed.
4. **`moving_distance` jumps to 0** every ~0.5 s — wrong pin pairing: swap `tx_pin` and `rx_pin` in the YAML.