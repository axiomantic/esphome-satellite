# @esphome-satellite/trainer

In-browser WASM and WebGPU wake word training and phonetic normalization library for `esphome-satellite`.

## Overview

This subproject provides client-side tooling for voice satellites running ESPHome and microWakeWord on ESP32-S3 hardware:

- **Phonetic Normalization**: Expands abbreviations, numbers, and technical shorthand into acoustic phonemes for optimal speech recognition (e.g., `ok c3p0` &rarr; `okay see three pee oh`, `dj pj` &rarr; `dee jay pee jay`).
- **Audio Processing**: Decodes 16-bit PCM WAV audio, resamples to 16 kHz mono, and extracts 40-bin log spectral energy feature frames.
- **Neural Network Training**: MicroWakeWord-compatible streaming convolutional model with WebGPU acceleration and CPU/WASM execution fallback.
- **TFLite Micro Model Packager**: Formats trained weights and layer parameters into a deployable `.tflite` FlatBuffer with `TFL3` file identifier for direct flashing to ESP32-S3 flash partitions.

## Phonetic Spelling Recommendations

For optimal acoustic feature detection, custom wake words should be spelled out phonetically:
- `ok c3p0` &rarr; `okay see three pee oh`
- `dj pj` &rarr; `dee jay pee jay`
- `ai tv` &rarr; `ay eye tee vee`
- Numbers should be written as spoken words (`42` &rarr; `four two`)

## Development & Testing

```bash
# Install dependencies
npm install

# Type check
npm run typecheck

# Run test suite
npm test

# Build distribution bundle
npm run build
```
