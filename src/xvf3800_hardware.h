#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/components/i2c/i2c_bus.h"
#include <cmath>
#include <cstring>
#include <string>

namespace esphome {
namespace xvf3800 {

static const char *const TAG = "xvf3800_hw";
static const uint8_t XVF3800_I2C_ADDR = 0x2C;
static const uint8_t AIC3104_I2C_ADDR = 0x18;

// XMOS GPO Servicer constants
static const uint8_t GPO_SERVICER_RESID = 20;
static const uint8_t GPO_CMD_WRITE_VALUE = 1;
static const uint8_t GPO_CMD_LED_RING = 18;

// Board GPO Pins on XMOS
static const uint8_t PIN_MIC_MUTE = 30; // 1 = muted, 0 = unmuted
static const uint8_t PIN_AMP_ENABLE = 31; // 0 = enabled (active low), 1 = disabled
static const uint8_t PIN_LED_POWER = 33; // 1 = power on, 0 = power off

class XVF3800Hardware {
 public:
  static XVF3800Hardware &instance() {
    static XVF3800Hardware inst;
    return inst;
  }

  void init(i2c::I2CBus *bus) {
    this->bus_ = bus;
    if (!bus) return;

    ESP_LOGI(TAG, "Initializing ReSpeaker XVF3800 hardware (LED power, Amp enable, AIC3104 DAC)...");

    // 1. Enable LED Power (X0D33 = 1)
    write_gpo_pin(PIN_LED_POWER, 1);

    // 2. Enable Speaker Amplifier (X0D31 = 0, active low)
    write_gpo_pin(PIN_AMP_ENABLE, 0);

    // 3. Ensure Mic Mute LED/Line is unmuted on XMOS (X0D30 = 0)
    write_gpo_pin(PIN_MIC_MUTE, 0);

    // 4. Initialize AIC3104 Codec Volume to 0dB attenuation
    init_aic3104();

    // 5. Initial LED Test pattern (brief green flash on boot)
    uint32_t boot_colors[12];
    for (int i = 0; i < 12; i++) boot_colors[i] = 0x001F00; // soft green
    set_leds(boot_colors);
  }

  void write_gpo_pin(uint8_t pin, uint8_t val) {
    if (!this->bus_) return;
    uint8_t payload[5];
    if (nim_xvf3800_make_gpo_payload) {
      nim_xvf3800_make_gpo_payload(pin, val, payload);
    } else {
      payload[0] = GPO_SERVICER_RESID;
      payload[1] = GPO_CMD_WRITE_VALUE;
      payload[2] = 2;
      payload[3] = pin;
      payload[4] = val;
    }
    i2c::ErrorCode err = this->bus_->write(XVF3800_I2C_ADDR, payload, sizeof(payload));
    if (err != i2c::ERROR_OK) {
      ESP_LOGW(TAG, "Failed writing GPO pin %d val %d (err=%d)", pin, val, (int)err);
    } else {
      ESP_LOGD(TAG, "Wrote GPO pin %d = %d", pin, val);
    }
  }

  void init_aic3104() {
    if (!this->bus_) return;
    // Page 0
    uint8_t page_cmd[2] = {0x00, 0x00};
    this->bus_->write(AIC3104_I2C_ADDR, page_cmd, 2);

    // Left DAC volume = 0x00 (0dB attenuation)
    uint8_t l_vol[2] = {0x2B, 0x00};
    this->bus_->write(AIC3104_I2C_ADDR, l_vol, 2);

    // Right DAC volume = 0x00 (0dB attenuation)
    uint8_t r_vol[2] = {0x2C, 0x00};
    this->bus_->write(AIC3104_I2C_ADDR, r_vol, 2);
    ESP_LOGD(TAG, "AIC3104 DAC volume set to 0dB");
  }

  void reboot_xmos() {
    if (!this->bus_) return;
    const uint8_t reboot_req[] = {240, 89, 1, 0};
    this->bus_->write(XVF3800_I2C_ADDR, reboot_req, sizeof(reboot_req));
    ESP_LOGI(TAG, "Sent reboot command to XMOS SoC");
  }

  void set_leds(const uint32_t colors[12]) {
    if (!this->bus_) return;
    if (this->leds_valid_ && memcmp(this->last_colors_, colors, sizeof(this->last_colors_)) == 0) {
      return; // Skip bus write if frame is identical
    }
    memcpy(this->last_colors_, colors, sizeof(this->last_colors_));
    this->leds_valid_ = true;

    // Payload: [resid (20), cmd (18), len (48), 12 * (B, G, R, 0)]
    uint8_t payload[3 + 48];
    payload[0] = GPO_SERVICER_RESID;
    payload[1] = GPO_CMD_LED_RING;
    payload[2] = 48;

    for (int i = 0; i < 12; i++) {
      uint32_t c = colors[i];
      payload[3 + i * 4 + 0] = (uint8_t)(c & 0xFF);         // Blue
      payload[3 + i * 4 + 1] = (uint8_t)((c >> 8) & 0xFF);  // Green
      payload[3 + i * 4 + 2] = (uint8_t)((c >> 16) & 0xFF); // Red
      payload[3 + i * 4 + 3] = 0x00;
    }

    i2c::ErrorCode err = this->bus_->write(XVF3800_I2C_ADDR, payload, sizeof(payload));
    if (err != i2c::ERROR_OK) {
      ESP_LOGW(TAG, "Failed writing LED ring (err=%d)", (int)err);
    }
  }

  void clear_leds() {
    uint32_t off[12] = {0};
    set_leds(off);
  }

  void update_animation(const std::string &state_name, const std::string &pattern_pref, float brightness) {
    uint32_t colors[12] = {0};
    uint32_t now = millis();
    brightness = std::max(0.05f, std::min(1.0f, brightness));

    if (nim_xvf3800_update_animation != nullptr) {
      nim_xvf3800_update_animation(state_name.c_str(), pattern_pref.c_str(), brightness, now, colors);
    }
    set_leds(colors);
  }

 private:
  i2c::I2CBus *bus_{nullptr};
  uint32_t last_colors_[12]{};
  bool leds_valid_{false};
};

}  // namespace xvf3800
}  // namespace esphome
