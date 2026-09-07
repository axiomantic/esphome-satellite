# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Rich sound preset library featuring Modern Minimalist (`Modern Chime`, `Crystal Glass`, `Clockwork`) and Organic Acoustic (`Warm Kalimba`, `Meditation Bell`, `Water Droplets`, and vintage `Typewriter`) options for wake chimes and processing sound feedback loops.
- Dedicated partition flashing support for preset wake chimes (`chime_data` at `0x390000`) and processing sounds (`sound_data` at `0x370000`) in ESP-Web-Tools web installer.
- Runtime template entity support in ESPHome YAML for `select.wake_chime_sound` and `select.processing_sound` with new audio presets.

## [0.4.0] - 2026-09-06

### Added
- Multi-slot wake word web installer supporting up to 3 concurrent microWakeWord models flashed to dedicated partitions (`0x3B0000`, `0x3F0000`, `0x430000`).
- Integrated client-side in-browser wake word neural network trainer with acoustic feature synthesis, live epoch/loss/accuracy metrics, and `.tflite` model export.
- Wake chime selector (`Bell Ping`, `Modern Chime`, `Marimba`, `Subtle Beep`, `Silent`, `Custom Chime Audio`) with live Web Audio API previews and custom chime partition flashing (`chime_data` at `0x390000`).
- Firmware installation readiness gating with warning alerts preventing flashing while training or before required models are uploaded.
- Firmware `select.wake_chime_sound` template entity and YAML package substitution for runtime chime configuration.

## [0.3.1] - 2026-09-06

### Fixed
- Audio resampling tests and context assertions in test runner.

## [0.3.0] - 2026-09-06

### Added
- ESP-Web-Tools web installer interface with dynamic manifest generation and custom audio flash support.

## [0.2.0] - 2026-09-06

### Added
- 6 extended satellite lifecycle states:
  - `Muted`: Privacy switch / mute state that cleanly ignores wake-word events and blocks microphone capture.
  - `FollowUp`: Continuous conversation mode keeping the session open for multi-turn dialogue without repeating the wake word.
  - `PlayingMedia`: Media playback state with audio ducking support upon wake-word trigger.
  - `Alerting`: Active timer/alarm ringing with dedicated dismissal transitions.
  - `Announcing`: Server push broadcast handling for TTS notifications.
  - `Updating`: Over-The-Air (OTA) firmware update protection blocking interrupts during flash writes.
- Compile-time invariant test suite enforcing that illegal transitions (e.g. waking while Muted, Updating, or in ConnectionError) fail at compile time.
- Automated release workflow in GitHub Actions triggered on version bumps in `esphome_satellite.nimble`.

### Changed
- Renamed package and repository to `esphome-satellite` for clean, discoverable integration with ESPHome.
- Updated minimum `nim_esphome` requirement to `>= 0.2.0`.
- Standardized test suites to use generic wake words (`hey assistant`, `assistant`).
- Reframed project description and documentation around its core value as an on-device state supervisor eliminating audio glitches and race conditions.

## [0.1.0] - 2026-09-06

### Added
- Initial release of compile-time verified voice satellite state machine for ESPHome.
- Core conversational state machine (`Idle`, `Woken`, `Listening`, `Thinking`, `Replying`) using `nim-typestates`.
- Interrupt handling for stop words during listening, thinking, and replying.
- Granular error recovery transitions (`SilentDismiss`, `PipelineError`, `ConnectionError`).
- High-performance zero-copy C ABI bridge (`nim_satellite_bridge.h`) and drop-in ESPHome YAML package.

[Unreleased]: https://github.com/axiomantic/esphome-satellite/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/axiomantic/esphome-satellite/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/axiomantic/esphome-satellite/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/axiomantic/esphome-satellite/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/axiomantic/esphome-satellite/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/axiomantic/esphome-satellite/releases/tag/v0.1.0
