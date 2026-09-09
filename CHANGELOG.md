# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-09-09

### Added
- Independent Assistant Profiles: Multi-slot runtime architecture enabling discrete audio, volume, and wake word configurations for Assistant Slot 1 and Assistant Slot 2 directly in Home Assistant.
- Dynamic Acoustic Equalization: Added `Extreme sensitivity` tier (0.45x cutoff scaling), runtime dynamic `Speech: Wake Window Size` configuration (2-5 frames), and runtime dynamic `Speech: Mic Pre-Gain Boost` slider (0-12 dB) to improve detection for quieter and higher-pitched vocal ranges.
- Synthetic Wake Word Corpus Generator & Trainer: Added `scripts/generate_wakeword_corpus.py` supporting ElevenLabs API (cloud neural synthesis and Instant Voice Cloning), local macOS `say` system voices, and F5-TTS zero-shot flow-matching synthesis. Features demographic voice balancing, combinatorial phonetic variations, and additive multi-voice composition.
- Web Installer microWakeWord Integration: Added guidance callout and README links on the web flashing page to assist users in generating and training custom wake word models.
- Discrete Partition Flashing: Preserved NVS settings, Wi-Fi credentials, and Home Assistant entity states across web flasher firmware updates.

### Changed
- Route wake-word triggering through the active assistant slot profile, ensuring independent sound and volume settings apply per assistant.
- Guaranteed Slot 1 precedence when both assistant slots share the same wake phrase.
- Reset conversation button (`Speech: Reset Conversation History`) now immediately aborts in-flight voice assistant pipelines and halts active sound playback.
- Synchronized watchdog and connection timeout cancel playback to eliminate race conditions between cancel audio output and microphone capture.

## [0.5.0] - 2026-09-08

### Added
- Explicit `Cancelling` typestate in Nim state supervisor (`SatelliteFSM`) preventing wake word or VAD re-triggering while cancel chime plays.
- Bounded audio hardware and network watchdog timeouts across all states (`Woken`: 2s, `Listening`: 10s, `Thinking`: 20s, `Replying`: 60s, `Cancelling`: 1.5s, `FollowUp`: 5s, `Alerting`: 5m, `Announcing`: 30s, `Updating`: 5m) preventing stuck states.
- Dedicated `set_on_cancel_finished` callback in `PcmSoundPlayer` ensuring clean wake word re-arming only after cancel audio completes.
- Native Nim cancellation phrase matcher detecting voice assistant abort intents ("stop", "nevermind", "never mind", "abort", "cancel", "dismiss", "quit", "silence", "quiet", "shut up") with punctuation stripping and whole-word boundary awareness.
- Sound playback guard preserving cancel sound audio from being cut off early by voice assistant teardown events.
- Rich sound preset library featuring Modern Minimalist (`Modern Chime`, `Crystal Glass`, `Clockwork`) and Organic Acoustic (`Warm Kalimba`, `Meditation Bell`, `Water Droplets`, and vintage `Typewriter`) options for wake chimes and processing sound feedback loops.
- Dedicated partition flashing support for preset wake chimes (`chime_data` at `0x390000`) and processing sounds (`sound_data` at `0x370000`) in ESP-Web-Tools web installer.
- Runtime template entity support in ESPHome YAML for `select.wake_chime_sound` and `select.processing_sound` with new audio presets.
- In-browser **Erase Device (Factory Reset)** button powered by WebSerial and `esptool-js` to wipe flash memory, cached Wi-Fi credentials, and NVS partitions before flashing.
- Persistent **Next Steps: Connecting to Home Assistant** guide on the installer page and interactive post-installation success modal with direct Home Assistant linking.

### Changed
- Replaced `Warm Kalimba` wake chime and cancel sound with authentic, resonant steel-tine Hokema Sansula acoustic recordings under CC0 1.0 Universal license.
- Replaced arbitrary YAML delays with event-driven playback completion and typestate transitions.

### Removed
- Orphaned `@esphome-satellite/trainer` experimental in-browser trainer subproject and obsolete TypeScript CI job.
- Redundant `scripts/build.sh` script in favor of comprehensive `scripts/test.sh` runner.

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
