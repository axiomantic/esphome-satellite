#pragma once

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/micro_wake_word/micro_wake_word.h"
#include "esphome/components/select/select.h"
#include <esp_partition.h>
#include <string>
#include <vector>
#include <cstring>

namespace esphome {
namespace wake_loader {

static const char *const TAG = "wake_loader";
static const uint32_t WAKE_MAGIC = 0x57414B45; // 'WAKE' in little-endian

struct __attribute__((packed)) WakeModelHeader {
  uint32_t magic;                 // 0x57414B45 ("WAKE")
  uint16_t header_version;        // 1
  uint16_t flags;                 // 0
  uint32_t model_size;            // Size in bytes of the tflite model following this header
  uint8_t  probability_cutoff;    // Quantized cutoff (0-255). 0 = default (102 for 0.40)
  uint8_t  sliding_window_size;   // Default 5
  uint16_t tensor_arena_kb;       // Tensor arena size in KB (e.g. 40 = 40960 bytes). If 0, default 40KB
  char     wake_word[32];         // Null-terminated wake word string, e.g. "Marvin"
  uint8_t  reserved[16];          // Padding to 64 bytes
};
static_assert(sizeof(WakeModelHeader) == 64, "WakeModelHeader must be exactly 64 bytes");

extern "C" {
bool nim_wake_loader_validate_header(
    const uint8_t *data,
    uint32_t part_size,
    int slot_index,
    uint32_t *out_model_size,
    uint8_t *out_cutoff,
    size_t *out_window,
    size_t *out_arena,
    char *out_name,
    size_t max_name_len
) __attribute__((weak));

uint8_t nim_wake_loader_scale_cutoff(uint8_t base_cutoff, const char *level) __attribute__((weak));
}

struct CustomWakeSlot {
  std::string name;
  micro_wake_word::WakeWordModel *model{nullptr};
  const void *map_ptr{nullptr};
  esp_partition_mmap_handle_t map_handle{0};
  uint8_t base_cutoff{102};
};

class StreamingModelWindowAccessor : public micro_wake_word::StreamingModel {
 public:
  static void set_window(micro_wake_word::StreamingModel *model, size_t window_size) {
    if (model == nullptr) return;
    auto *accessor = static_cast<StreamingModelWindowAccessor *>(model);
    if (window_size < 2) window_size = 2;
    if (window_size > 10) window_size = 10;
    accessor->sliding_window_size_ = window_size;
    accessor->recent_streaming_probabilities_.assign(window_size, 0);
    accessor->last_n_index_ = 0;
  }
};


class WakePartitionLoader {
 public:
  static WakePartitionLoader &instance() {
    static WakePartitionLoader inst;
    return inst;
  }

  void init(
      micro_wake_word::MicroWakeWord *mww,
      select::Select *slot1_select = nullptr,
      select::Select *slot2_select = nullptr
  ) {
    if (mww == nullptr) {
      ESP_LOGE(TAG, "MicroWakeWord pointer is null!");
      return;
    }

    const char *part_names[3] = {"wake_model", "wake_model_2", "wake_model_3"};

    for (size_t i = 0; i < 3; i++) {
      const esp_partition_t *part = esp_partition_find_first(
          ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, part_names[i]);

      if (part == nullptr) {
        continue;
      }

      ESP_LOGI(TAG, "Found '%s' partition at offset 0x%06X (size %u KB)",
               part_names[i], (unsigned int)part->address, (unsigned int)(part->size / 1024));

      CustomWakeSlot slot;
      esp_err_t err = esp_partition_mmap(part, 0, part->size, ESP_PARTITION_MMAP_DATA, &slot.map_ptr, &slot.map_handle);
      if (err != ESP_OK || slot.map_ptr == nullptr) {
        ESP_LOGE(TAG, "Failed to memory-map %s partition: err=0x%X", part_names[i], err);
        continue;
      }

      uint32_t model_size = 0;
      uint8_t cutoff = 102;
      size_t window = 5;
      size_t arena_size = 40960;
      char name_buf[33] = {0};

      if (nim_wake_loader_validate_header != nullptr) {
        bool ok = nim_wake_loader_validate_header(
            reinterpret_cast<const uint8_t *>(slot.map_ptr),
            part->size,
            i + 1,
            &model_size,
            &cutoff,
            &window,
            &arena_size,
            name_buf,
            sizeof(name_buf)
        );
        if (!ok) {
          esp_partition_munmap(slot.map_handle);
          continue;
        }
      } else {
        esp_partition_munmap(slot.map_handle);
        continue;
      }

      slot.name = std::string(name_buf);
      slot.base_cutoff = cutoff;
      const uint8_t *model_data = reinterpret_cast<const uint8_t *>(slot.map_ptr) + sizeof(WakeModelHeader);

      ESP_LOGI(TAG, "Registering custom wake word slot %u (%s): '%s' (%u bytes, cutoff=%u, arena=%u)",
               (unsigned int)(i + 1), part_names[i], slot.name.c_str(), (unsigned int)model_size, cutoff, (unsigned int)arena_size);

      std::string model_id = "custom_model_" + std::to_string(i + 1);
      slot.model = new micro_wake_word::WakeWordModel(
          model_id,
          model_data,
          cutoff,
          window,
          slot.name,
          arena_size,
          true,   // default_enabled
          false   // internal_only
      );

      mww->add_wake_word_model(slot.model);
      this->slots_.push_back(slot);
      this->custom_names_.push_back(slot.name);
    }

    if (slot1_select != nullptr) {
      this->slot1_options_ = {"Mr. Clemens", "Okay Nabu"};
      for (const auto &name : this->custom_names_) {
        this->slot1_options_.push_back(name);
      }
      FixedVector<const char *> fixed_opts1;
      fixed_opts1.init(this->slot1_options_.size());
      for (const auto &opt : this->slot1_options_) {
        fixed_opts1.push_back(opt.c_str());
      }
      slot1_select->traits.set_options(fixed_opts1);
      ESP_LOGI(TAG, "Populated Slot 1 Wake Word select with %zu options", this->slot1_options_.size());
    }

    if (slot2_select != nullptr) {
      this->slot2_options_ = {"Disabled", "Mr. Clemens", "Okay Nabu"};
      for (const auto &name : this->custom_names_) {
        this->slot2_options_.push_back(name);
      }
      FixedVector<const char *> fixed_opts2;
      fixed_opts2.init(this->slot2_options_.size());
      for (const auto &opt : this->slot2_options_) {
        fixed_opts2.push_back(opt.c_str());
      }
      slot2_select->traits.set_options(fixed_opts2);
      ESP_LOGI(TAG, "Populated Slot 2 Wake Word select with %zu options", this->slot2_options_.size());
    }
  }

  bool has_custom_models() const { return !this->slots_.empty(); }
  const std::vector<std::string> &custom_names() const { return this->custom_names_; }

  void update_slot_models(
      const std::string &slot1_choice,
      const std::string &slot2_choice,
      micro_wake_word::WakeWordModel *clemens,
      micro_wake_word::WakeWordModel *nabu
  ) {
    this->slot1_model_name_ = slot1_choice;
    this->slot2_model_name_ = slot2_choice;
    ESP_LOGI(TAG, "Configured Wake Word Slots -> Slot 1: '%s', Slot 2: '%s'",
             slot1_choice.c_str(), slot2_choice.c_str());

    auto should_enable = [&](const std::string &name) -> bool {
      if (name == this->slot1_model_name_) return true;
      if (this->slot2_model_name_ != "Disabled" && name == this->slot2_model_name_) return true;
      return false;
    };

    if (clemens) {
      if (should_enable("Mr. Clemens")) clemens->enable();
      else clemens->disable();
    }
    if (nabu) {
      if (should_enable("Okay Nabu")) nabu->enable();
      else nabu->disable();
    }
    for (auto &s : this->slots_) {
      if (s.model) {
        if (should_enable(s.name)) s.model->enable();
        else s.model->disable();
      }
    }

    this->apply_all_sensitivities(clemens, nabu);
  }

  void set_slot_sensitivity(
      int slot,
      const std::string &level,
      micro_wake_word::WakeWordModel *clemens,
      micro_wake_word::WakeWordModel *nabu
  ) {
    ESP_LOGI(TAG, "Setting Slot %d sensitivity to '%s'", slot, level.c_str());
    if (slot == 1) {
      this->slot1_sensitivity_ = level;
    } else if (slot == 2) {
      this->slot2_sensitivity_ = level;
    }
    this->apply_all_sensitivities(clemens, nabu);
  }

  void apply_all_sensitivities(
      micro_wake_word::WakeWordModel *clemens,
      micro_wake_word::WakeWordModel *nabu
  ) {
    auto get_cutoff_for_model = [&](const std::string &model_name, uint8_t base_cutoff) -> uint8_t {
      std::string level = this->slot1_sensitivity_;
      if (this->slot2_model_name_ != "Disabled" && model_name == this->slot2_model_name_) {
        level = this->slot2_sensitivity_;
      }
      if (nim_wake_loader_scale_cutoff != nullptr) {
        return nim_wake_loader_scale_cutoff(base_cutoff, level.c_str());
      }
      return base_cutoff;
    };

    if (clemens) {
      uint8_t c = get_cutoff_for_model("Mr. Clemens", 102);
      clemens->set_probability_cutoff(c);
      ESP_LOGI(TAG, "Applied Clemens cutoff %u (%s)", c,
               (this->slot2_model_name_ == "Mr. Clemens" ? this->slot2_sensitivity_.c_str() : this->slot1_sensitivity_.c_str()));
    }
    if (nabu) {
      uint8_t c = get_cutoff_for_model("Okay Nabu", 170);
      nabu->set_probability_cutoff(c);
      ESP_LOGI(TAG, "Applied Nabu cutoff %u (%s)", c,
               (this->slot2_model_name_ == "Okay Nabu" ? this->slot2_sensitivity_.c_str() : this->slot1_sensitivity_.c_str()));
    }
    for (auto &s : this->slots_) {
      if (s.model) {
        uint8_t c = get_cutoff_for_model(s.name, s.base_cutoff);
        s.model->set_probability_cutoff(c);
        ESP_LOGI(TAG, "Applied '%s' cutoff %u", s.name.c_str(), c);
      }
    }
  }

  int get_slot_for_wake_word(const std::string &detected_word) const {
    if (detected_word == this->slot1_model_name_) {
      return 1;
    }
    if (this->slot2_model_name_ != "Disabled" && detected_word == this->slot2_model_name_) {
      return 2;
    }
    return 1;
  }

  void set_sliding_window(size_t window, micro_wake_word::WakeWordModel *clemens, micro_wake_word::WakeWordModel *nabu) {
    ESP_LOGI(TAG, "Updating microWakeWord sliding window size to %zu frames", window);
    this->sliding_window_size_ = window;

    StreamingModelWindowAccessor::set_window(clemens, window);
    StreamingModelWindowAccessor::set_window(nabu, window);
    for (auto &s : this->slots_) {
      StreamingModelWindowAccessor::set_window(s.model, window);
    }
  }

  void set_mic_pre_gain(float db) {
    ESP_LOGI(TAG, "Setting microphone pre-gain boost to %.1f dB", db);
    this->mic_pre_gain_db_ = db;
    extern void nim_audio_dsp_set_mic_pre_gain(float db) __attribute__((weak));
    if (nim_audio_dsp_set_mic_pre_gain != nullptr) {
      nim_audio_dsp_set_mic_pre_gain(db);
    }
  }

  // Backward compatibility helpers
  void handle_active_wake_word_change(const std::string &opt, micro_wake_word::WakeWordModel *clemens, micro_wake_word::WakeWordModel *nabu) {
    this->update_slot_models(opt, this->slot2_model_name_, clemens, nabu);
  }

  void handle_sensitivity_change(const std::string &level, micro_wake_word::WakeWordModel *clemens, micro_wake_word::WakeWordModel *nabu) {
    this->set_slot_sensitivity(1, level, clemens, nabu);
  }

 protected:
  std::vector<CustomWakeSlot> slots_;
  std::vector<std::string> custom_names_;
  std::vector<std::string> slot1_options_;
  std::vector<std::string> slot2_options_;
  std::string slot1_model_name_{"Mr. Clemens"};
  std::string slot2_model_name_{"Disabled"};
  std::string slot1_sensitivity_{"Moderately sensitive"};
  std::string slot2_sensitivity_{"Moderately sensitive"};
  size_t sliding_window_size_{3};
  float mic_pre_gain_db_{3.0f};
};

inline WakePartitionLoader &get_wake_partition_loader() {
  return WakePartitionLoader::instance();
}

} // namespace wake_loader
} // namespace esphome
