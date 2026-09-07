#pragma once

#include "esphome/core/component.h"
#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/speaker/speaker.h"
#include "sound_data.h"
#include <string>
#include <algorithm>
#include <functional>

namespace esphome {

static const char *const PCM_PLAYER_TAG = "pcm_sound_player";

class PcmSoundPlayer : public Component {
 public:
  void set_speaker(speaker::Speaker *speaker) { this->speaker_ = speaker; }
  
  void play_sound(const std::string &name, bool loop = false, float volume = -1.0f) {
    if (this->speaker_ == nullptr) return;
    
    const satellite_audio::SoundEntry *entry = satellite_audio::find_sound(name);
    if (!entry) {
      ESP_LOGW(PCM_PLAYER_TAG, "Sound not found: '%s'", name.c_str());
      return;
    }
    
    this->play_adpcm(entry->data, entry->length, loop, volume, entry->name);
  }
  
  void play_adpcm(const uint8_t *data, size_t length, bool loop = false, float volume = -1.0f, const char* name = "sound") {
    if (this->speaker_ == nullptr || data == nullptr || length == 0) return;
    
    if (this->is_playing_) {
      this->speaker_->stop();
    }
    
    this->data_ = data;
    this->data_len_ = length;
    this->read_offset_ = 0;
    this->is_loop_ = loop;
    this->valprev_ = 0;
    this->index_ = 0;
    this->buffer_samples_ = 0;
    this->buffer_sent_bytes_ = 0;
    this->is_playing_ = true;
    
    audio::AudioStreamInfo info(16, 1, 16000);
    this->speaker_->set_audio_stream_info(info);
    if (volume >= 0.0f) {
      this->speaker_->set_volume(volume);
    }
    this->speaker_->start();
    ESP_LOGD(PCM_PLAYER_TAG, "Playing PCM recorded audio: %s (%zu bytes ADPCM, loop=%d)", name, length, (int)loop);
  }
  
  void set_on_finished(std::function<void()> callback) { this->on_finished_ = callback; }

  void stop() {
    if (!this->is_playing_) return;
    this->is_playing_ = false;
    this->is_loop_ = false;
    if (this->speaker_ != nullptr) {
      this->speaker_->stop();
    }
    ESP_LOGD(PCM_PLAYER_TAG, "PCM audio stopped");
    if (this->on_finished_) {
      this->on_finished_();
    }
  }
  
  bool is_playing() const { return this->is_playing_; }
  
  void loop() override {
    if (!this->is_playing_ || this->speaker_ == nullptr) return;
    
    // 1. Send remainder of decode_buffer_ if any
    size_t total_buffer_bytes = this->buffer_samples_ * sizeof(int16_t);
    if (this->buffer_sent_bytes_ < total_buffer_bytes) {
      const uint8_t *src = reinterpret_cast<const uint8_t*>(this->decode_buffer_) + this->buffer_sent_bytes_;
      size_t to_send = total_buffer_bytes - this->buffer_sent_bytes_;
      size_t sent = this->speaker_->play(src, to_send, 0);
      this->buffer_sent_bytes_ += sent;
      if (this->buffer_sent_bytes_ < total_buffer_bytes) {
        return; // ring buffer full, continue next loop
      }
    }
    
    // 2. Decode next chunk if available
    if (this->read_offset_ >= this->data_len_) {
      if (this->is_loop_) {
        this->read_offset_ = 0;
        this->valprev_ = 0;
        this->index_ = 0;
      } else {
        this->is_playing_ = false;
        this->speaker_->finish();
        ESP_LOGD(PCM_PLAYER_TAG, "PCM audio finished");
        if (this->on_finished_) {
          this->on_finished_();
        }
        return;
      }
    }
    
    size_t bytes_to_decode = std::min((size_t)256, this->data_len_ - this->read_offset_);
    this->buffer_samples_ = 0;
    this->buffer_sent_bytes_ = 0;
    
    for (size_t i = 0; i < bytes_to_decode; ++i) {
      uint8_t byte = this->data_[this->read_offset_++];
      uint8_t nibble_low = byte & 0x0F;
      uint8_t nibble_high = (byte >> 4) & 0x0F;
      
      this->decode_buffer_[this->buffer_samples_++] = this->decode_sample_(nibble_low);
      this->decode_buffer_[this->buffer_samples_++] = this->decode_sample_(nibble_high);
    }
    
    total_buffer_bytes = this->buffer_samples_ * sizeof(int16_t);
    const uint8_t *src = reinterpret_cast<const uint8_t*>(this->decode_buffer_);
    size_t sent = this->speaker_->play(src, total_buffer_bytes, 0);
    this->buffer_sent_bytes_ = sent;
  }
  
 protected:
  speaker::Speaker *speaker_{nullptr};
  const uint8_t *data_{nullptr};
  size_t data_len_{0};
  size_t read_offset_{0};
  bool is_playing_{false};
  bool is_loop_{false};
  std::function<void()> on_finished_{nullptr};
  
  int32_t valprev_{0};
  int8_t index_{0};
  
  int16_t decode_buffer_[512];
  size_t buffer_samples_{0};
  size_t buffer_sent_bytes_{0};
  
  inline int16_t decode_sample_(uint8_t nibble) {
    int32_t step = satellite_audio::STEP_SIZE_TABLE[this->index_];
    this->index_ += satellite_audio::INDEX_TABLE[nibble & 0x0F];
    if (this->index_ < 0) this->index_ = 0;
    else if (this->index_ > 88) this->index_ = 88;
    
    int32_t diff = step >> 3;
    if (nibble & 4) diff += step;
    if (nibble & 2) diff += step >> 1;
    if (nibble & 1) diff += step >> 2;
    
    if (nibble & 8) this->valprev_ -= diff;
    else this->valprev_ += diff;
    
    if (this->valprev_ > 32767) this->valprev_ = 32767;
    else if (this->valprev_ < -32768) this->valprev_ = -32768;
    
    return static_cast<int16_t>(this->valprev_);
  }
};

inline PcmSoundPlayer &get_pcm_sound_player() {
  static PcmSoundPlayer instance;
  return instance;
}

} // namespace esphome
