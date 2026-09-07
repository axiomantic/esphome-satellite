#pragma once

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/speaker/speaker.h"
#include "sound_data.h"
#include <string>
#include <algorithm>
#include <functional>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace esphome {

static const char *const PCM_PLAYER_TAG = "pcm_sound_player";

class PcmSoundPlayer {
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
    
    this->stop_task_();
    
    this->data_ = data;
    this->data_len_ = length;
    this->read_offset_ = 0;
    this->is_loop_ = loop;
    this->valprev_ = 0;
    this->index_ = 0;
    this->is_playing_ = true;
    
    audio::AudioStreamInfo info(16, 1, 16000);
    this->speaker_->set_audio_stream_info(info);
    if (volume >= 0.0f) {
      this->speaker_->set_volume(volume);
    }
    this->speaker_->start();
    
    ESP_LOGD(PCM_PLAYER_TAG, "Playing PCM audio: %s (%zu bytes, loop=%d, vol=%.2f)", name, length, (int)loop, volume);
    
    BaseType_t ret = xTaskCreatePinnedToCore(
        playback_task_entry_,
        "pcm_playback",
        4096,
        this,
        5,
        &this->task_handle_,
        1
    );
    if (ret != pdPASS) {
      ESP_LOGE(PCM_PLAYER_TAG, "Failed to create playback task!");
      this->is_playing_ = false;
      this->speaker_->stop();
    }
  }
  
  void set_on_finished(std::function<void()> callback) { this->on_finished_ = callback; }

  void stop() {
    if (!this->is_playing_ && this->task_handle_ == nullptr) return;
    this->is_playing_ = false;
    this->is_loop_ = false;
    this->stop_task_();
    if (this->speaker_ != nullptr) {
      this->speaker_->stop();
    }
    ESP_LOGD(PCM_PLAYER_TAG, "PCM audio stopped");
    if (this->on_finished_) {
      this->on_finished_();
    }
  }
  
  bool is_playing() const { return this->is_playing_; }

 protected:
  speaker::Speaker *speaker_{nullptr};
  const uint8_t *data_{nullptr};
  size_t data_len_{0};
  size_t read_offset_{0};
  volatile bool is_playing_{false};
  bool is_loop_{false};
  std::function<void()> on_finished_{nullptr};
  TaskHandle_t task_handle_{nullptr};
  
  int32_t valprev_{0};
  int8_t index_{0};
  
  static void playback_task_entry_(void *arg) {
    PcmSoundPlayer *self = static_cast<PcmSoundPlayer *>(arg);
    self->run_playback_();
    self->task_handle_ = nullptr;
    vTaskDelete(NULL);
  }
  
  void stop_task_() {
    this->is_playing_ = false;
    if (this->task_handle_ != nullptr) {
      for (int i = 0; i < 40 && this->task_handle_ != nullptr; ++i) {
        vTaskDelay(pdMS_TO_TICKS(5));
      }
      if (this->task_handle_ != nullptr) {
        vTaskDelete(this->task_handle_);
        this->task_handle_ = nullptr;
      }
    }
  }
  
  void run_playback_() {
    vTaskDelay(pdMS_TO_TICKS(20));
    
    int16_t pcm_buf[256];
    
    while (this->is_playing_) {
      if (this->read_offset_ >= this->data_len_) {
        if (this->is_loop_) {
          this->read_offset_ = 0;
          this->valprev_ = 0;
          this->index_ = 0;
        } else {
          break;
        }
      }
      
      size_t bytes_to_decode = std::min((size_t)128, this->data_len_ - this->read_offset_);
      size_t samples = 0;
      for (size_t i = 0; i < bytes_to_decode; ++i) {
        uint8_t byte = this->data_[this->read_offset_++];
        pcm_buf[samples++] = this->decode_sample_(byte & 0x0F);
        pcm_buf[samples++] = this->decode_sample_((byte >> 4) & 0x0F);
      }
      
      size_t total_bytes = samples * sizeof(int16_t);
      const uint8_t *ptr = reinterpret_cast<const uint8_t *>(pcm_buf);
      
      while (total_bytes > 0 && this->is_playing_) {
        size_t written = this->speaker_->play(ptr, total_bytes, pdMS_TO_TICKS(50));
        if (written > 0) {
          ptr += written;
          total_bytes -= written;
        } else {
          vTaskDelay(pdMS_TO_TICKS(5));
        }
      }
    }
    
    if (this->is_playing_ && !this->is_loop_) {
      this->speaker_->finish();
      uint32_t wait_count = 0;
      while (this->is_playing_ && this->speaker_->is_running() && wait_count < 150) {
        vTaskDelay(pdMS_TO_TICKS(20));
        wait_count++;
      }
      ESP_LOGD(PCM_PLAYER_TAG, "PCM audio finished");
      if (this->on_finished_) {
        this->on_finished_();
      }
    }
    
    this->is_playing_ = false;
  }
  
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
