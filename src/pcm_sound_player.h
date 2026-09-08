#pragma once

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/speaker/speaker.h"
#include "esphome/components/select/select.h"
#include "sound_data.h"
#include <esp_partition.h>
#include <string>
#include <vector>
#include <algorithm>
#include <functional>
#include <cstring>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace esphome {

static const char *const PCM_PLAYER_TAG = "pcm_sound_player";
static const uint32_t CAUD_MAGIC = 0x44554143; // 'CAUD' in little-endian

struct __attribute__((packed)) CustomAudioHeader {
  uint32_t magic;         // 0x44554143 ("CAUD")
  uint16_t version;       // 1
  uint16_t count;         // Number of sound entries
  uint8_t  reserved[24];  // 32 bytes total
};
static_assert(sizeof(CustomAudioHeader) == 32, "CustomAudioHeader must be 32 bytes");

struct __attribute__((packed)) CustomAudioEntry {
  char     name[32];      // Null-terminated sound name, e.g. "My Chime"
  uint32_t offset;        // Byte offset from partition start
  uint32_t size;          // Byte length of WAV file
  uint8_t  reserved[8];   // 48 bytes total
};
static_assert(sizeof(CustomAudioEntry) == 48, "CustomAudioEntry must be 48 bytes");

struct CustomSoundItem {
  std::string name;
  const uint8_t *pcm_data{nullptr};
  size_t pcm_len{0};
  uint32_t sample_rate{16000};
  uint16_t channels{1};
  uint16_t bits_per_sample{16};
};

struct WavInfo {
  bool valid{false};
  uint16_t channels{1};
  uint32_t sample_rate{16000};
  uint16_t bits_per_sample{16};
  const uint8_t *pcm_data{nullptr};
  size_t pcm_len{0};
};

class PcmSoundPlayer {
 public:
  void set_speaker(speaker::Speaker *speaker) { this->speaker_ = speaker; }

  void init_partitions(select::Select *chime_sel = nullptr, select::Select *proc_sel = nullptr, select::Select *cancel_sel = nullptr) {
    if (this->partitions_initialized_) return;
    this->partitions_initialized_ = true;

    // sound_data partition (custom processing sounds)
    const esp_partition_t *part_sound = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "sound_data");
    if (part_sound != nullptr) {
      esp_err_t err = esp_partition_mmap(part_sound, 0, part_sound->size, ESP_PARTITION_MMAP_DATA,
                                         &this->sound_map_ptr_, &this->sound_map_handle_);
      if (err == ESP_OK && this->sound_map_ptr_ != nullptr) {
        this->sound_partition_size_ = part_sound->size;
        ESP_LOGI(PCM_PLAYER_TAG, "Mapped sound_data partition at 0x%06X (size %u KB)",
                 (unsigned int)part_sound->address, (unsigned int)(part_sound->size / 1024));
        this->custom_processing_sounds_ = parse_custom_sounds(
            reinterpret_cast<const uint8_t *>(this->sound_map_ptr_), this->sound_partition_size_, "Custom Processing");
      }
    }

    // chime_data partition (custom wake chimes)
    const esp_partition_t *part_chime = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "chime_data");
    if (part_chime != nullptr) {
      esp_err_t err = esp_partition_mmap(part_chime, 0, part_chime->size, ESP_PARTITION_MMAP_DATA,
                                         &this->chime_map_ptr_, &this->chime_map_handle_);
      if (err == ESP_OK && this->chime_map_ptr_ != nullptr) {
        this->chime_partition_size_ = part_chime->size;
        ESP_LOGI(PCM_PLAYER_TAG, "Mapped chime_data partition at 0x%06X (size %u KB)",
                 (unsigned int)part_chime->address, (unsigned int)(part_chime->size / 1024));
        this->custom_chimes_ = parse_custom_sounds(
            reinterpret_cast<const uint8_t *>(this->chime_map_ptr_), this->chime_partition_size_, "Custom Chime");
      }
    }

    // cancel_data partition (custom cancel sounds)
    const esp_partition_t *part_cancel = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "cancel_data");
    if (part_cancel != nullptr) {
      esp_err_t err = esp_partition_mmap(part_cancel, 0, part_cancel->size, ESP_PARTITION_MMAP_DATA,
                                         &this->cancel_map_ptr_, &this->cancel_map_handle_);
      if (err == ESP_OK && this->cancel_map_ptr_ != nullptr) {
        this->cancel_partition_size_ = part_cancel->size;
        ESP_LOGI(PCM_PLAYER_TAG, "Mapped cancel_data partition at 0x%06X (size %u KB)",
                 (unsigned int)part_cancel->address, (unsigned int)(part_cancel->size / 1024));
        this->custom_cancel_sounds_ = parse_custom_sounds(
            reinterpret_cast<const uint8_t *>(this->cancel_map_ptr_), this->cancel_partition_size_, "Custom Cancel");
      }
    }

    // Update Home Assistant select entities if custom sounds were found
    if (chime_sel != nullptr && !this->custom_chimes_.empty()) {
      this->chime_options_storage_ = {
        "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
        "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
        "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime",
        "Silent"
      };
      for (const auto &c : this->custom_chimes_) {
        this->chime_options_storage_.push_back(c.name);
      }
      FixedVector<const char *> fixed_opts;
      fixed_opts.init(this->chime_options_storage_.size());
      for (const auto &opt : this->chime_options_storage_) fixed_opts.push_back(opt.c_str());
      chime_sel->traits.set_options(fixed_opts);
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Wake Chime Sound options with %zu custom sound(s)", this->custom_chimes_.size());
    }

    if (proc_sel != nullptr && !this->custom_processing_sounds_.empty()) {
      this->proc_options_storage_ = {
        "Spinner", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets",
        "Raindrops", "Forest Stream", "Campfire Ember", "Shishi-Odoshi", "Soft Footsteps",
        "Radar Ping", "Data Crunch", "Telemetry Blip", "Quantum Flux", "Retro Terminal",
        "Silent"
      };
      for (const auto &p : this->custom_processing_sounds_) {
        this->proc_options_storage_.push_back(p.name);
      }
      FixedVector<const char *> fixed_opts;
      fixed_opts.init(this->proc_options_storage_.size());
      for (const auto &opt : this->proc_options_storage_) fixed_opts.push_back(opt.c_str());
      proc_sel->traits.set_options(fixed_opts);
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Processing Sound options with %zu custom sound(s)", this->custom_processing_sounds_.size());
    }

    if (cancel_sel != nullptr && !this->custom_cancel_sounds_.empty()) {
      this->cancel_options_storage_ = {
        "Match Wake Chime", "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba",
        "Meditation Bell", "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl",
        "Acoustic Harp", "Woodblock", "Ceramic Bell", "Neon Shimmer", "Prism Ping",
        "Cyber Bloom", "Quantum Beep", "Aero Chime", "Silent"
      };
      for (const auto &cs : this->custom_cancel_sounds_) {
        this->cancel_options_storage_.push_back(cs.name);
      }
      FixedVector<const char *> fixed_opts;
      fixed_opts.init(this->cancel_options_storage_.size());
      for (const auto &opt : this->cancel_options_storage_) fixed_opts.push_back(opt.c_str());
      cancel_sel->traits.set_options(fixed_opts);
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Cancel Sound options with %zu custom sound(s)", this->custom_cancel_sounds_.size());
    }
  }

  static std::vector<CustomSoundItem> parse_custom_sounds(const uint8_t *part_data, size_t part_size, const std::string &default_name) {
    std::vector<CustomSoundItem> items;
    if (part_data == nullptr || part_size < 32) return items;

    if (*reinterpret_cast<const uint32_t *>(part_data) == CAUD_MAGIC) {
      const CustomAudioHeader *hdr = reinterpret_cast<const CustomAudioHeader *>(part_data);
      const CustomAudioEntry *entries = reinterpret_cast<const CustomAudioEntry *>(part_data + sizeof(CustomAudioHeader));
      size_t max_entries = (part_size - sizeof(CustomAudioHeader)) / sizeof(CustomAudioEntry);
      size_t count = std::min((size_t)hdr->count, max_entries);

      for (size_t i = 0; i < count; i++) {
        const auto &e = entries[i];
        if (e.offset >= part_size || e.offset + e.size > part_size || e.size < 44) continue;
        WavInfo wav = parse_wav(part_data + e.offset, e.size);
        if (wav.valid) {
          char name_buf[33] = {0};
          memcpy(name_buf, e.name, 32);
          name_buf[32] = '\0';
          std::string sound_name = (name_buf[0] != '\0') ? std::string(name_buf) : (default_name + " " + std::to_string(i + 1));
          items.push_back({sound_name, wav.pcm_data, wav.pcm_len, wav.sample_rate, wav.channels, wav.bits_per_sample});
          ESP_LOGI(PCM_PLAYER_TAG, "Loaded custom sound: '%s' (%u bytes PCM)", sound_name.c_str(), (unsigned int)wav.pcm_len);
        }
      }
    } else {
      WavInfo wav = parse_wav(part_data, part_size);
      if (wav.valid) {
        items.push_back({default_name, wav.pcm_data, wav.pcm_len, wav.sample_rate, wav.channels, wav.bits_per_sample});
        ESP_LOGI(PCM_PLAYER_TAG, "Loaded legacy single custom sound: '%s'", default_name.c_str());
      }
    }
    return items;
  }

  static WavInfo parse_wav(const uint8_t *data, size_t max_len) {
    WavInfo info;
    if (data == nullptr || max_len < 44) return info;

    if (nim_pcm_parse_wav != nullptr) {
      uint32_t sample_rate = 0;
      uint16_t channels = 0;
      uint16_t bits = 0;
      size_t pcm_offset = 0;
      size_t pcm_len = 0;
      if (nim_pcm_parse_wav(data, max_len, &sample_rate, &channels, &bits, &pcm_offset, &pcm_len)) {
        info.valid = true;
        info.channels = channels;
        info.sample_rate = sample_rate;
        info.bits_per_sample = bits;
        info.pcm_data = data + pcm_offset;
        info.pcm_len = pcm_len;
      }
    }
    return info;
  }

  void play_sound(const std::string &name, bool loop = false, float volume = -1.0f) {
    this->is_playing_cancel_ = false;
    if (this->speaker_ == nullptr) return;
    if (name == "Silent") {
      this->stop();
      return;
    }

    const satellite_audio::SoundEntry *entry = satellite_audio::find_sound(name);
    if (!entry) {
      ESP_LOGW(PCM_PLAYER_TAG, "Sound not found: '%s'", name.c_str());
      return;
    }

    this->play_adpcm(entry->data, entry->length, loop, volume, entry->name);
  }

  void play_processing_sound(const std::string &name, bool loop = true, float volume = -1.0f) {
    this->is_playing_cancel_ = false;
    if (name == "Silent") {
      this->stop();
      return;
    }
    for (const auto &item : this->custom_processing_sounds_) {
      if (item.name == name || (name == "Custom" && &item == &this->custom_processing_sounds_[0])) {
        this->play_raw_pcm(item.pcm_data, item.pcm_len, item.sample_rate, item.channels, item.bits_per_sample, loop, volume, item.name.c_str());
        return;
      }
    }
    this->play_sound(name, loop, volume);
  }

  void play_chime(const std::string &name, bool loop = false, float volume = -1.0f) {
    this->is_playing_cancel_ = false;
    if (name == "Silent") {
      this->stop();
      return;
    }
    for (const auto &item : this->custom_chimes_) {
      if (item.name == name || (name == "Custom" && &item == &this->custom_chimes_[0])) {
        this->play_raw_pcm(item.pcm_data, item.pcm_len, item.sample_rate, item.channels, item.bits_per_sample, loop, volume, item.name.c_str());
        return;
      }
    }
    this->play_sound(name, loop, volume);
  }

  void play_cancel_sound(const std::string &name, bool loop = false, float volume = -1.0f) {
    if (name == "Silent") {
      this->stop();
      return;
    }
    this->is_playing_cancel_ = true;
    for (const auto &item : this->custom_cancel_sounds_) {
      if (item.name == name || (name == "Custom" && !this->custom_cancel_sounds_.empty() && &item == &this->custom_cancel_sounds_[0])) {
        this->play_raw_pcm(item.pcm_data, item.pcm_len, item.sample_rate, item.channels, item.bits_per_sample, loop, volume, item.name.c_str());
        return;
      }
    }
    for (const auto &item : this->custom_chimes_) {
      if (item.name == name || (name == "Custom" && !this->custom_chimes_.empty() && &item == &this->custom_chimes_[0])) {
        this->play_raw_pcm(item.pcm_data, item.pcm_len, item.sample_rate, item.channels, item.bits_per_sample, loop, volume, item.name.c_str());
        return;
      }
    }
    std::string lookup = name;
    if (lookup.rfind("cancel-", 0) != 0 && lookup.rfind("Cancel ", 0) != 0) {
      lookup = "cancel-" + lookup;
    }
    const satellite_audio::SoundEntry *entry = satellite_audio::find_sound(lookup);
    if (!entry) entry = satellite_audio::find_sound(name);
    if (!entry) entry = satellite_audio::find_sound("cancel-bell-ping");
    if (entry) {
      this->play_adpcm(entry->data, entry->length, loop, volume, entry->name);
    }
  }

  void play_adpcm(const uint8_t *data, size_t length, bool loop = false, float volume = -1.0f, const char *name = "sound") {
    if (this->speaker_ == nullptr || data == nullptr || length == 0) return;

    this->stop_task_();

    this->data_ = data;
    this->data_len_ = length;
    this->read_offset_ = 0;
    this->is_loop_ = loop;
    this->is_raw_pcm_ = false;
    this->valprev_ = 0;
    this->index_ = 0;
    this->is_playing_ = true;

    audio::AudioStreamInfo info(16, 1, 16000);
    this->speaker_->set_audio_stream_info(info);
    if (volume >= 0.0f) {
      this->speaker_->set_volume(volume);
    }
    this->speaker_->start();

    ESP_LOGD(PCM_PLAYER_TAG, "Playing ADPCM audio: %s (%zu bytes, loop=%d, vol=%.2f)", name, length, (int)loop, volume);

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

  void play_raw_pcm(const uint8_t *data, size_t length, uint32_t sample_rate, uint16_t channels, uint16_t bits, bool loop = false, float volume = -1.0f, const char *name = "raw_pcm") {
    if (this->speaker_ == nullptr || data == nullptr || length == 0) return;

    this->stop_task_();

    this->data_ = data;
    this->data_len_ = length;
    this->read_offset_ = 0;
    this->is_loop_ = loop;
    this->is_raw_pcm_ = true;
    this->is_playing_ = true;

    audio::AudioStreamInfo info(bits, channels, sample_rate);
    this->speaker_->set_audio_stream_info(info);
    if (volume >= 0.0f) {
      this->speaker_->set_volume(volume);
    }
    this->speaker_->start();

    ESP_LOGI(PCM_PLAYER_TAG, "Playing custom raw PCM: %s (%zu bytes, %uHz, %uch, %ubit, loop=%d, vol=%.2f)",
             name, length, (unsigned int)sample_rate, (unsigned int)channels, (unsigned int)bits, (int)loop, volume);

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
  void set_on_cancel_finished(std::function<void()> callback) { this->on_cancel_finished_ = callback; }

  void stop() {
    if (!this->is_playing_ && this->task_handle_ == nullptr) return;
    this->is_playing_ = false;
    this->is_playing_cancel_ = false;
    this->is_loop_ = false;
    this->stop_task_();
    if (this->speaker_ != nullptr) {
      this->speaker_->stop();
    }
    ESP_LOGD(PCM_PLAYER_TAG, "Audio stopped");
    if (this->on_finished_) {
      this->on_finished_();
    }
  }

  bool is_playing() const { return this->is_playing_; }
  bool is_playing_cancel() const { return this->is_playing_ && this->is_playing_cancel_; }

 protected:
  speaker::Speaker *speaker_{nullptr};
  const uint8_t *data_{nullptr};
  size_t data_len_{0};
  size_t read_offset_{0};
  volatile bool is_playing_{false};
  volatile bool is_playing_cancel_{false};
  bool is_loop_{false};
  bool is_raw_pcm_{false};
  std::function<void()> on_finished_{nullptr};
  std::function<void()> on_cancel_finished_{nullptr};
  TaskHandle_t task_handle_{nullptr};

  // Memory-mapped flash partitions
  bool partitions_initialized_{false};
  const void *sound_map_ptr_{nullptr};
  esp_partition_mmap_handle_t sound_map_handle_{0};
  size_t sound_partition_size_{0};

  const void *chime_map_ptr_{nullptr};
  esp_partition_mmap_handle_t chime_map_handle_{0};
  size_t chime_partition_size_{0};

  const void *cancel_map_ptr_{nullptr};
  esp_partition_mmap_handle_t cancel_map_handle_{0};
  size_t cancel_partition_size_{0};

  std::vector<CustomSoundItem> custom_chimes_;
  std::vector<CustomSoundItem> custom_processing_sounds_;
  std::vector<CustomSoundItem> custom_cancel_sounds_;

  std::vector<std::string> chime_options_storage_;
  std::vector<std::string> proc_options_storage_;
  std::vector<std::string> cancel_options_storage_;

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

    if (this->is_raw_pcm_) {
      while (this->is_playing_) {
        if (this->read_offset_ >= this->data_len_) {
          if (this->is_loop_) {
            this->read_offset_ = 0;
          } else {
            break;
          }
        }

        size_t bytes_to_send = std::min((size_t)512, this->data_len_ - this->read_offset_);
        const uint8_t *ptr = this->data_ + this->read_offset_;

        while (bytes_to_send > 0 && this->is_playing_) {
          size_t written = this->speaker_->play(ptr, bytes_to_send, pdMS_TO_TICKS(50));
          if (written > 0) {
            ptr += written;
            this->read_offset_ += written;
            bytes_to_send -= written;
          } else {
            vTaskDelay(pdMS_TO_TICKS(5));
          }
        }
      }
    } else {
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
        if (nim_pcm_decode_adpcm_chunk != nullptr) {
          int16_t vp = static_cast<int16_t>(this->valprev_);
          int8_t idx = this->index_;
          samples = nim_pcm_decode_adpcm_chunk(
              this->data_ + this->read_offset_,
              bytes_to_decode,
              pcm_buf,
              1.0f,
              &vp,
              &idx
          );
          this->valprev_ = vp;
          this->index_ = idx;
          this->read_offset_ += bytes_to_decode;
        } else {
          break;
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
    }

    if (this->is_playing_ && !this->is_loop_) {
      this->speaker_->finish();
      uint32_t wait_count = 0;
      while (this->is_playing_ && this->speaker_->is_running() && wait_count < 150) {
        vTaskDelay(pdMS_TO_TICKS(20));
        wait_count++;
      }
      ESP_LOGD(PCM_PLAYER_TAG, "Audio finished");
      bool was_cancel = this->is_playing_cancel_;
      if (this->on_finished_) {
        this->on_finished_();
      }
      if (was_cancel) {
        if (this->on_cancel_finished_) {
          this->on_cancel_finished_();
        }
        call_nim_cancel_done(true);
      }
    }

    this->is_playing_ = false;
    this->is_playing_cancel_ = false;
  }
};

inline PcmSoundPlayer &get_pcm_sound_player() {
  static PcmSoundPlayer instance;
  return instance;
}

} // namespace esphome
