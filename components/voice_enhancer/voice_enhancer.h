#pragma once

#include "esphome/core/component.h"
#include "esphome/core/helpers.h"
#include "esphome/components/speaker/speaker.h"
#include <vector>

namespace esphome {
namespace voice_enhancer {

struct BiquadState {
  float s1{0.0f};
  float s2{0.0f};
  void reset() { s1 = 0.0f; s2 = 0.0f; }
};

struct BiquadCoeffs {
  float b0{1.0f}, b1{0.0f}, b2{0.0f};
  float a1{0.0f}, a2{0.0f};
};

class VoiceEnhancerSpeaker : public Component, public speaker::Speaker {
 public:
  void set_output_speaker(speaker::Speaker *output_speaker) { this->output_speaker_ = output_speaker; }
  void set_enabled(bool enabled) { this->enabled_ = enabled; }
  bool is_enabled() const { return this->enabled_; }
  void set_hpf_enabled(bool hpf) { this->hpf_enabled_ = hpf; }
  void set_presence_enabled(bool presence) { this->presence_enabled_ = presence; }
  void set_compressor_enabled(bool comp) { this->compressor_enabled_ = comp; }
  void set_limiter_enabled(bool lim) { this->limiter_enabled_ = lim; }

  void setup() override;
  void dump_config() override;
  void loop() override {}

  size_t play(const uint8_t *data, size_t length, TickType_t ticks_to_wait) override;
  size_t play(const uint8_t *data, size_t length) override { return this->play(data, length, 0); }
  void start() override;
  void stop() override;
  void finish() override;

  void set_pause_state(bool pause_state) override {
    if (this->output_speaker_ != nullptr) this->output_speaker_->set_pause_state(pause_state);
  }
  bool get_pause_state() const override {
    return this->output_speaker_ != nullptr ? this->output_speaker_->get_pause_state() : false;
  }
  bool has_buffered_data() const override {
    return this->output_speaker_ != nullptr ? this->output_speaker_->has_buffered_data() : false;
  }
  void set_volume(float volume) override {
    this->volume_ = volume;
    if (this->output_speaker_ != nullptr) this->output_speaker_->set_volume(volume);
  }
  float get_volume() override {
    return this->output_speaker_ != nullptr ? this->output_speaker_->get_volume() : this->volume_;
  }
  void set_mute_state(bool mute_state) override {
    this->mute_state_ = mute_state;
    if (this->output_speaker_ != nullptr) this->output_speaker_->set_mute_state(mute_state);
  }
  bool get_mute_state() override {
    return this->output_speaker_ != nullptr ? this->output_speaker_->get_mute_state() : this->mute_state_;
  }

 protected:
  void reset_filter_states_();
  void recompute_filters_(uint32_t sample_rate);
  void process_samples_(const int16_t *src, int16_t *dst, size_t num_samples, uint8_t channels);

  speaker::Speaker *output_speaker_{nullptr};
  bool enabled_{true};
  bool hpf_enabled_{true};
  bool presence_enabled_{true};
  bool compressor_enabled_{true};
  bool limiter_enabled_{true};

  uint32_t current_sample_rate_{0};

  BiquadCoeffs hpf_coeffs_;
  BiquadCoeffs presence_coeffs_;
  BiquadState hpf_state_[2];
  BiquadState presence_state_[2];

  float envelope_{0.0f};
  float alpha_att_{0.0f};
  float alpha_rel_{0.0f};
  float threshold_{0.158489f};   // -16 dBFS
  float makeup_gain_{1.88365f};  // +5.5 dB

  std::vector<uint8_t> process_buffer_;
};

}  // namespace voice_enhancer
}  // namespace esphome
