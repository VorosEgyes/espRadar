"""LD2420 energy listener — implements the upstream `LD2420Listener` interface.

The parent LD2420 component calls `on_energy()` after every parsed energy
frame (Normal mode, firmware >= v1.5.4), about 10 Hz. We forward each of
the 16 gate-energy values to its own `sensor::Sensor` entity.

The listener pattern is upstream-owned, so no fork of the ld2420 component
is required.
"""
#pragma once

#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/ld2420/ld2420.h"

namespace esphome {
namespace ld2420_energy {

class LD2420EnergyListener : public Component,
                              public esphome::ld2420::LD2420Listener {
 public:
  void register_gate(uint8_t gate, sensor::Sensor *sens) {
    if (gate < 16) this->gate_sensors_[gate] = sens;
  }

  // LD2420Listener interface
  void on_energy(uint16_t *sensor_energy, size_t size) override;

  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  sensor::Sensor *gate_sensors_[16]{};
};

}  // namespace ld2420_energy
}  // namespace esphome