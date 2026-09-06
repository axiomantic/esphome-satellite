#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Core Voice Assistant Functions
void nim_satellite_wake_word(const char *word, int angle) __attribute__((weak));
void nim_satellite_chime_done(bool ok) __attribute__((weak));
void nim_satellite_speech_ended(void) __attribute__((weak));
void nim_satellite_silence_timeout(void) __attribute__((weak));
void nim_satellite_tts_start(void) __attribute__((weak));
void nim_satellite_tts_end(void) __attribute__((weak));
void nim_satellite_stop_word(void) __attribute__((weak));
void nim_satellite_error(const char *code) __attribute__((weak));
void nim_satellite_disconnected(void) __attribute__((weak));
void nim_satellite_connected(void) __attribute__((weak));
int nim_satellite_get_state(void) __attribute__((weak));

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

// Safe C++ inlined callers
inline void call_nim_wake_word(const char *word, int angle) {
  if (nim_satellite_wake_word) nim_satellite_wake_word(word, angle);
}
inline void call_nim_chime_done(bool ok) {
  if (nim_satellite_chime_done) nim_satellite_chime_done(ok);
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

inline void call_nim_action_test_audio(const char *style, float volume) {
  if (nim_action_test_audio) nim_action_test_audio(style, volume);
}
inline void call_nim_action_set_mute(bool muted) {
  if (nim_action_set_mute) nim_action_set_mute(muted);
}

#ifdef __cplusplus
}
#endif
