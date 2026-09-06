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
});

describe("Neural Network Trainer & MicroWakeWord Engine", () => {
  it("computes predictions and updates weights via gradient descent", async () => {
    const trainer = new WakeWordTrainer({
      epochs: 5,
      learningRate: 0.05,
    });

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
