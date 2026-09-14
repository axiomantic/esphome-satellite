#include "aic3104.h"

#include "esphome/core/defines.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

namespace esphome {
namespace aic3104 {

static const char *const TAG = "aic3104";

#define ERROR_CHECK(err, msg) \
  if (!(err)) { \
    ESP_LOGE(TAG, msg); \
    this->mark_failed(); \
    return; \
  }

extern "C" size_t nim_aic3104_get_init_registers(uint8_t *outRegs, uint8_t *outVals);
extern "C" void nim_aic3104_compute_volume(float vol, bool muted, uint8_t *outDacVal, uint8_t *outHpLevel, uint8_t *outLopLevel);

void AIC3104::setup() {
  ESP_LOGI(TAG, "Setting up TLV320AIC3104 audio DAC...");
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
    if (!this->write_byte(regs[i], vals[i])) {
      ESP_LOGW(TAG, "Failed writing AIC3104 register 0x%02X=0x%02X", regs[i], vals[i]);
    }
  }
}

void AIC3104::dump_config() {
  ESP_LOGCONFIG(TAG, "AIC3104:");
  LOG_I2C_DEVICE(this);

  if (this->is_failed()) {
    ESP_LOGE(TAG, ESP_LOG_MSG_COMM_FAIL);
  }
}

bool AIC3104::set_mute_off() {
  this->is_muted_ = false;
  return this->write_mute_();
}

bool AIC3104::set_mute_on() {
  this->is_muted_ = true;
  return this->write_mute_();
}

bool AIC3104::set_volume(float volume) {
  this->volume_ = clamp<float>(volume, 0.0, 1.0);
  ESP_LOGD(TAG, "AIC3104 set_volume called: %.2f", this->volume_);
  bool result = this->write_volume_();
  ESP_LOGD(TAG, "AIC3104 write_volume result: %s", result ? "SUCCESS" : "FAILED");
  return result;
}

bool AIC3104::is_muted() { return this->is_muted_; }

float AIC3104::volume() { return this->volume_; }

bool AIC3104::write_mute_() {
  return this->write_volume_();
}

bool AIC3104::write_volume_() {
  ESP_LOGD(TAG, "write_volume_() called - volume: %.2f (muted: %d)", this->volume_, (int)this->is_muted_);

  if (!this->write_byte(AIC3104_PAGE_CTRL, 0x00)) {
    ESP_LOGE(TAG, "Failed to set page 0");
    return false;
  }

  uint8_t dac_val = 0;
  uint8_t hp_level = 0x0D;
  uint8_t lop_level = 0x0B;

  if (nim_aic3104_compute_volume != nullptr) {
    nim_aic3104_compute_volume(this->volume_, this->is_muted_, &dac_val, &hp_level, &lop_level);
  } else {
    dac_val = this->is_muted_ ? 0x80 : (uint8_t)clamp<float>((1.0f - this->volume_) * 0x80, 0.0f, 128.0f);
    hp_level = this->is_muted_ ? 0x08 : 0x0D;
    lop_level = this->is_muted_ ? 0x08 : 0x0B;
  }

  ESP_LOGD(TAG, "Writing AIC3104 volume registers: DAC=0x%02X, HP=0x%02X, LOP=0x%02X", dac_val, hp_level, lop_level);

  bool ok = this->write_byte(AIC3104_LEFT_DAC_VOLUME, dac_val) &&
            this->write_byte(AIC3104_RIGHT_DAC_VOLUME, dac_val) &&
            this->write_byte(AIC3104_HPLOUT_LEVEL, hp_level) &&
            this->write_byte(AIC3104_HPROUT_LEVEL, hp_level) &&
            this->write_byte(AIC3104_LEFT_LOP_LEVEL, lop_level) &&
            this->write_byte(AIC3104_RIGHT_LOP_LEVEL, lop_level);

  if (!ok) {
    ESP_LOGE(TAG, "Writing AIC3104 volume registers failed");
    return false;
  }

  return true;
}

}  // namespace aic3104
}  // namespace esphome
