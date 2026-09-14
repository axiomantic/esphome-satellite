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

extern "C" size_t nim_xvf3800_get_reboot_payload(uint8_t *outBuf);
extern "C" size_t nim_aic3104_get_init_registers(uint8_t *outRegs, uint8_t *outVals);
extern "C" void nim_aic3104_compute_volume(float vol, bool muted, uint8_t *outDacVal, uint8_t *outHpLevel, uint8_t *outLopLevel);
extern "C" uint8_t nim_aic3104_compute_hp_gain(float volume);
extern "C" size_t nim_xmos_make_level_payload(uint8_t cmd, uint8_t level, uint8_t *outBuf);

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

    // 4. Initialize AIC3104 Codec (DAC Power, Datapath, Headphone & Lineout outputs)
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

    ESP_LOGI(TAG, "Configuring TLV320AIC3104 DAC registers (power, datapath, HPLOUT/HPROUT, LEFT_LOP/RIGHT_LOP)...");
    uint8_t regs[32];
    uint8_t vals[32];
    size_t count = 0;
    if (nim_aic3104_get_init_registers != nullptr) {
      count = nim_aic3104_get_init_registers(regs, vals);
    } else {
      static const uint8_t fallback_regs[] = {0x00, 0x07, 0x25, 0x29, 0x2B, 0x2C, 0x2F, 0x33, 0x40, 0x41, 0x52, 0x56, 0x59, 0x5D};
      static const uint8_t fallback_vals[] = {0x00, 0x0A, 0xC0, 0x00, 0x00, 0x00, 0x80, 0x0D, 0x80, 0x0D, 0x80, 0x0B, 0x80, 0x0B};
      count = sizeof(fallback_regs);
      memcpy(regs, fallback_regs, count);
      memcpy(vals, fallback_vals, count);
    }

    for (size_t i = 0; i < count; i++) {
      uint8_t cmd[2] = {regs[i], vals[i]};
      i2c::ErrorCode err = this->bus_->write(AIC3104_I2C_ADDR, cmd, 2);
      if (err != i2c::ERROR_OK) {
        ESP_LOGW(TAG, "Failed writing AIC3104 reg 0x%02X=0x%02X (err=%d)", regs[i], vals[i], (int)err);
      }
    }

    // Also configure XMOS AIC3104 output levels (ResID 48, Cmd 11 & 12 = 9)
    uint8_t hp_payload[4];
    uint8_t line_payload[4];
    if (nim_xmos_make_level_payload != nullptr) {
      nim_xmos_make_level_payload(11, 9, hp_payload);
      nim_xmos_make_level_payload(12, 9, line_payload);
    } else {
      hp_payload[0] = 48; hp_payload[1] = 11; hp_payload[2] = 1; hp_payload[3] = 9;
      line_payload[0] = 48; line_payload[1] = 12; line_payload[2] = 1; line_payload[3] = 9;
    }
    this->bus_->write(XVF3800_I2C_ADDR, hp_payload, sizeof(hp_payload));
    this->bus_->write(XVF3800_I2C_ADDR, line_payload, sizeof(line_payload));

    ESP_LOGI(TAG, "TLV320AIC3104 DAC initialized successfully (3.5mm lineout/headphone unmuted)");
  }

  void reboot_xmos() {
    if (!this->bus_) return;
    uint8_t reboot_req[4] = {240, 89, 1, 0};
    if (nim_xvf3800_get_reboot_payload != nullptr) {
      nim_xvf3800_get_reboot_payload(reboot_req);
    }
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
