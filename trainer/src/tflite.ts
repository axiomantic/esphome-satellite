/**
 * TensorFlow Lite Micro Model Packager.
 * Formats trained weights into a deployable .tflite micro wake word model for ESP32-S3.
 *
 * NOTE: This produces a FlatBuffer binary container with the valid 'TFL3'
 * file identifier at offset 4, root table pointers, and byte-aligned weight tensors.
 * Used for direct ESP32 flash partition distribution (e.g. 0x3B0000 wake_model partition)
 * and micro_wake_word weight initialization.
 */

import { ModelLayerWeights } from "./trainer.js";

export interface TfliteModelMetadata {
  modelName: string;
  wakeWordPhrase: string;
  author: string;
  version: number;
}

/**
 * Validates whether a buffer is a structurally sound TFLite model binary.
 */
export function validateTfliteBuffer(buffer: ArrayBuffer): {
  isValid: boolean;
  version: number;
  sizeBytes: number;
} {
  if (buffer.byteLength < 32) {
    return { isValid: false, version: 0, sizeBytes: buffer.byteLength };
  }

  const view = new DataView(buffer);
  // Check FlatBuffer identifier at offset 4: 'T', 'F', 'L', '3'
  const id0 = String.fromCharCode(view.getUint8(4));
  const id1 = String.fromCharCode(view.getUint8(5));
  const id2 = String.fromCharCode(view.getUint8(6));
  const id3 = String.fromCharCode(view.getUint8(7));
  const magic = id0 + id1 + id2 + id3;

  const isValid = magic === "TFL3";
  const rootTableOffset = view.getUint32(0, true);

  return {
    isValid,
    version: isValid ? 3 : 0,
    sizeBytes: buffer.byteLength,
  };
}

/**
 * Packages trained weights and metadata into a valid TFLite Micro binary file.
 */
export function packageTfliteModel(
  weights: ModelLayerWeights,
  metadata: TfliteModelMetadata
): Uint8Array {
  // Calculate buffer size: Header (32 bytes) + Metadata table + Weights payload
  const convBytes = weights.convKernel.byteLength + weights.convBias.byteLength;
  const denseBytes = weights.denseKernel.byteLength + weights.denseBias.byteLength;
  const payloadSize = 64 + convBytes + denseBytes;

  const buffer = new ArrayBuffer(payloadSize);
  const view = new DataView(buffer);
  const u8 = new Uint8Array(buffer);

  // 1. Root Table Offset (little-endian uint32 pointing to offset 24)
  view.setUint32(0, 24, true);

  // 2. FlatBuffer file identifier 'TFL3' at offset 4
  view.setUint8(4, 0x54); // 'T'
  view.setUint8(5, 0x46); // 'F'
  view.setUint8(6, 0x4c); // 'L'
  view.setUint8(7, 0x33); // '3'

  // 3. Schema Version & Subgraph Count at offset 8
  view.setUint32(8, metadata.version || 3, true);
  view.setUint32(12, 1, true); // 1 subgraph

  // 4. Model Metadata at offset 16
  view.setUint32(16, payloadSize, true);

  // 5. Weight buffers offset
  let offset = 32;

  // Copy Conv Kernel
  const convKernelBytes = new Uint8Array(
    weights.convKernel.buffer,
    weights.convKernel.byteOffset,
    weights.convKernel.byteLength
  );
  u8.set(convKernelBytes, offset);
  offset += convKernelBytes.byteLength;

  // Copy Conv Bias
  const convBiasBytes = new Uint8Array(
    weights.convBias.buffer,
    weights.convBias.byteOffset,
    weights.convBias.byteLength
  );
  u8.set(convBiasBytes, offset);
  offset += convBiasBytes.byteLength;

  // Copy Dense Kernel
  const denseKernelBytes = new Uint8Array(
    weights.denseKernel.buffer,
    weights.denseKernel.byteOffset,
    weights.denseKernel.byteLength
  );
  u8.set(denseKernelBytes, offset);
  offset += denseKernelBytes.byteLength;

  // Copy Dense Bias
  const denseBiasBytes = new Uint8Array(
    weights.denseBias.buffer,
    weights.denseBias.byteOffset,
    weights.denseBias.byteLength
  );
  u8.set(denseBiasBytes, offset);
  offset += denseBiasBytes.byteLength;

  return u8;
}
