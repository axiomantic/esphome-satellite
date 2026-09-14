#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Core Voice Assistant Functions
void nim_satellite_wake_word(const char *word, int angle);
void nim_satellite_chime_done(bool ok);
void nim_satellite_cancel_done(bool ok);
void nim_satellite_speech_ended(void);
void nim_satellite_silence_timeout(void);
void nim_satellite_tts_start(void);
void nim_satellite_tts_end(void);
void nim_satellite_stop_word(void);
void nim_satellite_error(const char *code);
void nim_satellite_disconnected(void);
void nim_satellite_connected(void);
bool nim_satellite_is_cancellation(const char *text, const char *config);
bool nim_satellite_is_reset_phrase(const char *text);
int nim_satellite_get_state(void);
bool nim_satellite_is_cancelling(void);

// Extended State Functions
void nim_satellite_set_muted(bool muted);
void nim_satellite_follow_up(void);
void nim_satellite_media_play(void);
void nim_satellite_media_stop(void);
void nim_satellite_alert_start(void);
void nim_satellite_alert_stop(void);
void nim_satellite_announcement_start(void);
void nim_satellite_announcement_end(void);
void nim_satellite_ota_start(void);
void nim_satellite_ota_end(bool ok);
void nim_satellite_restart(void);
bool nim_satellite_is_muted(void);
bool nim_satellite_is_media_playing(void);
bool nim_satellite_is_alerting(void);

// Real-Time Audio DSP Hooks
void nim_audio_dsp_process(int16_t *samples, int count);
void nim_audio_dsp_process32(int32_t *samples, int count);
void nim_audio_dsp_set_mic_pre_gain(float db);
void nim_audio_dsp_apply_mic_pre_gain32(int32_t *samples, int count);

// Hardware & Animation Nim Hooks
void nim_xvf3800_make_gpo_payload(uint8_t pin, uint8_t val, uint8_t *outBuf);
void nim_xvf3800_update_animation(const char *stateName, const char *patternPref, float brightness, uint32_t nowMs, uint32_t *outColors);

// Partition Loader Nim Hooks
bool nim_wake_loader_validate_header(const uint8_t *data, uint32_t partSize, int slotIndex, uint32_t *outModelSize, uint8_t *outCutoff, size_t *outWindow, size_t *outArena, char *outName, size_t maxNameLen);

// PCM Player Nim Hooks
bool nim_pcm_parse_wav(const uint8_t *data, size_t len, uint32_t *outSampleRate, uint16_t *outChannels, uint16_t *outBits, size_t *outPcmOffset, size_t *outPcmLen);
size_t nim_pcm_decode_adpcm_chunk(const uint8_t *adpcmData, size_t adpcmLen, int16_t *outSamples, float volume, int16_t *valprev, int8_t *index);

// DMA Audio Stream Typestate Tracker Nim Hooks
bool nim_dma_stream_start(int kind, uint32_t max_duration_ms, uint32_t inactivity_timeout_ms, bool is_loop);
void nim_dma_stream_feed(size_t bytes);
void nim_dma_stream_finish(void);
void nim_dma_stream_abort(void);
int nim_dma_stream_tick(uint32_t now_ms);
bool nim_dma_stream_is_active(void);
int nim_dma_stream_get_kind(void);
uint32_t nim_dma_stream_get_elapsed_ms(uint32_t now_ms);

inline bool call_nim_dma_stream_start(int kind, uint32_t max_duration_ms, uint32_t inactivity_timeout_ms, bool is_loop) {
  return nim_dma_stream_start(kind, max_duration_ms, inactivity_timeout_ms, is_loop);
}
inline void call_nim_dma_stream_feed(size_t bytes) {
  nim_dma_stream_feed(bytes);
}
inline void call_nim_dma_stream_finish(void) {
  nim_dma_stream_finish();
}
inline void call_nim_dma_stream_abort(void) {
  nim_dma_stream_abort();
}
inline int call_nim_dma_stream_tick(uint32_t now_ms) {
  return nim_dma_stream_tick(now_ms);
}
inline bool call_nim_dma_stream_is_active(void) {
  return nim_dma_stream_is_active();
}
inline int call_nim_dma_stream_get_kind(void) {
  return nim_dma_stream_get_kind();
}
inline uint32_t call_nim_dma_stream_get_elapsed_ms(uint32_t now_ms) {
  return nim_dma_stream_get_elapsed_ms(now_ms);
}

inline void call_nim_audio_dsp_process(int16_t *samples, int count) {
  nim_audio_dsp_process(samples, count);
}
inline void call_nim_audio_dsp_process32(int32_t *samples, int count) {
  nim_audio_dsp_process32(samples, count);
}
inline void call_nim_audio_dsp_set_mic_pre_gain(float db) {
  nim_audio_dsp_set_mic_pre_gain(db);
}
inline void call_nim_audio_dsp_apply_mic_pre_gain32(int32_t *samples, int count) {
  nim_audio_dsp_apply_mic_pre_gain32(samples, count);
}

// Safe C++ inlined callers
inline void call_nim_wake_word(const char *word, int angle) {
  nim_satellite_wake_word(word, angle);
}
inline void call_nim_chime_done(bool ok) {
  nim_satellite_chime_done(ok);
}
inline void call_nim_cancel_done(bool ok) {
  nim_satellite_cancel_done(ok);
}
inline bool call_nim_is_cancelling(void) {
  return nim_satellite_is_cancelling();
}
inline void call_nim_speech_ended(void) {
  nim_satellite_speech_ended();
}
inline void call_nim_tts_start(void) {
  nim_satellite_tts_start();
}
inline void call_nim_tts_end(void) {
  nim_satellite_tts_end();
}
inline void call_nim_stop_word(void) {
  nim_satellite_stop_word();
}
inline void call_nim_error(const char *code) {
  nim_satellite_error(code);
}
inline void call_nim_connected(void) {
  nim_satellite_connected();
}
inline void call_nim_disconnected(void) {
  nim_satellite_disconnected();
}
inline bool call_nim_is_cancellation(const char *text, const char *config = nullptr) {
  return nim_satellite_is_cancellation(text, config);
}
inline bool call_nim_is_reset_phrase(const char *text) {
  return nim_satellite_is_reset_phrase(text);
}
inline void call_nim_set_muted(bool muted) {
  nim_satellite_set_muted(muted);
}
inline void call_nim_follow_up(void) {
  nim_satellite_follow_up();
}
inline void call_nim_media_play(void) {
  nim_satellite_media_play();
}
inline void call_nim_media_stop(void) {
  nim_satellite_media_stop();
}
inline void call_nim_alert_start(void) {
  nim_satellite_alert_start();
}
inline void call_nim_alert_stop(void) {
  nim_satellite_alert_stop();
}
inline void call_nim_announcement_start(void) {
  nim_satellite_announcement_start();
}
inline void call_nim_announcement_end(void) {
  nim_satellite_announcement_end();
}
inline void call_nim_ota_start(void) {
  nim_satellite_ota_start();
}
inline void call_nim_ota_end(bool ok) {
  nim_satellite_ota_end(ok);
}
inline void call_nim_restart(void) {
  nim_satellite_restart();
}
inline void call_nim_sync_preferences(void) {
  if (global_preferences != nullptr) {
    global_preferences->sync();
  }
}

// Home Assistant Actions Bridge
void nim_action_test_audio(const char *style, float volume);
void nim_action_set_mute(bool muted);
void nim_action_set_processing_sound(const char *sound);
void nim_action_set_processing_volume(float volume);
void nim_action_set_chime_sound(const char *sound);
void nim_action_set_chime_volume(float volume);

inline void call_nim_action_test_audio(const char *style, float volume) {
  nim_action_test_audio(style, volume);
}
inline void call_nim_action_set_mute(bool muted) {
  nim_action_set_mute(muted);
}
inline void call_nim_action_set_processing_sound(const char *sound) {
  nim_action_set_processing_sound(sound);
}
inline void call_nim_action_set_processing_volume(float volume) {
  nim_action_set_processing_volume(volume);
}
inline void call_nim_action_set_chime_sound(const char *sound) {
  nim_action_set_chime_sound(sound);
}
inline void call_nim_action_set_chime_volume(float volume) {
  nim_action_set_chime_volume(volume);
}

inline const char* get_satellite_state_name() {
  int s = nim_satellite_get_state();
  switch (s) {
    case 0: return "Idle";
    case 1: return "Woken";
    case 2: return "Listening";
    case 3: return "Thinking";
    case 4: return "Replying";
    case 5: return "Dismissed";
    case 6: return "Pipeline Error";
    case 7: return "Connection Error";
    case 8: return "Muted";
    case 9: return "Follow Up";
    case 10: return "Playing Media";
    case 11: return "Alerting";
    case 12: return "Announcing";
    case 13: return "Updating";
    case 14: return "Cancelling";
    default: return "Unknown";
  }
}

#ifdef __cplusplus
} // extern "C"

#ifdef USE_VOICE_ASSISTANT
#include "esphome/components/voice_assistant/voice_assistant.h"

namespace esphome {
namespace voice_assistant {

template<typename Tag, typename Tag::type M>
struct MemberRobber {
  friend typename Tag::type get_member(Tag) {
    return M;
  }
};

struct VoiceAssistantContinueConversationTag {
  typedef bool VoiceAssistant::*type;
  friend type get_member(VoiceAssistantContinueConversationTag);
};
template struct MemberRobber<VoiceAssistantContinueConversationTag, &VoiceAssistant::continue_conversation_>;

class VoiceAssistantAccessor {
 public:
  static bool is_continuing(const VoiceAssistant *va) {
    if (!va) return false;
    return (va->*get_member(VoiceAssistantContinueConversationTag{})) || va->is_continuous();
  }
};

} // namespace voice_assistant
} // namespace esphome
#endif

#include <string>
#include <cstring>

inline const char* get_chime_rtttl(const std::string &sound) {
  if (sound == "Modern Chime") {
    return "modern:d=16,o=5,b=200:e,g,b,e6";
  } else if (sound == "Crystal Glass") {
    return "crystal:d=32,o=6,b=200:e,b,e7";
  } else if (sound == "Warm Kalimba") {
    return "kalimba:d=16,o=5,b=160:c,g,c6";
  } else if (sound == "Meditation Bell") {
    return "meditate:d=8,o=4,b=100:g,c5,e5";
  } else if (sound == "Marimba") {
    return "marimba:d=16,o=5,b=200:c,e,g";
  } else if (sound == "Subtle Beep") {
    return "subtle:d=32,o=5,b=240:e";
  } else if (sound == "Silent") {
    return "";
  } else {
    // "Bell Ping" or fallback
    return "bell:d=16,o=6,b=180:c,g";
  }
}

inline const char* get_processing_rtttl(const std::string &style) {
  if (style == "Pulse") {
    return "pulse:d=16,o=4,b=120:c,p,c,8p";
  } else if (style == "Sonar") {
    return "sonar:d=16,o=6,b=100:g,8p,4p";
  } else if (style == "Tick") {
    return "tick:d=32,o=6,b=160:c,8p,16p";
  } else if (style == "Typewriter") {
    return "typewriter:d=32,o=5,b=220:c,e,d,g,e";
  } else if (style == "Clockwork") {
    return "clockwork:d=16,o=5,b=140:c,d,c,d";
  } else if (style == "Water Droplets") {
    return "droplets:d=32,o=6,b=160:c,8p,g,8p,e7,8p";
  } else if (style == "Silent") {
    return "";
  } else {
    // "Spinner" or fallback
    return "spinner:d=16,o=5,b=200:c,e,g,c6,g,e";
  }
}
#endif

