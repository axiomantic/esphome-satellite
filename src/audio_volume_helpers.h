#pragma once

namespace esphome {

inline float calculate_effective_voice_volume(float master_pct, float voice_pct, float slot_pct) {
  float v = (master_pct / 100.0f) * (voice_pct / 100.0f) * (slot_pct / 100.0f);
  if (v > 1.0f) return 1.0f;
  if (v < 0.0f) return 0.0f;
  return v;
}

inline float calculate_effective_sound_volume(float master_pct, float sound_pct) {
  float v = (master_pct / 100.0f) * (sound_pct / 100.0f);
  if (v > 1.0f) return 1.0f;
  if (v < 0.0f) return 0.0f;
  return v;
}

}  // namespace esphome
