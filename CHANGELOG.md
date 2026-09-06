# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/axiomantic/esphome-satellite/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/axiomantic/esphome-satellite/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/axiomantic/esphome-satellite/releases/tag/v0.1.0
