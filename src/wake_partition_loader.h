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

struct CustomWakeSlot {
  std::string name;
  micro_wake_word::WakeWordModel *model{nullptr};
  const void *map_ptr{nullptr};
  esp_partition_mmap_handle_t map_handle{0};
};

class WakePartitionLoader {
 public:
  static WakePartitionLoader &instance() {
    static WakePartitionLoader inst;
    return inst;
  }

  void init(micro_wake_word::MicroWakeWord *mww, select::Select *active_select) {
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

      const WakeModelHeader *header = reinterpret_cast<const WakeModelHeader *>(slot.map_ptr);
      if (header->magic != WAKE_MAGIC) {
        ESP_LOGI(TAG, "No custom wake word model in %s (magic: 0x%08X)", part_names[i], (unsigned int)header->magic);
        continue;
      }

      if (header->model_size < 1000 || header->model_size > (part->size - sizeof(WakeModelHeader))) {
        ESP_LOGW(TAG, "Invalid model size in %s header: %u bytes", part_names[i], (unsigned int)header->model_size);
        continue;
      }

      char name_buf[33] = {0};
      memcpy(name_buf, header->wake_word, 32);
      name_buf[32] = '\0';
      if (name_buf[0] == '\0') {
        std::string fallback = "Custom Wake Word " + std::to_string(i + 1);
        strncpy(name_buf, fallback.c_str(), 32);
      }
      slot.name = std::string(name_buf);

      const uint8_t *model_data = reinterpret_cast<const uint8_t *>(slot.map_ptr) + sizeof(WakeModelHeader);
      uint8_t cutoff = header->probability_cutoff > 0 ? header->probability_cutoff : 102; // default 0.40 (102/255)
      size_t window = header->sliding_window_size > 0 ? header->sliding_window_size : 5;
      size_t arena_size = header->tensor_arena_kb > 0 ? (header->tensor_arena_kb * 1024) : 40960;

      ESP_LOGI(TAG, "Registering custom wake word slot %u (%s): '%s' (%u bytes, cutoff=%u, arena=%u)",
               (unsigned int)(i + 1), part_names[i], slot.name.c_str(), (unsigned int)header->model_size, cutoff, (unsigned int)arena_size);

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

    if (active_select != nullptr && !this->slots_.empty()) {
      this->options_storage_ = {"Mr. Clemens", "Okay Nabu"};
      for (const auto &name : this->custom_names_) {
        this->options_storage_.push_back(name);
      }
      this->options_storage_.push_back("All");
      FixedVector<const char *> fixed_opts;
      fixed_opts.init(this->options_storage_.size());
      for (const auto &opt : this->options_storage_) {
        fixed_opts.push_back(opt.c_str());
      }
      active_select->traits.set_options(fixed_opts);
      ESP_LOGI(TAG, "Updated Active Wake Word select options with %zu custom model(s)", this->slots_.size());
    }
  }

  bool has_custom_models() const { return !this->slots_.empty(); }
  const std::vector<std::string> &custom_names() const { return this->custom_names_; }

  void handle_active_wake_word_change(const std::string &opt, micro_wake_word::WakeWordModel *clemens, micro_wake_word::WakeWordModel *nabu) {
    ESP_LOGI(TAG, "Active wake word option changed to: '%s'", opt.c_str());
    if (opt == "Mr. Clemens") {
      if (clemens) clemens->enable();
      if (nabu) nabu->disable();
      for (auto &s : this->slots_) { if (s.model) s.model->disable(); }
    } else if (opt == "Okay Nabu") {
      if (clemens) clemens->disable();
      if (nabu) nabu->enable();
      for (auto &s : this->slots_) { if (s.model) s.model->disable(); }
    } else if (opt == "All") {
      if (clemens) clemens->enable();
      if (nabu) nabu->enable();
      for (auto &s : this->slots_) { if (s.model) s.model->enable(); }
    } else {
      bool matched = false;
      for (auto &s : this->slots_) {
        if (s.name == opt) {
          if (clemens) clemens->disable();
          if (nabu) nabu->disable();
          for (auto &other : this->slots_) {
            if (other.model) {
              if (other.name == opt) other.model->enable();
              else other.model->disable();
            }
          }
          matched = true;
          break;
        }
      }
      if (!matched) {
        if (clemens) clemens->enable();
        if (nabu) nabu->enable();
        for (auto &s : this->slots_) { if (s.model) s.model->enable(); }
      }
    }
  }

 protected:
  std::vector<CustomWakeSlot> slots_;
  std::vector<std::string> custom_names_;
  std::vector<std::string> options_storage_;
};

inline WakePartitionLoader &get_wake_partition_loader() {
  return WakePartitionLoader::instance();
}

} // namespace wake_loader
} // namespace esphome
