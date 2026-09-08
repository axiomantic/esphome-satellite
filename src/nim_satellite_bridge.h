#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Core Voice Assistant Functions
void nim_satellite_wake_word(const char *word, int angle) __attribute__((weak));
void nim_satellite_chime_done(bool ok) __attribute__((weak));
void nim_satellite_cancel_done(bool ok) __attribute__((weak));
void nim_satellite_speech_ended(void) __attribute__((weak));
void nim_satellite_silence_timeout(void) __attribute__((weak));
void nim_satellite_tts_start(void) __attribute__((weak));
void nim_satellite_tts_end(void) __attribute__((weak));
void nim_satellite_stop_word(void) __attribute__((weak));
void nim_satellite_error(const char *code) __attribute__((weak));
void nim_satellite_disconnected(void) __attribute__((weak));
void nim_satellite_connected(void) __attribute__((weak));
bool nim_satellite_is_cancellation(const char *text, const char *config) __attribute__((weak));
int nim_satellite_get_state(void) __attribute__((weak));
bool nim_satellite_is_cancelling(void) __attribute__((weak));

// Extended State Functions
void nim_satellite_set_muted(bool muted) __attribute__((weak));
void nim_satellite_follow_up(void) __attribute__((weak));
void nim_satellite_media_play(void) __attribute__((weak));
void nim_satellite_media_stop(void) __attribute__((weak));
void nim_satellite_alert_start(void) __attribute__((weak));
void nim_satellite_alert_stop(void) __attribute__((weak));
void nim_satellite_announcement_start(void) __attribute__((weak));
void nim_satellite_announcement_end(void) __attribute__((weak));
void nim_satellite_ota_start(void) __attribute__((weak));
void nim_satellite_ota_end(bool ok) __attribute__((weak));
bool nim_satellite_is_muted(void) __attribute__((weak));
bool nim_satellite_is_media_playing(void) __attribute__((weak));
bool nim_satellite_is_alerting(void) __attribute__((weak));

// Real-Time Audio DSP Hooks
void nim_audio_dsp_process(int16_t *samples, int count) __attribute__((weak));
void nim_audio_dsp_process32(int32_t *samples, int count) __attribute__((weak));

// Hardware & Animation Nim Hooks
void nim_xvf3800_make_gpo_payload(uint8_t pin, uint8_t val, uint8_t *outBuf) __attribute__((weak));
void nim_xvf3800_update_animation(const char *stateName, const char *patternPref, float brightness, uint32_t nowMs, uint32_t *outColors) __attribute__((weak));

// Partition Loader Nim Hooks
bool nim_wake_loader_validate_header(const uint8_t *data, uint32_t partSize, int slotIndex, uint32_t *outModelSize, uint8_t *outCutoff, size_t *outWindow, size_t *outArena, char *outName, size_t maxNameLen) __attribute__((weak));

// PCM Player Nim Hooks
bool nim_pcm_parse_wav(const uint8_t *data, size_t len, uint32_t *outSampleRate, uint16_t *outChannels, uint16_t *outBits, size_t *outPcmOffset, size_t *outPcmLen) __attribute__((weak));
size_t nim_pcm_decode_adpcm_chunk(const uint8_t *adpcmData, size_t adpcmLen, int16_t *outSamples, float volume, int16_t *valprev, int8_t *index) __attribute__((weak));

inline void call_nim_audio_dsp_process(int16_t *samples, int count) {
  if (nim_audio_dsp_process) nim_audio_dsp_process(samples, count);
}
inline void call_nim_audio_dsp_process32(int32_t *samples, int count) {
  if (nim_audio_dsp_process32) nim_audio_dsp_process32(samples, count);
}

// Safe C++ inlined callers
inline void call_nim_wake_word(const char *word, int angle) {
  if (nim_satellite_wake_word) nim_satellite_wake_word(word, angle);
}
inline void call_nim_chime_done(bool ok) {
  if (nim_satellite_chime_done) nim_satellite_chime_done(ok);
}
inline void call_nim_cancel_done(bool ok) {
  if (nim_satellite_cancel_done) nim_satellite_cancel_done(ok);
}
inline bool call_nim_is_cancelling(void) {
  if (nim_satellite_is_cancelling) return nim_satellite_is_cancelling();
  return false;
}
inline void call_nim_speech_ended(void) {
  if (nim_satellite_speech_ended) nim_satellite_speech_ended();
}
inline void call_nim_tts_start(void) {
  if (nim_satellite_tts_start) nim_satellite_tts_start();
}
inline void call_nim_tts_end(void) {
  if (nim_satellite_tts_end) nim_satellite_tts_end();
}
inline void call_nim_stop_word(void) {
  if (nim_satellite_stop_word) nim_satellite_stop_word();
}
inline void call_nim_error(const char *code) {
  if (nim_satellite_error) nim_satellite_error(code);
}
inline void call_nim_connected(void) {
  if (nim_satellite_connected) nim_satellite_connected();
}
inline void call_nim_disconnected(void) {
  if (nim_satellite_disconnected) nim_satellite_disconnected();
}
inline bool call_nim_is_cancellation(const char *text, const char *config = nullptr) {
  if (nim_satellite_is_cancellation) return nim_satellite_is_cancellation(text, config);
  return false;
}
inline void call_nim_set_muted(bool muted) {
  if (nim_satellite_set_muted) nim_satellite_set_muted(muted);
}
inline void call_nim_follow_up(void) {
  if (nim_satellite_follow_up) nim_satellite_follow_up();
}
inline void call_nim_media_play(void) {
  if (nim_satellite_media_play) nim_satellite_media_play();
}
inline void call_nim_media_stop(void) {
  if (nim_satellite_media_stop) nim_satellite_media_stop();
}
inline void call_nim_alert_start(void) {
  if (nim_satellite_alert_start) nim_satellite_alert_start();
}
inline void call_nim_alert_stop(void) {
  if (nim_satellite_alert_stop) nim_satellite_alert_stop();
}
inline void call_nim_announcement_start(void) {
  if (nim_satellite_announcement_start) nim_satellite_announcement_start();
}
inline void call_nim_announcement_end(void) {
  if (nim_satellite_announcement_end) nim_satellite_announcement_end();
}
inline void call_nim_ota_start(void) {
  if (nim_satellite_ota_start) nim_satellite_ota_start();
}
inline void call_nim_ota_end(bool ok) {
  if (nim_satellite_ota_end) nim_satellite_ota_end(ok);
}

// Home Assistant Actions Bridge
void nim_action_test_audio(const char *style, float volume) __attribute__((weak));
void nim_action_set_mute(bool muted) __attribute__((weak));
void nim_action_set_processing_sound(const char *sound) __attribute__((weak));
void nim_action_set_processing_volume(float volume) __attribute__((weak));
void nim_action_set_chime_sound(const char *sound) __attribute__((weak));
void nim_action_set_chime_volume(float volume) __attribute__((weak));

inline void call_nim_action_test_audio(const char *style, float volume) {
  if (nim_action_test_audio) nim_action_test_audio(style, volume);
}
inline void call_nim_action_set_mute(bool muted) {
  if (nim_action_set_mute) nim_action_set_mute(muted);
}
inline void call_nim_action_set_processing_sound(const char *sound) {
  if (nim_action_set_processing_sound) nim_action_set_processing_sound(sound);
}
inline void call_nim_action_set_processing_volume(float volume) {
  if (nim_action_set_processing_volume) nim_action_set_processing_volume(volume);
}
inline void call_nim_action_set_chime_sound(const char *sound) {
  if (nim_action_set_chime_sound) nim_action_set_chime_sound(sound);
}
inline void call_nim_action_set_chime_volume(float volume) {
  if (nim_action_set_chime_volume) nim_action_set_chime_volume(volume);
}

inline const char* get_satellite_state_name() {
  int s = nim_satellite_get_state ? nim_satellite_get_state() : 0;
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

