#pragma once

#include "esphome/core/log.h"
#include "esphome/core/helpers.h"
#include "esphome/components/micro_wake_word/micro_wake_word.h"
#include "esphome/components/select/select.h"
#include <esp_partition.h>
#include <esp_http_client.h>
#include <esp_https_ota.h>
#include <esp_crt_bundle.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
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

bool nim_wake_installer_pack_header(
    uint8_t *out_buf,
    size_t max_len,
    const char *name,
    uint32_t model_size,
    uint8_t cutoff,
    uint8_t window,
    uint16_t arena_kb
) __attribute__((weak));

bool nim_wake_installer_validate_tflite(const uint8_t *data, size_t len) __attribute__((weak));

bool nim_wake_installer_get_partition_name(int slot, char *out_buf, size_t max_len) __attribute__((weak));
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
    this->mww_ = mww;

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

  bool install_custom_wake_word_from_url(
      const std::string &url,
      int slot,
      const std::string &wake_word_name,
      int cutoff_input = 102,
      int window_input = 5
  ) {
    if (slot < 1 || slot > 3) {
      ESP_LOGE(TAG, "Invalid wake word slot %d (must be 1, 2, or 3)", slot);
      return false;
    }
    if (url.empty()) {
      ESP_LOGE(TAG, "Empty URL provided for custom wake word installation");
      return false;
    }

    uint8_t cutoff = (cutoff_input > 0 && cutoff_input <= 255) ? static_cast<uint8_t>(cutoff_input) : 102;
    uint8_t window = (window_input >= 2 && window_input <= 10) ? static_cast<uint8_t>(window_input) : 5;

    char part_name[16] = {0};
    if (nim_wake_installer_get_partition_name != nullptr) {
      if (!nim_wake_installer_get_partition_name(slot, part_name, sizeof(part_name))) {
        ESP_LOGE(TAG, "Failed to resolve partition name for slot %d", slot);
        return false;
      }
    } else {
      snprintf(part_name, sizeof(part_name), slot == 1 ? "wake_model" : (slot == 2 ? "wake_model_2" : "wake_model_3"));
    }

    const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, part_name);
    if (part == nullptr) {
      ESP_LOGE(TAG, "Target partition '%s' not found on flash", part_name);
      return false;
    }

    ESP_LOGI(TAG, "Connecting to %s to download wake word model for slot %d ('%s')...",
             url.c_str(), slot, part_name);

    esp_http_client_config_t config = {};
    config.url = url.c_str();
    config.timeout_ms = 15000;
    config.buffer_size = 2048;
    config.skip_cert_common_name_check = true;
    config.crt_bundle_attach = esp_crt_bundle_attach;
    config.max_redirection_count = 5;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == nullptr) {
      ESP_LOGE(TAG, "Failed to initialize HTTP client");
      return false;
    }

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Failed to open HTTP connection: %s", esp_err_to_name(err));
      esp_http_client_cleanup(client);
      return false;
    }

    esp_http_client_fetch_headers(client);
    int status_code = esp_http_client_get_status_code(client);
    if (status_code != 200) {
      ESP_LOGE(TAG, "HTTP server returned error status code: %d", status_code);
      esp_http_client_close(client);
      esp_http_client_cleanup(client);
      return false;
    }

    const size_t max_model_size = part->size - sizeof(WakeModelHeader);
    uint8_t *model_buf = static_cast<uint8_t *>(heap_caps_malloc(max_model_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (model_buf == nullptr) {
      model_buf = static_cast<uint8_t *>(malloc(max_model_size));
    }
    if (model_buf == nullptr) {
      ESP_LOGE(TAG, "Failed to allocate memory buffer (%zu bytes) for wake word download", max_model_size);
      esp_http_client_close(client);
      esp_http_client_cleanup(client);
      return false;
    }

    size_t total_read = 0;
    while (total_read < max_model_size) {
      int read_bytes = esp_http_client_read(client, reinterpret_cast<char *>(model_buf + total_read), max_model_size - total_read);
      if (read_bytes < 0) {
        ESP_LOGE(TAG, "Error reading HTTP stream: read_bytes=%d", read_bytes);
        free(model_buf);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
      }
      if (read_bytes == 0) {
        break; // EOF reached
      }
      total_read += read_bytes;
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    ESP_LOGI(TAG, "Downloaded %zu bytes. Validating TFLite model...", total_read);

    if (total_read < 1000) {
      ESP_LOGE(TAG, "Downloaded model too small (%zu bytes), minimum is 1000 bytes", total_read);
      free(model_buf);
      return false;
    }

    if (nim_wake_installer_validate_tflite != nullptr) {
      if (!nim_wake_installer_validate_tflite(model_buf, total_read)) {
        ESP_LOGE(TAG, "Model validation failed (invalid TFL3 flatbuffer header)");
        free(model_buf);
        return false;
      }
    }

    uint8_t header_buf[64] = {0};
    if (nim_wake_installer_pack_header != nullptr) {
      bool packed = nim_wake_installer_pack_header(
          header_buf,
          sizeof(header_buf),
          wake_word_name.c_str(),
          static_cast<uint32_t>(total_read),
          cutoff,
          window,
          40 // 40KB arena
      );
      if (!packed) {
        ESP_LOGE(TAG, "Failed to pack WakeModelHeader");
        free(model_buf);
        return false;
      }
    } else {
      WakeModelHeader *hdr = reinterpret_cast<WakeModelHeader *>(header_buf);
      hdr->magic = WAKE_MAGIC;
      hdr->header_version = 1;
      hdr->flags = 0;
      hdr->model_size = static_cast<uint32_t>(total_read);
      hdr->probability_cutoff = cutoff;
      hdr->sliding_window_size = window;
      hdr->tensor_arena_kb = 40;
      strncpy(hdr->wake_word, wake_word_name.c_str(), sizeof(hdr->wake_word) - 1);
    }

    // Stop microWakeWord inference before modifying flash to prevent Core 0 cache panics
    if (this->mww_ != nullptr) {
      ESP_LOGI(TAG, "Stopping microWakeWord inference before partition update...");
      this->mww_->stop();
    }

    // Release any active MMAP handle on the target partition before erase
    if (slot >= 1 && slot <= static_cast<int>(this->slots_.size())) {
      auto &s = this->slots_[slot - 1];
      if (s.map_handle != 0) {
        ESP_LOGI(TAG, "Unmapping active partition mmap handle for slot %d...", slot);
        esp_partition_munmap(s.map_handle);
        s.map_handle = 0;
        s.map_ptr = nullptr;
      }
    }

    ESP_LOGI(TAG, "Erasing flash partition '%s' (0x%06X, %u KB)...",
             part_name, (unsigned int)part->address, (unsigned int)(part->size / 1024));
    err = esp_partition_erase_range(part, 0, part->size);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Failed to erase partition: %s", esp_err_to_name(err));
      free(model_buf);
      return false;
    }

    ESP_LOGI(TAG, "Writing 64-byte WakeModelHeader to offset 0x0...");
    err = esp_partition_write(part, 0, header_buf, sizeof(header_buf));
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Failed to write header to partition: %s", esp_err_to_name(err));
      free(model_buf);
      return false;
    }

    ESP_LOGI(TAG, "Writing %zu bytes of TFLite model data to offset 0x%02X...",
             total_read, (unsigned int)sizeof(header_buf));
    err = esp_partition_write(part, sizeof(header_buf), model_buf, total_read);
    free(model_buf);

    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Failed to write model data to partition: %s", esp_err_to_name(err));
      return false;
    }

    ESP_LOGI(TAG, "Custom wake word '%s' successfully installed into slot %d ('%s')!",
             wake_word_name.c_str(), slot, part_name);
    return true;
  }

  bool remove_custom_wake_word(int slot) {
    if (slot < 1 || slot > 3) {
      ESP_LOGE(TAG, "Invalid wake word slot %d (must be 1, 2, or 3)", slot);
      return false;
    }
    char part_name[16] = {0};
    if (nim_wake_installer_get_partition_name != nullptr) {
      nim_wake_installer_get_partition_name(slot, part_name, sizeof(part_name));
    } else {
      snprintf(part_name, sizeof(part_name), slot == 1 ? "wake_model" : (slot == 2 ? "wake_model_2" : "wake_model_3"));
    }

    const esp_partition_t *part = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, part_name);
    if (part == nullptr) {
      ESP_LOGE(TAG, "Target partition '%s' not found on flash", part_name);
      return false;
    }

    // Stop microWakeWord inference before modifying flash to prevent Core 0 cache panics
    if (this->mww_ != nullptr) {
      ESP_LOGI(TAG, "Stopping microWakeWord inference before partition update...");
      this->mww_->stop();
    }

    // Release any active MMAP handle on the target partition before erase
    if (slot >= 1 && slot <= static_cast<int>(this->slots_.size())) {
      auto &s = this->slots_[slot - 1];
      if (s.map_handle != 0) {
        ESP_LOGI(TAG, "Unmapping active partition mmap handle for slot %d...", slot);
        esp_partition_munmap(s.map_handle);
        s.map_handle = 0;
        s.map_ptr = nullptr;
      }
    }

    ESP_LOGI(TAG, "Clearing custom wake word slot %d ('%s')...", slot, part_name);
    esp_err_t err = esp_partition_erase_range(part, 0, 4096);
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Failed to erase partition sector: %s", esp_err_to_name(err));
      return false;
    }

    ESP_LOGI(TAG, "Custom wake word slot %d cleared successfully", slot);
    return true;
  }

  bool flash_firmware_ota(const std::string &url) {
    if (url.empty()) {
      ESP_LOGE(TAG, "Firmware OTA URL is empty!");
      return false;
    }

    esp_http_client_config_t http_config = {};
    http_config.url = url.c_str();
    http_config.timeout_ms = 30000;
    http_config.buffer_size = 2048;
    http_config.buffer_size_tx = 1024;
    http_config.crt_bundle_attach = esp_crt_bundle_attach;
    http_config.skip_cert_common_name_check = true;
    http_config.max_redirection_count = 5;

    esp_https_ota_config_t ota_config = {};
    ota_config.http_config = &http_config;

    ESP_LOGI(TAG, "Starting firmware OTA flash from URL: %s", url.c_str());
    extern void nim_satellite_ota_start() __attribute__((weak));
    if (nim_satellite_ota_start != nullptr) nim_satellite_ota_start();

    // Stop microWakeWord inference before modifying flash to prevent Core 0 cache panics
    if (this->mww_ != nullptr) {
      ESP_LOGI(TAG, "Stopping microWakeWord inference before firmware update...");
      this->mww_->stop();
    }

    esp_err_t ret = esp_https_ota(&ota_config);
    if (ret == ESP_OK) {
      ESP_LOGI(TAG, "Firmware OTA update successful! Rebooting in 1s...");
      extern void nim_satellite_ota_end(bool ok) __attribute__((weak));
      if (nim_satellite_ota_end != nullptr) nim_satellite_ota_end(true);
      return true;
    } else {
      ESP_LOGE(TAG, "Firmware OTA update failed: %s", esp_err_to_name(ret));
      extern void nim_satellite_ota_end(bool ok) __attribute__((weak));
      if (nim_satellite_ota_end != nullptr) nim_satellite_ota_end(false);
      return false;
    }
  }

 protected:
  micro_wake_word::MicroWakeWord *mww_{nullptr};
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
