## Real-Time Audio Dynamic Range Compression, Loudness Normalization & Limiter
##
## Implements a deterministic, zero-heap-allocation audio processor designed
## specifically for speech vocal enhancement on embedded voice satellites.

import std/math

type
  AudioCompressor* = object
    sampleRate*: float32
    thresholdDb*: float32
    thresholdLinear*: float32
    ratio*: float32
    attackCoeff*: float32
    releaseCoeff*: float32
    makeupGainDb*: float32
    makeupGain*: float32
    envelope*: float32

proc newAudioCompressor*(
    sampleRate: float32 = 16000.0'f32,
    thresholdDb: float32 = -14.0'f32,
    ratio: float32 = 3.0'f32,
    attackMs: float32 = 4.0'f32,
    releaseMs: float32 = 75.0'f32,
    makeupGainDb: float32 = 5.0'f32
): AudioCompressor =
  result.sampleRate = sampleRate
  result.thresholdDb = thresholdDb
  result.thresholdLinear = pow(10.0'f32, thresholdDb / 20.0'f32)
  result.ratio = ratio
  result.attackCoeff = exp(-1.0'f32 / (sampleRate * (attackMs / 1000.0'f32)))
  result.releaseCoeff = exp(-1.0'f32 / (sampleRate * (releaseMs / 1000.0'f32)))
  result.makeupGainDb = makeupGainDb
  result.makeupGain = pow(10.0'f32, makeupGainDb / 20.0'f32)
  result.envelope = 0.0'f32

proc softClip*(x: float32, limit: float32 = 32767.0'f32): int16 {.inline.} =
  ## Rational soft-saturation curve: strictly bounded within [-limit, limit].
  ## Linear for small amplitudes, smoothly saturating at high levels with zero clipping buzz.
  let normalized = x / limit
  let saturated = normalized / sqrt(1.0'f32 + normalized * normalized)
  let scaled = saturated * limit
  if scaled >= 32767.0'f32:
    return 32767'i16
  elif scaled <= -32767.0'f32:
    return -32767'i16
  else:
    return int16(scaled)

proc process*(comp: var AudioCompressor, samples: ptr int16, count: int) =
  if samples == nil or count <= 0:
    return

  let arr = cast[ptr UncheckedArray[int16]](samples)
  for i in 0 ..< count:
    let s = float32(arr[i])
    let absX = abs(s) / 32768.0'f32

    # Envelope peak follower
    if absX > comp.envelope:
      comp.envelope = comp.attackCoeff * comp.envelope + (1.0'f32 - comp.attackCoeff) * absX
    else:
      comp.envelope = comp.releaseCoeff * comp.envelope + (1.0'f32 - comp.releaseCoeff) * absX

    # Compute gain reduction
    var gainReduction: float32 = 1.0'f32
    if comp.envelope > comp.thresholdLinear and comp.envelope > 1e-6'f32:
      let envDb = 20.0'f32 * log10(comp.envelope)
      let compressedDb = comp.thresholdDb + (envDb - comp.thresholdDb) / comp.ratio
      gainReduction = pow(10.0'f32, (compressedDb - envDb) / 20.0'f32)

    # Apply compression gain reduction and makeup vocal boost
    let processed = s * gainReduction * comp.makeupGain

    # Soft-knee limiting to eliminate digital clipping
    arr[i] = softClip(processed)

proc process32*(comp: var AudioCompressor, samples: ptr int32, count: int) =
  if samples == nil or count <= 0:
    return

  let arr = cast[ptr UncheckedArray[int32]](samples)
  for i in 0 ..< count:
    let s = float32(arr[i])
    let absX = abs(s) / 2147483648.0'f32

    # Envelope peak follower
    if absX > comp.envelope:
      comp.envelope = comp.attackCoeff * comp.envelope + (1.0'f32 - comp.attackCoeff) * absX
    else:
      comp.envelope = comp.releaseCoeff * comp.envelope + (1.0'f32 - comp.releaseCoeff) * absX

    # Compute gain reduction
    var gainReduction: float32 = 1.0'f32
    if comp.envelope > comp.thresholdLinear and comp.envelope > 1e-6'f32:
      let envDb = 20.0'f32 * log10(comp.envelope)
      let compressedDb = comp.thresholdDb + (envDb - comp.thresholdDb) / comp.ratio
      gainReduction = pow(10.0'f32, (compressedDb - envDb) / 20.0'f32)

    # Apply compression gain reduction and makeup vocal boost
    let processed = s * gainReduction * comp.makeupGain

    # Soft-knee limiting for 32-bit
    let normalized = processed / 2147483647.0'f32
    let saturated = normalized / sqrt(1.0'f32 + normalized * normalized)
    let scaled = saturated * 2147483647.0'f32
    arr[i] = int32(clamp(scaled, -2147483647.0'f32, 2147483647.0'f32))

# Global singleton audio DSP processor for satellite speaker pipeline
var globalVoiceCompressor = newAudioCompressor()

proc nim_audio_dsp_process*(samples: ptr UncheckedArray[int16], count: int) {.exportc: "nim_audio_dsp_process", cdecl.} =
  ## C ABI entry point called directly by ESPHome I2S speaker DMA task (16-bit PCM)
  if samples != nil and count > 0:
    globalVoiceCompressor.process(cast[ptr int16](samples), count)

proc nim_audio_dsp_process32*(samples: ptr UncheckedArray[int32], count: int) {.exportc: "nim_audio_dsp_process32", cdecl.} =
  ## C ABI entry point called directly by ESPHome I2S speaker DMA task (32-bit PCM)
  if samples != nil and count > 0:
    globalVoiceCompressor.process32(cast[ptr int32](samples), count)

# Microphone Pre-Gain Boost for High-Recall Female Voice & Low Energy Equalization
var globalMicPreGainLinear*: float32 = 1.41253754'f32 # Default +3 dB: 10^(3/20)

proc setMicPreGainDb*(db: float32) =
  let clampedDb = clamp(db, 0.0'f32, 12.0'f32)
  globalMicPreGainLinear = pow(10.0'f32, clampedDb / 20.0'f32)

proc getMicPreGainDb*(): float32 =
  return 20.0'f32 * log10(globalMicPreGainLinear)

proc getMicPreGainLinear*(): float32 {.inline.} =
  return globalMicPreGainLinear

proc applyMicPreGain32*(samples: ptr int32, count: int) =
  if samples == nil or count <= 0:
    return
  let gain = globalMicPreGainLinear
  if gain >= 0.999'f32 and gain <= 1.001'f32:
    return
  let arr = cast[ptr UncheckedArray[int32]](samples)
  let gain64 = float64(gain)
  for i in 0 ..< count:
    let scaled = float64(arr[i]) * gain64
    if scaled >= 2147483647.0:
      arr[i] = 2147483647'i32
    elif scaled <= -2147483647.0:
      arr[i] = -2147483647'i32
    else:
      arr[i] = int32(scaled)

proc nim_audio_dsp_set_mic_pre_gain*(db: float32) {.exportc: "nim_audio_dsp_set_mic_pre_gain", cdecl.} =
  setMicPreGainDb(db)

proc nim_audio_dsp_apply_mic_pre_gain32*(samples: ptr UncheckedArray[int32], count: int) {.exportc: "nim_audio_dsp_apply_mic_pre_gain32", cdecl.} =
  applyMicPreGain32(cast[ptr int32](samples), count)

