import { describe, it, expect } from "vitest";
import {
  normalizePhoneticPhrase,
  validatePhoneticSpelling,
  expandNumbers,
  expandAlphanumeric,
} from "../src/phonetics.js";
import {
  createSyntheticWav,
  decodeWav,
  resampleTo16kHz,
  extractSpectralFeatures,
} from "../src/audio.js";
import {
  WakeWordTrainer,
  TrainingSample,
} from "../src/trainer.js";
import {
  packageTfliteModel,
  validateTfliteBuffer,
} from "../src/tflite.js";

describe("Phonetics & Expansion Engine", () => {
  it("expands 'ok c3p0' -> 'okay see three pee oh'", () => {
    const result = normalizePhoneticPhrase("ok c3p0");
    expect(result).toBe("okay see three pee oh");
  });

  it("expands 'dj pj' -> 'dee jay pee jay'", () => {
    const result = normalizePhoneticPhrase("dj pj");
    expect(result).toBe("dee jay pee jay");
  });

  it("expands numbers and alphanumeric tokens", () => {
    expect(expandNumbers("satellite 42")).toBe("satellite four two");
    expect(expandAlphanumeric("r2d2")).toBe("ar two dee two");
    expect(normalizePhoneticPhrase("Hey R2D2, status 1")).toBe("hey ar two dee two status one");
  });

  it("validates phonetic spelling and flags unexpanded abbreviations", () => {
    const valid = validatePhoneticSpelling("okay see three pee oh");
    expect(valid.isValid).toBe(true);
    expect(valid.suggestions).toHaveLength(0);

    const invalid = validatePhoneticSpelling("ok c3p0");
    expect(invalid.isValid).toBe(false);
    expect(invalid.suggestions.length).toBeGreaterThan(0);
    expect(invalid.normalized).toBe("okay see three pee oh");
  });
});

describe("Audio Pipeline & Feature Extraction", () => {
  it("decodes 16kHz mono WAV properly", () => {
    const wavBuffer = createSyntheticWav(0.5, 440.0);
    const { samples, metadata } = decodeWav(wavBuffer);

    expect(metadata.sampleRate).toBe(16000);
    expect(metadata.numChannels).toBe(1);
    expect(metadata.bitsPerSample).toBe(16);
    expect(samples.length).toBe(8000);
    expect(metadata.durationSec).toBe(0.5);
  });

  it("resamples audio correctly", () => {
    const input = new Float32Array([0.0, 0.5, 1.0, 0.5, 0.0]);
    const resampled = resampleTo16kHz(input, 16000);
    expect(resampled).toBe(input); // unchanged if already 16k
  });

  it("extracts 40-bin spectral features matching MicroWakeWord format", () => {
    const wavBuffer = createSyntheticWav(0.5, 880.0);
    const { samples } = decodeWav(wavBuffer);
    const features = extractSpectralFeatures(samples, 40);

    expect(features.featuresPerFrame).toBe(40);
    expect(features.numFrames).toBeGreaterThan(10);
    expect(features.data.length).toBe(features.numFrames * 40);

    // Verify all feature values are real finite numbers
    for (let i = 0; i < features.data.length; i++) {
      expect(Number.isFinite(features.data[i])).toBe(true);
    }
  });

  it("handles empty audio arrays gracefully", () => {
    const empty = extractSpectralFeatures(new Float32Array(0), 40);
    expect(empty.numFrames).toBe(0);
    expect(empty.data.length).toBe(0);
  });

  it("decodes WAV files with odd-length metadata chunks requiring padding alignment", () => {
    // Construct a WAV with a 3-byte 'JUNK' chunk preceding 'data'
    const sampleRate = 16000;
    const numSamples = 100;
    // RIFF (12) + fmt (24) + JUNK header (8) + JUNK payload (3) + 1 pad byte + data header (8) + data (200)
    const totalBytes = 12 + 24 + 8 + 3 + 1 + 8 + (numSamples * 2);
    const buffer = new ArrayBuffer(totalBytes);
    const view = new DataView(buffer);

    // RIFF header
    view.setUint8(0, 0x52); view.setUint8(1, 0x49); view.setUint8(2, 0x46); view.setUint8(3, 0x46);
    view.setUint32(4, totalBytes - 8, true);
    view.setUint8(8, 0x57); view.setUint8(9, 0x41); view.setUint8(10, 0x56); view.setUint8(11, 0x45);

    // fmt chunk (offset 12)
    view.setUint8(12, 0x66); view.setUint8(13, 0x6d); view.setUint8(14, 0x74); view.setUint8(15, 0x20);
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);

    // Odd-sized JUNK chunk (offset 36, size 3)
    view.setUint8(36, 0x4a); view.setUint8(37, 0x55); view.setUint8(38, 0x4e); view.setUint8(39, 0x4b);
    view.setUint32(40, 3, true);
    view.setUint8(44, 0x01); view.setUint8(45, 0x02); view.setUint8(46, 0x03);
    view.setUint8(47, 0x00); // 1-byte padding to align next chunk to 48

    // data chunk (offset 48)
    view.setUint8(48, 0x64); view.setUint8(49, 0x61); view.setUint8(50, 0x74); view.setUint8(51, 0x61);
    view.setUint32(52, numSamples * 2, true);

    const { samples, metadata } = decodeWav(buffer);
    expect(metadata.numSamples).toBe(numSamples);
    expect(samples.length).toBe(numSamples);
  });
});

describe("Neural Network Trainer & MicroWakeWord Engine", () => {
  it("computes predictions and updates weights (including convKernel) via gradient descent", async () => {
    const trainer = new WakeWordTrainer({
      epochs: 5,
      learningRate: 0.05,
    });

    const initialConvKernel = new Float32Array(trainer.getWeights().convKernel);

    const wavPositive = createSyntheticWav(0.5, 880.0);
    const { samples: posSamples } = decodeWav(wavPositive);
    const posFeatures = extractSpectralFeatures(posSamples, 40);

    const wavNegative = createSyntheticWav(0.5, 220.0);
    const { samples: negSamples } = decodeWav(wavNegative);
    const negFeatures = extractSpectralFeatures(negSamples, 40);

    const dataset: TrainingSample[] = [
      { features: posFeatures, label: 1 },
      { features: negFeatures, label: 0 },
    ];

    const initialPred = trainer.predict(posFeatures);
    expect(initialPred).toBeGreaterThanOrEqual(0.0);
    expect(initialPred).toBeLessThanOrEqual(1.0);

    let lastLoss = 999;
    const weights = await trainer.train(dataset, (p) => {
      lastLoss = p.loss;
    });

    expect(weights.convKernel.length).toBe(40 * 16);
    expect(weights.denseKernel.length).toBe(16);
    expect(lastLoss).toBeLessThan(999);

    // Verify convKernel actually trained and changed from its initial values
    let kernelChanged = false;
    for (let i = 0; i < weights.convKernel.length; i++) {
      if (Math.abs(weights.convKernel[i] - initialConvKernel[i]) > 1e-6) {
        kernelChanged = true;
        break;
      }
    }
    expect(kernelChanged).toBe(true);
  });
});

describe("TFLite Micro Model Packager", () => {
  it("packages weights into a valid TFLite FlatBuffer with 'TFL3' magic", () => {
    const trainer = new WakeWordTrainer();
    const weights = trainer.getWeights();

    const tfliteBytes = packageTfliteModel(weights, {
      modelName: "micro_wake_c3p0",
      wakeWordPhrase: "okay see three pee oh",
      author: "esphome-satellite",
      version: 3,
    });

    expect(tfliteBytes.byteLength).toBeGreaterThan(100);

    const validation = validateTfliteBuffer(tfliteBytes.buffer);
    expect(validation.isValid).toBe(true);
    expect(validation.version).toBe(3);
    expect(validation.sizeBytes).toBe(tfliteBytes.byteLength);
  });
});
