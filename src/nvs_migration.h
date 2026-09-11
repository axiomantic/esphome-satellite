#pragma once

#include "esphome/core/preferences.h"
#include "esphome/core/log.h"
#include "esphome/components/number/number.h"
#include "esphome/components/select/select.h"
#include "esphome/components/switch/switch.h"

namespace esphome {

static const char *const NVS_MIG_TAG = "nvs_migration";

// Legacy v0.5.0 FNV-1a preference hashes computed from pre-v0.6.0 entity names
static const uint32_t HASH_LEGACY_VOICE_VOLUME = 1848069015UL;           // "Audio: Voice Volume"
static const uint32_t HASH_LEGACY_CANCEL_SOUND = 1728718513UL;           // "Audio: Cancel Sound Sound"
static const uint32_t HASH_LEGACY_WAKE_CHIME = 817734680UL;              // "Audio: Wake Chime Sound"
static const uint32_t HASH_LEGACY_PROCESSING_SOUND = 3079313095UL;        // "Audio: Processing Sound"
static const uint32_t HASH_LEGACY_SENSITIVITY = 4098752856UL;             // "Speech: Wake Word Sensitivity"
static const uint32_t HASH_LEGACY_WAKE_CHIME_SWITCH = 3930144138UL;       // "Audio: Wake Chime Enabled"
static const uint32_t HASH_LEGACY_CANCEL_SOUND_SWITCH = 483196759UL;       // "Audio: Cancel Sound Enabled"

extern "C" {
const char *nim_nvs_get_legacy_sensitivity(size_t idx) __attribute__((weak));
const char *nim_nvs_get_legacy_chime(size_t idx) __attribute__((weak));
const char *nim_nvs_get_legacy_proc(size_t idx) __attribute__((weak));
const char *nim_nvs_get_legacy_cancel(size_t idx) __attribute__((weak));
}

inline void migrate_legacy_nvs_preferences(
    number::Number *slot1_vol,
    select::Select *slot1_cancel,
    select::Select *slot1_chime,
    select::Select *slot1_proc,
    select::Select *slot1_sens,
    switch_::Switch *slot1_chime_sw,
    switch_::Switch *slot1_cancel_sw
) {
  if (global_preferences == nullptr) return;

  static const uint32_t NVS_MIGRATION_VERSION_KEY = 3847291045UL;
  auto mig_pref = global_preferences->make_preference<uint32_t>(NVS_MIGRATION_VERSION_KEY);
  uint32_t migrated = 0;
  if (mig_pref.load(&migrated) && migrated == 1) {
    return;
  }

  ESP_LOGI(NVS_MIG_TAG, "Running legacy v0.5.0 NVS preference migration check...");
  bool any_migrated = false;

  // 1. Audio: Voice Volume -> Slot 1 Volume
  if (slot1_vol != nullptr) {
    auto leg_pref = global_preferences->make_preference<float>(HASH_LEGACY_VOICE_VOLUME);
    float leg_val = 0.0f;
    if (leg_pref.load(&leg_val) && leg_val >= 0.0f && leg_val <= 100.0f) {
      ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Voice Volume: %.1f%%", leg_val);
      slot1_vol->make_call().set_value(leg_val).perform();
      any_migrated = true;
    }
  }

  // 2. Audio: Cancel Sound Sound -> Slot 1 Cancel Sound
  if (slot1_cancel != nullptr) {
    auto leg_pref = global_preferences->make_preference<size_t>(HASH_LEGACY_CANCEL_SOUND);
    size_t leg_idx = 0;
    if (leg_pref.load(&leg_idx)) {
      const char *opt = nim_nvs_get_legacy_cancel ? nim_nvs_get_legacy_cancel(leg_idx) : nullptr;
      if (opt != nullptr) {
        ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Cancel Sound: '%s' (idx %zu)", opt, leg_idx);
        slot1_cancel->make_call().set_option(opt).perform();
        any_migrated = true;
      }
    }
  }

  // 3. Audio: Wake Chime Sound -> Slot 1 Wake Chime
  if (slot1_chime != nullptr) {
    auto leg_pref = global_preferences->make_preference<size_t>(HASH_LEGACY_WAKE_CHIME);
    size_t leg_idx = 0;
    if (leg_pref.load(&leg_idx)) {
      const char *opt = nim_nvs_get_legacy_chime ? nim_nvs_get_legacy_chime(leg_idx) : nullptr;
      if (opt != nullptr) {
        ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Wake Chime: '%s' (idx %zu)", opt, leg_idx);
        slot1_chime->make_call().set_option(opt).perform();
        any_migrated = true;
      }
    }
  }

  // 4. Audio: Processing Sound -> Slot 1 Processing Sound
  if (slot1_proc != nullptr) {
    auto leg_pref = global_preferences->make_preference<size_t>(HASH_LEGACY_PROCESSING_SOUND);
    size_t leg_idx = 0;
    if (leg_pref.load(&leg_idx)) {
      const char *opt = nim_nvs_get_legacy_proc ? nim_nvs_get_legacy_proc(leg_idx) : nullptr;
      if (opt != nullptr) {
        ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Processing Sound: '%s' (idx %zu)", opt, leg_idx);
        slot1_proc->make_call().set_option(opt).perform();
        any_migrated = true;
      }
    }
  }

  // 5. Speech: Wake Word Sensitivity -> Slot 1 Sensitivity
  if (slot1_sens != nullptr) {
    auto leg_pref = global_preferences->make_preference<size_t>(HASH_LEGACY_SENSITIVITY);
    size_t leg_idx = 0;
    if (leg_pref.load(&leg_idx)) {
      const char *opt = nim_nvs_get_legacy_sensitivity ? nim_nvs_get_legacy_sensitivity(leg_idx) : nullptr;
      if (opt != nullptr) {
        ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Wake Word Sensitivity: '%s' (idx %zu)", opt, leg_idx);
        slot1_sens->make_call().set_option(opt).perform();
        any_migrated = true;
      }
    }
  }

  // 6. Audio: Wake Chime Enabled -> Slot 1 Wake Chime Switch
  if (slot1_chime_sw != nullptr) {
    auto leg_pref = global_preferences->make_preference<bool>(HASH_LEGACY_WAKE_CHIME_SWITCH);
    bool leg_sw = true;
    if (leg_pref.load(&leg_sw)) {
      ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Wake Chime Enabled: %d", leg_sw);
      if (leg_sw) slot1_chime_sw->turn_on(); else slot1_chime_sw->turn_off();
      any_migrated = true;
    }
  }

  // 7. Audio: Cancel Sound Enabled -> Slot 1 Cancel Sound Switch
  if (slot1_cancel_sw != nullptr) {
    auto leg_pref = global_preferences->make_preference<bool>(HASH_LEGACY_CANCEL_SOUND_SWITCH);
    bool leg_sw = true;
    if (leg_pref.load(&leg_sw)) {
      ESP_LOGI(NVS_MIG_TAG, "Migrating legacy Cancel Sound Enabled: %d", leg_sw);
      if (leg_sw) slot1_cancel_sw->turn_on(); else slot1_cancel_sw->turn_off();
      any_migrated = true;
    }
  }

  uint32_t done = 1;
  mig_pref.save(&done);
  global_preferences->sync();
  ESP_LOGI(NVS_MIG_TAG, "Legacy NVS preference migration finished (migrated=%s)", any_migrated ? "YES" : "NO");
}

}  // namespace esphome
