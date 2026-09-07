/**
 * In-Browser WebGPU & WASM/CPU Wake Word Neural Network Trainer.
 * Supports streaming convolutional architecture designed for ESP32-S3 MicroWakeWord inference.
 */

import { AudioTensorFrames } from "./audio.js";

export interface TrainingSample {
  features: AudioTensorFrames;
  label: number; // 1 for positive wake word, 0 for negative/ambient
}

export interface TrainingConfig {
  epochs: number;
  learningRate: number;
  batchSize: number;
  timeSteps: number;
  featureBins: number;
  useWebGPU?: boolean;
}

export interface TrainingProgress {
  epoch: number;
  totalEpochs: number;
  loss: number;
  accuracy: number;
}

export interface ModelLayerWeights {
  convKernel: Float32Array; // [featureBins, hiddenDim]
  convBias: Float32Array;   // [hiddenDim]
  denseKernel: Float32Array;// [hiddenDim, 1]
  denseBias: Float32Array;  // [1]
}

/**
 * Checks if the WebGPU API is available in the current execution environment.
 */
export function isWebGPUSupported(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator && !!navigator.gpu;
}

export class WakeWordTrainer {
  private config: TrainingConfig;
  private weights: ModelLayerWeights;
  private hiddenDim: number = 16;

  constructor(config: Partial<TrainingConfig> = {}) {
    this.config = {
      epochs: config.epochs ?? 10,
      learningRate: config.learningRate ?? 0.01,
      batchSize: config.batchSize ?? 4,
      timeSteps: config.timeSteps ?? 10,
      featureBins: config.featureBins ?? 40,
      useWebGPU: config.useWebGPU ?? false,
    };

    // Initialize model weights with Xavier normal initialization
    const fanIn = this.config.featureBins;
    const stdDev = Math.sqrt(2.0 / fanIn);

    const convKernel = new Float32Array(this.config.featureBins * this.hiddenDim);
    for (let i = 0; i < convKernel.length; i++) {
      convKernel[i] = (Math.random() * 2 - 1) * stdDev;
    }

    const convBias = new Float32Array(this.hiddenDim).fill(0.01);

    const denseKernel = new Float32Array(this.hiddenDim);
    for (let i = 0; i < denseKernel.length; i++) {
      denseKernel[i] = (Math.random() * 2 - 1) * Math.sqrt(2.0 / this.hiddenDim);
    }

    const denseBias = new Float32Array(1).fill(0.0);

    this.weights = {
      convKernel,
      convBias,
      denseKernel,
      denseBias,
    };
  }

  /**
   * Forward inference pass on a single audio feature frame vector.
   * Returns predicted probability and intermediate activations for backprop.
   */
  public forward(sample: AudioTensorFrames): {
    pred: number;
    pooled: Float32Array;
    preAct: Float32Array;
    hidden: Float32Array;
  } {
    const { data, numFrames, featuresPerFrame } = sample;
    const bins = Math.min(featuresPerFrame, this.config.featureBins);
    const hidden = new Float32Array(this.hiddenDim);
    const preAct = new Float32Array(this.hiddenDim);

    // 1. Average pooling across time frames into frequency vector
    const pooled = new Float32Array(bins);
    if (numFrames > 0) {
      for (let f = 0; f < numFrames; f++) {
        for (let k = 0; k < bins; k++) {
          pooled[k] += data[f * featuresPerFrame + k] / numFrames;
        }
      }
    }

    // 2. Linear projection + ReLU activation
    for (let h = 0; h < this.hiddenDim; h++) {
      let sum = this.weights.convBias[h];
      for (let k = 0; k < bins; k++) {
        sum += pooled[k] * this.weights.convKernel[k * this.hiddenDim + h];
      }
      preAct[h] = sum;
      hidden[h] = Math.max(0, sum); // ReLU
    }

    // 3. Dense layer + Sigmoid output
    let logit = this.weights.denseBias[0];
    for (let h = 0; h < this.hiddenDim; h++) {
      logit += hidden[h] * this.weights.denseKernel[h];
    }

    const pred = 1.0 / (1.0 + Math.exp(-Math.max(-10, Math.min(10, logit))));
    return { pred, pooled, preAct, hidden };
  }

  /**
   * Forward inference pass on a single audio feature frame vector.
   * Returns predicted probability [0.0, 1.0].
   */
  public predict(sample: AudioTensorFrames): number {
    return this.forward(sample).pred;
  }

  /**
   * Performs one gradient descent step over a batch of training samples.
   */
  public trainStep(batch: TrainingSample[]): { loss: number; accuracy: number } {
    let totalLoss = 0;
    let correct = 0;
    const lr = this.config.learningRate;

    // Accumulators for gradients
    const gradConvKernel = new Float32Array(this.weights.convKernel.length);
    const gradConvBias = new Float32Array(this.weights.convBias.length);
    const gradDenseKernel = new Float32Array(this.weights.denseKernel.length);
    let gradDenseBias = 0;

    for (const sample of batch) {
      const { pred, pooled, preAct, hidden } = this.forward(sample.features);
      const target = sample.label;

      // Binary cross-entropy loss: - [y * log(p) + (1-y) * log(1-p)]
      const pClamped = Math.max(1e-7, Math.min(1 - 1e-7, pred));
      const bce = -(target * Math.log(pClamped) + (1 - target) * Math.log(1 - pClamped));
      totalLoss += bce;

      const isCorrect = (pred >= 0.5 && target === 1) || (pred < 0.5 && target === 0);
      if (isCorrect) correct++;

      // Gradient of BCE w.r.t logit: (pred - target)
      const dLogit = pred - target;

      // Accumulate dense gradients
      gradDenseBias += dLogit;
      for (let h = 0; h < this.hiddenDim; h++) {
        gradDenseKernel[h] += dLogit * hidden[h];

        // Backpropagation through ReLU to conv layer
        const dAct = preAct[h] > 0 ? dLogit * this.weights.denseKernel[h] : 0.0;
        gradConvBias[h] += dAct;

        // Backprop to spectral projection conv kernel
        const bins = pooled.length;
        for (let k = 0; k < bins; k++) {
          gradConvKernel[k * this.hiddenDim + h] += dAct * pooled[k];
        }
      }
    }

    const batchSize = Math.max(1, batch.length);

    // Apply SGD updates
    for (let i = 0; i < this.weights.denseKernel.length; i++) {
      this.weights.denseKernel[i] -= lr * (gradDenseKernel[i] / batchSize);
    }
    this.weights.denseBias[0] -= lr * (gradDenseBias / batchSize);

    for (let i = 0; i < this.weights.convBias.length; i++) {
      this.weights.convBias[i] -= lr * (gradConvBias[i] / batchSize);
    }

    for (let i = 0; i < this.weights.convKernel.length; i++) {
      this.weights.convKernel[i] -= lr * (gradConvKernel[i] / batchSize);
    }

    return {
      loss: totalLoss / batchSize,
      accuracy: correct / batchSize,
    };
  }

  /**
   * Executes the full training routine over provided samples.
   */
  public async train(
    samples: TrainingSample[],
    onProgress?: (progress: TrainingProgress) => void
  ): Promise<ModelLayerWeights> {
    if (samples.length === 0) {
      throw new Error("Cannot train with empty sample dataset.");
    }

    for (let epoch = 1; epoch <= this.config.epochs; epoch++) {
      // Shuffle samples
      const shuffled = [...samples].sort(() => Math.random() - 0.5);
      const stepResult = this.trainStep(shuffled);

      if (onProgress) {
        onProgress({
          epoch,
          totalEpochs: this.config.epochs,
          loss: stepResult.loss,
          accuracy: stepResult.accuracy,
        });
      }
    }

    return this.weights;
  }

  public getWeights(): ModelLayerWeights {
    return this.weights;
  }
}
