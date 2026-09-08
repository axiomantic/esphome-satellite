#include "voice_enhancer.h"
#include "esphome/core/log.h"
#include <cmath>
#include <algorithm>

namespace esphome {
namespace voice_enhancer {

static const char *const TAG = "voice_enhancer";

void VoiceEnhancerSpeaker::setup() {
  ESP_LOGCONFIG(TAG, "Setting up Voice Enhancer Speaker...");
  this->recompute_filters_(16000);
  if (this->output_speaker_ != nullptr) {
    this->output_speaker_->add_audio_output_callback([this](uint32_t frames, int64_t timestamp) {
      this->audio_output_callback_.call(frames, timestamp);
    });
  }
}

void VoiceEnhancerSpeaker::dump_config() {
  ESP_LOGCONFIG(TAG, "Voice Enhancer Speaker:");
  ESP_LOGCONFIG(TAG, "  Enabled: %s", YESNO(this->enabled_));
  ESP_LOGCONFIG(TAG, "  HPF (180Hz): %s", YESNO(this->hpf_enabled_));
  ESP_LOGCONFIG(TAG, "  Presence (+3.5dB @ 2.8kHz): %s", YESNO(this->presence_enabled_));
  ESP_LOGCONFIG(TAG, "  Compressor (-16dBFS / 3:1 / +5.5dB makeup): %s", YESNO(this->compressor_enabled_));
  ESP_LOGCONFIG(TAG, "  Limiter (-0.5dBFS soft-knee): %s", YESNO(this->limiter_enabled_));
}

void VoiceEnhancerSpeaker::reset_filter_states_() {
  this->hpf_state_[0].reset();
  this->hpf_state_[1].reset();
  this->presence_state_[0].reset();
  this->presence_state_[1].reset();
  this->envelope_ = 0.0f;
}

void VoiceEnhancerSpeaker::recompute_filters_(uint32_t sample_rate) {
  if (sample_rate == 0) sample_rate = 16000;
  if (sample_rate == this->current_sample_rate_) return;

  this->current_sample_rate_ = sample_rate;
  float fs = static_cast<float>(sample_rate);

  // 1. High-Pass Filter (180 Hz, 2nd-order Butterworth, Q = 0.7071)
  float w0_h = 2.0f * static_cast<float>(M_PI) * 180.0f / fs;
  float alpha_h = sinf(w0_h) / (2.0f * 0.70710678f);
  float a0_h = 1.0f + alpha_h;
  float cos_w0_h = cosf(w0_h);

  this->hpf_coeffs_.b0 = ((1.0f + cos_w0_h) * 0.5f) / a0_h;
  this->hpf_coeffs_.b1 = (-(1.0f + cos_w0_h)) / a0_h;
  this->hpf_coeffs_.b2 = ((1.0f + cos_w0_h) * 0.5f) / a0_h;
  this->hpf_coeffs_.a1 = (-2.0f * cos_w0_h) / a0_h;
  this->hpf_coeffs_.a2 = (1.0f - alpha_h) / a0_h;

  // 2. Speech Presence Peaking EQ (+3.5 dB @ 2.8 kHz, Q = 1.2)
  float fc_eq = std::min(2800.0f, fs * 0.45f);
  float A = powf(10.0f, 3.5f / 40.0f);
  float w0_p = 2.0f * static_cast<float>(M_PI) * fc_eq / fs;
  float alpha_p = sinf(w0_p) / (2.0f * 1.2f);
  float a0_p = 1.0f + alpha_p / A;
  float cos_w0_p = cosf(w0_p);

  this->presence_coeffs_.b0 = (1.0f + alpha_p * A) / a0_p;
  this->presence_coeffs_.b1 = (-2.0f * cos_w0_p) / a0_p;
  this->presence_coeffs_.b2 = (1.0f - alpha_p * A) / a0_p;
  this->presence_coeffs_.a1 = (-2.0f * cos_w0_p) / a0_p;
  this->presence_coeffs_.a2 = (1.0f - alpha_p / A) / a0_p;

  // 3. Compressor envelope time constants
  this->alpha_att_ = expf(-1.0f / (0.004f * fs));  // 4ms attack
  this->alpha_rel_ = expf(-1.0f / (0.060f * fs));  // 60ms release

  ESP_LOGI(TAG, "Recomputed filters for sample rate %u Hz", (unsigned int)sample_rate);
}

void VoiceEnhancerSpeaker::start() {
  if (this->output_speaker_ != nullptr) {
    this->output_speaker_->set_audio_stream_info(this->audio_stream_info_);
    this->output_speaker_->start();
  }
  this->state_ = speaker::STATE_RUNNING;
  this->reset_filter_states_();
  this->recompute_filters_(this->audio_stream_info_.get_sample_rate());
}

void VoiceEnhancerSpeaker::stop() {
  this->state_ = speaker::STATE_STOPPED;
  if (this->output_speaker_ != nullptr) {
    this->output_speaker_->stop();
  }
  this->reset_filter_states_();
}

void VoiceEnhancerSpeaker::finish() {
  this->state_ = speaker::STATE_STOPPED;
  if (this->output_speaker_ != nullptr) {
    this->output_speaker_->finish();
  }
}

size_t VoiceEnhancerSpeaker::play(const uint8_t *data, size_t length, TickType_t ticks_to_wait) {
  if (this->output_speaker_ == nullptr || data == nullptr || length == 0) {
    return 0;
  }

  if (this->state_ != speaker::STATE_RUNNING) {
    this->start();
  }

  // Pass through directly if disabled or not 16-bit PCM
  if (!this->enabled_ || this->audio_stream_info_.get_bits_per_sample() != 16) {
    return this->output_speaker_->play(data, length, ticks_to_wait);
  }

  uint8_t channels = this->audio_stream_info_.get_channels();
  if (channels != 1 && channels != 2) {
    return this->output_speaker_->play(data, length, ticks_to_wait);
  }

  size_t num_samples = length / sizeof(int16_t);
  if (num_samples == 0) return 0;

  if (this->process_buffer_.size() < length) {
    this->process_buffer_.resize(length);
  }

  const int16_t *src = reinterpret_cast<const int16_t *>(data);
  int16_t *dst = reinterpret_cast<int16_t *>(this->process_buffer_.data());

  this->process_samples_(src, dst, num_samples, channels);

  return this->output_speaker_->play(this->process_buffer_.data(), length, ticks_to_wait);
}

void VoiceEnhancerSpeaker::process_samples_(const int16_t *src, int16_t *dst, size_t num_samples, uint8_t channels) {
  if (channels == 1) {
    for (size_t i = 0; i < num_samples; ++i) {
      float sample = static_cast<float>(src[i]) / 32768.0f;

      // 1. High-Pass Filter (180 Hz)
      if (this->hpf_enabled_) {
        float y = this->hpf_coeffs_.b0 * sample + this->hpf_state_[0].s1;
        this->hpf_state_[0].s1 = this->hpf_coeffs_.b1 * sample - this->hpf_coeffs_.a1 * y + this->hpf_state_[0].s2;
        this->hpf_state_[0].s2 = this->hpf_coeffs_.b2 * sample - this->hpf_coeffs_.a2 * y;
        sample = y;
      }

      // 2. Presence Peaking EQ (+3.5 dB @ 2.8 kHz)
      if (this->presence_enabled_) {
        float y = this->presence_coeffs_.b0 * sample + this->presence_state_[0].s1;
        this->presence_state_[0].s1 = this->presence_coeffs_.b1 * sample - this->presence_coeffs_.a1 * y + this->presence_state_[0].s2;
        this->presence_state_[0].s2 = this->presence_coeffs_.b2 * sample - this->presence_coeffs_.a2 * y;
        sample = y;
      }

      // 3. Dynamic Range Compressor
      if (this->compressor_enabled_) {
        float mag = fabsf(sample);
        if (mag > this->envelope_) {
          this->envelope_ = this->alpha_att_ * this->envelope_ + (1.0f - this->alpha_att_) * mag;
        } else {
          this->envelope_ = this->alpha_rel_ * this->envelope_ + (1.0f - this->alpha_rel_) * mag;
        }

        float gain = this->makeup_gain_;
        if (this->envelope_ > this->threshold_) {
          float ratio = this->threshold_ / this->envelope_;
          gain *= powf(ratio, 0.666667f);
        }
        sample *= gain;
      }

      // 4. Soft-Knee Peak Limiter (-0.5 dBFS)
      if (this->limiter_enabled_) {
        float abs_val = fabsf(sample);
        if (abs_val > 0.89125f) {
          float excess = abs_val - 0.89125f;
          float compressed_excess = 0.08875f * tanhf(excess / 0.08875f);
          sample = (sample > 0.0f) ? (0.89125f + compressed_excess) : -(0.89125f + compressed_excess);
        }
        if (sample > 0.98f) sample = 0.98f;
        else if (sample < -0.98f) sample = -0.98f;
      }

      dst[i] = static_cast<int16_t>(clamp<float>(sample * 32767.0f, -32767.0f, 32767.0f));
    }
  } else if (channels == 2) {
    size_t num_frames = num_samples / 2;
    for (size_t f = 0; f < num_frames; ++f) {
      float left = static_cast<float>(src[f * 2]) / 32768.0f;
      float right = static_cast<float>(src[f * 2 + 1]) / 32768.0f;

      if (this->hpf_enabled_) {
        float y_l = this->hpf_coeffs_.b0 * left + this->hpf_state_[0].s1;
        this->hpf_state_[0].s1 = this->hpf_coeffs_.b1 * left - this->hpf_coeffs_.a1 * y_l + this->hpf_state_[0].s2;
        this->hpf_state_[0].s2 = this->hpf_coeffs_.b2 * left - this->hpf_coeffs_.a2 * y_l;
        left = y_l;

        float y_r = this->hpf_coeffs_.b0 * right + this->hpf_state_[1].s1;
        this->hpf_state_[1].s1 = this->hpf_coeffs_.b1 * right - this->hpf_coeffs_.a1 * y_r + this->hpf_state_[1].s2;
        this->hpf_state_[1].s2 = this->hpf_coeffs_.b2 * right - this->hpf_coeffs_.a2 * y_r;
        right = y_r;
      }

      if (this->presence_enabled_) {
        float y_l = this->presence_coeffs_.b0 * left + this->presence_state_[0].s1;
        this->presence_state_[0].s1 = this->presence_coeffs_.b1 * left - this->presence_coeffs_.a1 * y_l + this->presence_state_[0].s2;
        this->presence_state_[0].s2 = this->presence_coeffs_.b2 * left - this->presence_coeffs_.a2 * y_l;
        left = y_l;

        float y_r = this->presence_coeffs_.b0 * right + this->presence_state_[1].s1;
        this->presence_state_[1].s1 = this->presence_coeffs_.b1 * right - this->presence_coeffs_.a1 * y_r + this->presence_state_[1].s2;
        this->presence_state_[1].s2 = this->presence_coeffs_.b2 * right - this->presence_coeffs_.a2 * y_r;
        right = y_r;
      }

      if (this->compressor_enabled_) {
        float max_mag = std::max(fabsf(left), fabsf(right));
        if (max_mag > this->envelope_) {
          this->envelope_ = this->alpha_att_ * this->envelope_ + (1.0f - this->alpha_att_) * max_mag;
        } else {
          this->envelope_ = this->alpha_rel_ * this->envelope_ + (1.0f - this->alpha_rel_) * max_mag;
        }

        float gain = this->makeup_gain_;
        if (this->envelope_ > this->threshold_) {
          float ratio = this->threshold_ / this->envelope_;
          gain *= powf(ratio, 0.666667f);
        }
        left *= gain;
        right *= gain;
      }

      if (this->limiter_enabled_) {
        for (float *s : {&left, &right}) {
          float abs_val = fabsf(*s);
          if (abs_val > 0.89125f) {
            float excess = abs_val - 0.89125f;
            float compressed_excess = 0.08875f * tanhf(excess / 0.08875f);
            *s = (*s > 0.0f) ? (0.89125f + compressed_excess) : -(0.89125f + compressed_excess);
          }
          if (*s > 0.98f) *s = 0.98f;
          else if (*s < -0.98f) *s = -0.98f;
        }
      }

      dst[f * 2] = static_cast<int16_t>(clamp<float>(left * 32767.0f, -32767.0f, 32767.0f));
      dst[f * 2 + 1] = static_cast<int16_t>(clamp<float>(right * 32767.0f, -32767.0f, 32767.0f));
    }
  }
}

}  // namespace voice_enhancer
}  // namespace esphome
