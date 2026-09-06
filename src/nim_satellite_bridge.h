#pragma once
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

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

#ifdef __cplusplus
}
#endif
