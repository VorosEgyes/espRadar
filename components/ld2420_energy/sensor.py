"""LD2420 energy sensor — exposes the 16 per-gate energy values as ESPHome sensors.

Uses the upstream `LD2420Listener::on_energy` callback (declared in
esphome/components/ld2420/ld2420.h). The parent `LD2420Component` calls
the listener every time it parses a 45-byte energy frame (Normal mode,
firmware >= v1.5.4) — about 10 Hz. No upstream fork required.
"""
from __future__ import annotations

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_SIGNAL_STRENGTH,  # 2025.11+; renamed from DEVICE_CLASS_SIGNAL
    STATE_CLASS_MEASUREMENT,
    UNIT_DECIBEL,
)
from esphome.components.ld2420 import LD2420Component

ld2420_energy_ns = cg.esphome_ns.namespace("ld2420_energy")
LD2420EnergyListener = ld2420_energy_ns.class_(
    "LD2420EnergyListener", cg.Component
)

CONF_LD2420_ID = "ld2420_id"
CONF_GATE_ENERGY_KEYS = [f"gate_energy_{i}" for i in range(16)]


def _validate(value):
    if not any(k in value for k in CONF_GATE_ENERGY_KEYS):
        raise cv.Invalid("Provide at least one gate_energy_N entry (N in 0..15)")
    return value


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(LD2420EnergyListener),
            cv.Required(CONF_LD2420_ID): cv.use_id(LD2420Component),
            **{
                cv.Optional(key): sensor.sensor_schema(
                    unit_of_measurement=UNIT_DECIBEL,
                    accuracy_decimals=0,
                    device_class=DEVICE_CLASS_SIGNAL_STRENGTH,
                    state_class=STATE_CLASS_MEASUREMENT,
                )
                for key in CONF_GATE_ENERGY_KEYS
            },
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _validate,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    hub = await cg.get_variable(config[CONF_LD2420_ID])
    # Upstream LD2420Component exposes `register_listener` (not `add_listener`)
    # since ld2420 was merged into ESPHome core in 2023-11. The method name
    # was stable through 2026.9.1. Verified against
    # esphome/esphome@2026.9.1 esphome/components/ld2420/ld2420.h:102
    # (`void register_listener(LD2420Listener *listener) { ... }`).
    cg.add(hub.register_listener(var))

    for i, key in enumerate(CONF_GATE_ENERGY_KEYS):
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(var.register_gate(i, sens))