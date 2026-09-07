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
  uint8_t  reserved[20];          // Padding to 64 bytes
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

    const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, "wake_model");

    if (part == nullptr) {
      ESP_LOGW(TAG, "No 'wake_model' partition found in partition table");
      return;
    }

    ESP_LOGI(TAG, "Found 'wake_model' partition at offset 0x%06X (size %u KB)",
             (unsigned int)part->address, (unsigned int)(part->size / 1024));

    esp_err_t err = esp_partition_mmap(part, 0, part->size, ESP_PARTITION_MMAP_DATA, &this->map_ptr_, &this->map_handle_);
    if (err != ESP_OK || this->map_ptr_ == nullptr) {
      ESP_LOGE(TAG, "Failed to memory-map wake_model partition: err=0x%X", err);
      return;
    }

    const WakeModelHeader *header = reinterpret_cast<const WakeModelHeader *>(this->map_ptr_);
    if (header->magic != WAKE_MAGIC) {
      ESP_LOGI(TAG, "No custom wake word model installed (magic: 0x%08X). Using built-in models.", (unsigned int)header->magic);
      return;
    }

    if (header->model_size < 1000 || header->model_size > (part->size - sizeof(WakeModelHeader))) {
      ESP_LOGW(TAG, "Invalid model size in wake_model header: %u bytes", (unsigned int)header->model_size);
      return;
    }

    // Safely extract wake word name
    char name_buf[33] = {0};
    memcpy(name_buf, header->wake_word, 32);
    name_buf[32] = '\0';
    if (name_buf[0] == '\0') {
      strcpy(name_buf, "Custom Wake Word");
    }
    this->custom_name_ = std::string(name_buf);

    const uint8_t *model_data = reinterpret_cast<const uint8_t *>(this->map_ptr_) + sizeof(WakeModelHeader);
    uint8_t cutoff = header->probability_cutoff > 0 ? header->probability_cutoff : 102; // default 0.40 (102/255)
    size_t window = header->sliding_window_size > 0 ? header->sliding_window_size : 5;
    size_t arena_size = header->tensor_arena_kb > 0 ? (header->tensor_arena_kb * 1024) : 40960;

    ESP_LOGI(TAG, "Registering custom wake word: '%s' (%u bytes, cutoff=%u, arena=%u)",
             this->custom_name_.c_str(), (unsigned int)header->model_size, cutoff, (unsigned int)arena_size);

    this->custom_model_ = new micro_wake_word::WakeWordModel(
        "custom_model",
        model_data,
        cutoff,
        window,
        this->custom_name_,
        arena_size,
        true,   // default_enabled
        false   // internal_only
    );

    mww->add_wake_word_model(this->custom_model_);
    this->has_custom_model_ = true;

    if (active_select != nullptr) {
      this->options_storage_ = {"Mr. Clemens", "Okay Nabu", this->custom_name_, "All"};
      FixedVector<const char *> fixed_opts;
      fixed_opts.init(this->options_storage_.size());
      for (const auto &opt : this->options_storage_) {
        fixed_opts.push_back(opt.c_str());
      }
      active_select->traits.set_options(fixed_opts);
      ESP_LOGI(TAG, "Updated Active Wake Word select options with '%s'", this->custom_name_.c_str());
    }
  }

  bool has_custom_model() const { return this->has_custom_model_; }
  const std::string &custom_name() const { return this->custom_name_; }
  micro_wake_word::WakeWordModel *model() const { return this->custom_model_; }

  void handle_active_wake_word_change(const std::string &opt, micro_wake_word::WakeWordModel *clemens, micro_wake_word::WakeWordModel *nabu) {
    ESP_LOGI(TAG, "Active wake word option changed to: '%s'", opt.c_str());
    if (opt == "Mr. Clemens") {
      if (clemens) clemens->enable();
      if (nabu) nabu->disable();
      if (this->custom_model_) this->custom_model_->disable();
    } else if (opt == "Okay Nabu") {
      if (clemens) clemens->disable();
      if (nabu) nabu->enable();
      if (this->custom_model_) this->custom_model_->disable();
    } else if (this->has_custom_model_ && opt == this->custom_name_) {
      if (clemens) clemens->disable();
      if (nabu) nabu->disable();
      if (this->custom_model_) this->custom_model_->enable();
    } else {
      // "All" or unrecognized option
      if (clemens) clemens->enable();
      if (nabu) nabu->enable();
      if (this->custom_model_) this->custom_model_->enable();
    }
  }

 protected:
  bool has_custom_model_{false};
  std::string custom_name_{""};
  micro_wake_word::WakeWordModel *custom_model_{nullptr};
  const void *map_ptr_{nullptr};
  esp_partition_mmap_handle_t map_handle_{0};
  std::vector<std::string> options_storage_;
};

inline WakePartitionLoader &get_wake_partition_loader() {
  return WakePartitionLoader::instance();
}

} // namespace wake_loader
} // namespace esphome
