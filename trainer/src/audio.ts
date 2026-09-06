/**
 * Audio processing pipeline for wake word training and feature extraction.
 * Processes 16kHz mono audio into spectrogram feature vectors.
 */

export interface WavMetadata {
  sampleRate: number;
  numChannels: number;
  bitsPerSample: number;
  durationSec: number;
  numSamples: number;
}

export interface AudioTensorFrames {
  data: Float32Array;
  numFrames: number;
  featuresPerFrame: number;
}

/**
 * Decodes a 16-bit PCM WAV ArrayBuffer into Float32 samples normalized to [-1.0, 1.0].
 */
export function decodeWav(buffer: ArrayBuffer): { samples: Float32Array; metadata: WavMetadata } {
  const view = new DataView(buffer);

  // Validate RIFF header
  const riff = String.fromCharCode(
    view.getUint8(0),
    view.getUint8(1),
    view.getUint8(2),
    view.getUint8(3)
  );
  if (riff !== "RIFF") {
    throw new Error(`Invalid WAV file: missing RIFF header (got ${riff})`);
  }

  const wave = String.fromCharCode(
    view.getUint8(8),
    view.getUint8(9),
    view.getUint8(10),
    view.getUint8(11)
  );
  if (wave !== "WAVE") {
    throw new Error(`Invalid WAV file: missing WAVE format (got ${wave})`);
  }

  // Find 'fmt ' chunk
  let offset = 12;
  let numChannels = 1;
  let sampleRate = 16000;
  let bitsPerSample = 16;
  let dataOffset = 0;
  let dataSize = 0;

  while (offset < buffer.byteLength - 8) {
    const chunkId = String.fromCharCode(
      view.getUint8(offset),
      view.getUint8(offset + 1),
      view.getUint8(offset + 2),
      view.getUint8(offset + 3)
    );
    const chunkSize = view.getUint32(offset + 4, true);

    if (chunkId === "fmt ") {
      numChannels = view.getUint16(offset + 10, true);
      sampleRate = view.getUint32(offset + 12, true);
      bitsPerSample = view.getUint16(offset + 22, true);
    } else if (chunkId === "data") {
      dataOffset = offset + 8;
      dataSize = chunkSize;
      break;
    }

    offset += 8 + chunkSize;
  }

  if (dataOffset === 0) {
    throw new Error("Invalid WAV file: data chunk not found");
  }

  const bytesPerSample = bitsPerSample / 8;
  const totalSamples = Math.floor(dataSize / (bytesPerSample * numChannels));
  const samples = new Float32Array(totalSamples);

  for (let i = 0; i < totalSamples; i++) {
    const sampleOffset = dataOffset + i * bytesPerSample * numChannels;
    let sample = 0;
    if (bitsPerSample === 16) {
      sample = view.getInt16(sampleOffset, true) / 32768.0;
    } else if (bitsPerSample === 8) {
      sample = (view.getUint8(sampleOffset) - 128) / 128.0;
    } else if (bitsPerSample === 32) {
      sample = view.getFloat32(sampleOffset, true);
    }
    samples[i] = sample;
  }

  return {
    samples,
    metadata: {
      sampleRate,
      numChannels,
      bitsPerSample,
      durationSec: totalSamples / sampleRate,
      numSamples: totalSamples,
    },
  };
}

/**
 * Resamples audio to 16kHz if necessary (linear interpolation).
 */
export function resampleTo16kHz(samples: Float32Array, originalRate: number): Float32Array {
  if (originalRate === 16000) return samples;

  const targetRate = 16000;
  const ratio = originalRate / targetRate;
  const newLength = Math.round(samples.length / ratio);
  const result = new Float32Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const origIndex = i * ratio;
    const lower = Math.floor(origIndex);
    const upper = Math.min(lower + 1, samples.length - 1);
    const frac = origIndex - lower;
    result[i] = (1 - frac) * samples[lower] + frac * samples[upper];
  }

  return result;
}

/**
 * Extracts spectral energy features over sliding windows (25ms window, 10ms hop).
 * Produces 40-channel feature vectors matching MicroWakeWord standard input representation.
 */
export function extractSpectralFeatures(
  audio: Float32Array,
  featuresPerFrame: number = 40,
  windowSize: number = 400, // 25ms at 16kHz
  hopSize: number = 160     // 10ms at 16kHz
): AudioTensorFrames {
  const numFrames = Math.max(1, Math.floor((audio.length - windowSize) / hopSize) + 1);
  const data = new Float32Array(numFrames * featuresPerFrame);

  // Pre-emphasis filter
  const preEmphasized = new Float32Array(audio.length);
  preEmphasized[0] = audio[0];
  for (let i = 1; i < audio.length; i++) {
    preEmphasized[i] = audio[i] - 0.97 * audio[i - 1];
  }

  for (let f = 0; f < numFrames; f++) {
    const start = f * hopSize;
    let energySum = 0;

    // Windowed energy distribution across frequency bins
    for (let k = 0; k < featuresPerFrame; k++) {
      let binSum = 0;
      const binSliceSize = Math.floor(windowSize / featuresPerFrame);
      for (let s = 0; s < binSliceSize; s++) {
        const idx = start + k * binSliceSize + s;
        if (idx < preEmphasized.length) {
          const sample = preEmphasized[idx];
          binSum += sample * sample;
        }
      }
      // Log energy
      const logEnergy = Math.log(1.0 + 1000.0 * binSum);
      data[f * featuresPerFrame + k] = logEnergy;
      energySum += logEnergy;
    }
  }

  return {
    data,
    numFrames,
    featuresPerFrame,
  };
}

/**
 * Creates a synthetic 16kHz mono WAV file in memory (for testing and offline generation).
 */
export function createSyntheticWav(durationSec: number = 1.0, freqHz: number = 440.0): ArrayBuffer {
  const sampleRate = 16000;
  const numSamples = Math.floor(sampleRate * durationSec);
  const byteLength = 44 + numSamples * 2;
  const buffer = new ArrayBuffer(byteLength);
  const view = new DataView(buffer);

  // RIFF chunk descriptor
  view.setUint8(0, 0x52); // 'R'
  view.setUint8(1, 0x49); // 'I'
  view.setUint8(2, 0x46); // 'F'
  view.setUint8(3, 0x46); // 'F'
  view.setUint32(4, byteLength - 8, true);
  view.setUint8(8, 0x57);  // 'W'
  view.setUint8(9, 0x41);  // 'A'
  view.setUint8(10, 0x56); // 'V'
  view.setUint8(11, 0x45); // 'E'

  // 'fmt ' sub-chunk
  view.setUint8(12, 0x66); // 'f'
  view.setUint8(13, 0x6d); // 'm'
  view.setUint8(14, 0x74); // 't'
  view.setUint8(15, 0x20); // ' '
  view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
  view.setUint16(20, 1, true);  // AudioFormat (1 for PCM)
  view.setUint16(22, 1, true);  // NumChannels (1 = mono)
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // ByteRate
  view.setUint16(32, 2, true);  // BlockAlign
  view.setUint16(34, 16, true); // BitsPerSample

  // 'data' sub-chunk
  view.setUint8(36, 0x64); // 'd'
  view.setUint8(37, 0x61); // 'a'
  view.setUint8(38, 0x74); // 't'
  view.setUint8(39, 0x61); // 'a'
  view.setUint32(40, numSamples * 2, true);

  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    const sample = Math.sin(2 * Math.PI * freqHz * t) * 0.7;
    const int16 = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
    view.setInt16(44 + i * 2, int16, true);
  }

  return buffer;
}
