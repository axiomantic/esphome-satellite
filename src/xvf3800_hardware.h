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
    uint8_t payload[5] = {
      GPO_SERVICER_RESID,
      GPO_CMD_WRITE_VALUE,
      2,
      pin,
      val
    };
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

    if (state_name == "Muted") {
      // Solid red ring for privacy mute
      uint32_t red = ((uint8_t)(255 * brightness) << 16);
      for (int i = 0; i < 12; i++) colors[i] = red;
    } else if (state_name == "Woken" || state_name == "Listening") {
      // Listening: Bright pulsing cyan/blue
      float pulse = 0.6f + 0.4f * sinf(now * 0.008f);
      uint8_t r = 0;
      uint8_t g = (uint8_t)(200 * pulse * brightness);
      uint8_t b = (uint8_t)(255 * pulse * brightness);
      uint32_t cyan = (r << 16) | (g << 8) | b;
      for (int i = 0; i < 12; i++) colors[i] = cyan;
    } else if (state_name == "Thinking") {
      // Thinking: Rotating spinner (2-3 lit LEDs circling the ring)
      int head = (now / 70) % 12;
      for (int i = 0; i < 12; i++) {
        int dist = (head - i + 12) % 12;
        float factor = 0.0f;
        if (dist == 0) factor = 1.0f;
        else if (dist == 1) factor = 0.6f;
        else if (dist == 2) factor = 0.25f;
        else if (dist == 3) factor = 0.08f;

        if (factor > 0.0f) {
          uint8_t r = (uint8_t)(100 * factor * brightness);
          uint8_t g = (uint8_t)(150 * factor * brightness);
          uint8_t b = (uint8_t)(255 * factor * brightness);
          colors[i] = (r << 16) | (g << 8) | b;
        }
      }
    } else if (state_name == "Replying") {
      // Replying: Gentle warm amber/green breathing
      float breath = 0.5f + 0.5f * sinf(now * 0.006f);
      uint8_t r = (uint8_t)(255 * breath * brightness);
      uint8_t g = (uint8_t)(180 * breath * brightness);
      uint8_t b = (uint8_t)(40 * breath * brightness);
      uint32_t amber = (r << 16) | (g << 8) | b;
      for (int i = 0; i < 12; i++) colors[i] = amber;
    } else if (state_name == "Pipeline Error" || state_name == "Connection Error") {
      // Error: Fast red flash
      bool on = (now / 250) % 2 == 0;
      uint32_t red = on ? ((uint8_t)(255 * brightness) << 16) : 0;
      for (int i = 0; i < 12; i++) colors[i] = red;
    } else {
      // Idle state: Honor user pattern preference
      if (pattern_pref == "Off" || pattern_pref == "Silent") {
        // Off
      } else if (pattern_pref == "Breathe") {
        float bth = 0.15f + 0.15f * sinf(now * 0.002f);
        uint8_t val = (uint8_t)(255 * bth * brightness);
        uint32_t soft_blue = ((val / 2) << 16) | (val << 8) | val;
        for (int i = 0; i < 12; i++) colors[i] = soft_blue;
      } else if (pattern_pref == "Rainbow") {
        float hue_offset = (now % 4000) / 4000.0f;
        for (int i = 0; i < 12; i++) {
          float h = fmodf(hue_offset + (i / 12.0f), 1.0f);
          float rf, gf, bf;
          int hi = (int)(h * 6.0f);
          float f = h * 6.0f - hi;
          float q = 1.0f - f;
          float val = 0.35f * brightness;
          switch (hi % 6) {
            case 0: rf = val; gf = val * f; bf = 0; break;
            case 1: rf = val * q; gf = val; bf = 0; break;
            case 2: rf = 0; gf = val; bf = val * f; break;
            case 3: rf = 0; gf = val * q; bf = val; break;
            case 4: rf = val * f; gf = 0; bf = val; break;
            case 5: default: rf = val; gf = 0; bf = val * q; break;
          }
          colors[i] = ((uint8_t)(rf * 255) << 16) | ((uint8_t)(gf * 255) << 8) | (uint8_t)(bf * 255);
        }
      } else if (pattern_pref == "Spinner") {
        int head = (now / 200) % 12;
        colors[head] = ((uint8_t)(40 * brightness) << 8) | (uint8_t)(100 * brightness);
      }
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
