#pragma once

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/core/preferences.h"
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
static const uint32_t HASH_SLOT1_CHIME_NAME  = 2841950201UL;
static const uint32_t HASH_SLOT2_CHIME_NAME  = 2841950202UL;
static const uint32_t HASH_SLOT1_PROC_NAME   = 2841950203UL;
static const uint32_t HASH_SLOT2_PROC_NAME   = 2841950204UL;
static const uint32_t HASH_SLOT1_CANCEL_NAME = 2841950205UL;
static const uint32_t HASH_SLOT2_CANCEL_NAME = 2841950206UL;

struct SoundFixedStringPref {
  char value[64];
};
extern "C" {
size_t nim_pcm_parse_caud_count(const uint8_t *data, uint32_t part_size);
bool nim_pcm_get_caud_entry(
    const uint8_t *data,
    uint32_t part_size,
    size_t index,
    char *out_name,
    size_t max_name_len,
    uint32_t *out_offset,
    uint32_t *out_size
);
bool nim_dma_stream_start(int kind, uint32_t max_duration_ms, uint32_t inactivity_timeout_ms, bool is_loop);
void nim_dma_stream_feed(size_t bytes);
void nim_dma_stream_finish(void);
void nim_dma_stream_abort(void);
int nim_dma_stream_tick(uint32_t now_ms);
bool nim_dma_stream_is_active(void);
int nim_dma_stream_get_kind(void);
uint32_t nim_dma_stream_get_elapsed_ms(uint32_t now_ms);
}

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

  void init_partitions(
      select::Select *chime_sel = nullptr,
      select::Select *proc_sel = nullptr,
      select::Select *cancel_sel = nullptr,
      select::Select *chime_sel2 = nullptr,
      select::Select *proc_sel2 = nullptr,
      select::Select *cancel_sel2 = nullptr
  ) {
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

    // Always populate full options lists (17 acoustic themes + Silent + custom partition sounds)
    this->chime_options_storage_ = {
      "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
      "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
      "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime",
      "Silent"
    };
    for (const auto &c : this->custom_chimes_) {
      this->chime_options_storage_.push_back(c.name);
    }
    FixedVector<const char *> fixed_chimes;
    fixed_chimes.init(this->chime_options_storage_.size());
    for (const auto &opt : this->chime_options_storage_) fixed_chimes.push_back(opt.c_str());
    if (chime_sel != nullptr) chime_sel->traits.set_options(fixed_chimes);
    if (chime_sel2 != nullptr) chime_sel2->traits.set_options(fixed_chimes);
    if (!this->custom_chimes_.empty()) {
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Wake Chime Sound options with %zu custom sound(s)", this->custom_chimes_.size());
    }

    this->proc_options_storage_ = {
      "Spinner", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets",
      "Raindrops", "Forest Stream", "Campfire Ember", "Shishi-Odoshi", "Soft Footsteps",
      "Radar Ping", "Data Crunch", "Telemetry Blip", "Quantum Flux", "Retro Terminal",
      "Silent"
    };
    for (const auto &p : this->custom_processing_sounds_) {
      this->proc_options_storage_.push_back(p.name);
    }
    FixedVector<const char *> fixed_procs;
    fixed_procs.init(this->proc_options_storage_.size());
    for (const auto &opt : this->proc_options_storage_) fixed_procs.push_back(opt.c_str());
    if (proc_sel != nullptr) proc_sel->traits.set_options(fixed_procs);
    if (proc_sel2 != nullptr) proc_sel2->traits.set_options(fixed_procs);
    if (!this->custom_processing_sounds_.empty()) {
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Processing Sound options with %zu custom sound(s)", this->custom_processing_sounds_.size());
    }

    this->cancel_options_storage_ = {
      "Match Wake Chime", "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba",
      "Meditation Bell", "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl",
      "Acoustic Harp", "Woodblock", "Ceramic Bell", "Neon Shimmer", "Prism Ping",
      "Cyber Bloom", "Quantum Beep", "Aero Chime", "Silent"
    };
    for (const auto &cs : this->custom_cancel_sounds_) {
      this->cancel_options_storage_.push_back(cs.name);
    }
    FixedVector<const char *> fixed_cancels;
    fixed_cancels.init(this->cancel_options_storage_.size());
    for (const auto &opt : this->cancel_options_storage_) fixed_cancels.push_back(opt.c_str());
    if (cancel_sel != nullptr) cancel_sel->traits.set_options(fixed_cancels);
    if (cancel_sel2 != nullptr) cancel_sel2->traits.set_options(fixed_cancels);
    if (!this->custom_cancel_sounds_.empty()) {
      ESP_LOGI(PCM_PLAYER_TAG, "Updated Cancel Sound options with %zu custom sound(s)", this->custom_cancel_sounds_.size());
    }

    // Restore persistent sound names from NVS (or migrate legacy indices)
    this->restore_select_option_(chime_sel, HASH_SLOT1_CHIME_NAME, this->chime_options_storage_, "Bell Ping");
    this->restore_select_option_(chime_sel2, HASH_SLOT2_CHIME_NAME, this->chime_options_storage_, "Modern Chime");
    this->restore_select_option_(proc_sel, HASH_SLOT1_PROC_NAME, this->proc_options_storage_, "Spinner");
    this->restore_select_option_(proc_sel2, HASH_SLOT2_PROC_NAME, this->proc_options_storage_, "Pulse");
    this->restore_select_option_(cancel_sel, HASH_SLOT1_CANCEL_NAME, this->cancel_options_storage_, "Match Wake Chime");
    this->restore_select_option_(cancel_sel2, HASH_SLOT2_CANCEL_NAME, this->cancel_options_storage_, "Match Wake Chime");
  }

  void save_sound_pref_(uint32_t hash, const std::string &name) {
    if (global_preferences == nullptr || name.empty()) return;
    SoundFixedStringPref pref{};
    strncpy(pref.value, name.c_str(), sizeof(pref.value) - 1);
    auto p = global_preferences->make_preference<SoundFixedStringPref>(hash);
    p.save(&pref);
  }

  void restore_select_option_(
      select::Select *sel,
      uint32_t hash,
      const std::vector<std::string> &options,
      const std::string &default_option
  ) {
    if (sel == nullptr) return;
    std::string active = default_option;
    bool found_saved = false;
    if (global_preferences != nullptr) {
      SoundFixedStringPref pref{};
      auto p = global_preferences->make_preference<SoundFixedStringPref>(hash);
      if (p.load(&pref) && pref.value[0] != '\0') {
        std::string candidate(pref.value);
        for (const auto &opt : options) {
          if (opt == candidate) {
            active = candidate;
            found_saved = true;
            break;
          }
        }
      }
      if (!found_saved) {
        auto idx_pref = global_preferences->make_preference<size_t>(sel->get_object_id_hash());
        size_t idx = 0;
        if (idx_pref.load(&idx) && idx < options.size()) {
          active = options[idx];
          ESP_LOGI(PCM_PLAYER_TAG, "Migrated sound setting from index %zu: '%s'", idx, active.c_str());
          this->save_sound_pref_(hash, active);
        }
      }
    }
    sel->publish_state(active);
  }

  void save_slot1_chime(const std::string &name) { save_sound_pref_(HASH_SLOT1_CHIME_NAME, name); }
  void save_slot2_chime(const std::string &name) { save_sound_pref_(HASH_SLOT2_CHIME_NAME, name); }
  void save_slot1_proc(const std::string &name) { save_sound_pref_(HASH_SLOT1_PROC_NAME, name); }
  void save_slot2_proc(const std::string &name) { save_sound_pref_(HASH_SLOT2_PROC_NAME, name); }
  void save_slot1_cancel(const std::string &name) { save_sound_pref_(HASH_SLOT1_CANCEL_NAME, name); }
  void save_slot2_cancel(const std::string &name) { save_sound_pref_(HASH_SLOT2_CANCEL_NAME, name); }

  static std::vector<CustomSoundItem> parse_custom_sounds(const uint8_t *part_data, size_t part_size, const std::string &default_name) {
    std::vector<CustomSoundItem> items;
    if (part_data == nullptr || part_size < 32) return items;

    size_t count = (nim_pcm_parse_caud_count != nullptr) ? nim_pcm_parse_caud_count(part_data, part_size) : 0;
    if (count > 0) {
      for (size_t i = 0; i < count; i++) {
        char name_buf[33] = {0};
        uint32_t offset = 0, size = 0;
        if (nim_pcm_get_caud_entry && nim_pcm_get_caud_entry(part_data, part_size, i, name_buf, sizeof(name_buf), &offset, &size)) {
          if (offset >= part_size || offset + size > part_size || size < 44) continue;
          WavInfo wav = parse_wav(part_data + offset, size);
          if (wav.valid) {
            std::string sound_name = (name_buf[0] != '\0') ? std::string(name_buf) : (default_name + " " + std::to_string(i + 1));
            items.push_back({sound_name, wav.pcm_data, wav.pcm_len, wav.sample_rate, wav.channels, wav.bits_per_sample});
            ESP_LOGI(PCM_PLAYER_TAG, "Loaded custom sound: '%s' (%u bytes PCM)", sound_name.c_str(), (unsigned int)wav.pcm_len);
          }
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
    this->current_stream_kind_ = loop ? 2 : 1;
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
    this->current_stream_kind_ = 2;
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
    this->current_stream_kind_ = 1;
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
    this->current_stream_kind_ = 3;
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

    this->interrupt_playback_();

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

    uint32_t max_dur = 5000;
    uint32_t inact_to = 2000;
    if (this->current_stream_kind_ == 2) {
      max_dur = 25000;
      inact_to = 3000;
    } else if (this->current_stream_kind_ == 3) {
      max_dur = 3000;
      inact_to = 1500;
    }
    nim_dma_stream_start(this->current_stream_kind_, max_dur, inact_to, loop);

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
      nim_dma_stream_abort();
    }
  }

  void play_raw_pcm(const uint8_t *data, size_t length, uint32_t sample_rate, uint16_t channels, uint16_t bits, bool loop = false, float volume = -1.0f, const char *name = "raw_pcm") {
    if (this->speaker_ == nullptr || data == nullptr || length == 0) return;

    this->interrupt_playback_();

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

    uint32_t max_dur = 5000;
    uint32_t inact_to = 2000;
    if (this->current_stream_kind_ == 2) {
      max_dur = 25000;
      inact_to = 3000;
    } else if (this->current_stream_kind_ == 3) {
      max_dur = 3000;
      inact_to = 1500;
    }
    nim_dma_stream_start(this->current_stream_kind_, max_dur, inact_to, loop);

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
      nim_dma_stream_abort();
    }
  }

  void set_on_finished(std::function<void()> callback) { this->on_finished_ = callback; }
  void set_on_cancel_finished(std::function<void()> callback) { this->on_cancel_finished_ = callback; }

  void interrupt_playback_() {
    this->is_playing_ = false;
    this->is_playing_cancel_ = false;
    this->is_loop_ = false;
    nim_dma_stream_abort();
    TaskHandle_t h = this->task_handle_;
    this->task_handle_ = nullptr;
    if (h != nullptr) {
      vTaskDelete(h);
    }
    if (this->speaker_ != nullptr) {
      this->speaker_->stop();
    }
  }

  void stop() {
    if (!this->is_playing_ && this->task_handle_ == nullptr) return;
    bool was_cancel = this->is_playing_cancel_;
    this->interrupt_playback_();
    ESP_LOGD(PCM_PLAYER_TAG, "Audio stopped");
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

  bool is_playing() const { return this->is_playing_; }
  bool is_playing_cancel() const { return this->is_playing_ && this->is_playing_cancel_; }

 protected:
  int current_stream_kind_{1};
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
    this->interrupt_playback_();
  }

  void run_playback_() {

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
            nim_dma_stream_feed(written);
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
            nim_dma_stream_feed(written);
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
      nim_dma_stream_finish();
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
