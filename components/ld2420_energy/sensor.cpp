#include "sensor.h"
#include "esphome/core/log.h"
#include <algorithm>

namespace esphome {
namespace ld2420_energy {

static const char *const TAG = "ld2420_energy";

void LD2420EnergyListener::on_energy(uint16_t *sensor_energy, size_t size) {
  const size_t n = std::min(size, static_cast<size_t>(16));
  for (uint8_t i = 0; i < n; ++i) {
    if (this->gate_sensors_[i] != nullptr) {
      this->gate_sensors_[i]->publish_state(sensor_energy[i]);
    }
  }
}

void LD2420EnergyListener::dump_config() {
  ESP_LOGCONFIG(TAG, "LD2420 Energy Listener (16 gates via upstream LD2420Listener)");
  uint8_t registered = 0;
  for (uint8_t i = 0; i < 16; ++i) {
    if (this->gate_sensors_[i] != nullptr) ++registered;
  }
  ESP_LOGCONFIG(TAG, "  Registered gates: %u / 16", registered);
}

}  // namespace ld2420_energy
}  // namespace esphome