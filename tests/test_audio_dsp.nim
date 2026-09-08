import std/unittest
import std/math

# We will import audio_dsp once created. For now, testing RED phase.
import ../src/audio_dsp

suite "Real-Time Audio DSP Suite (TDD)":
  test "AudioCompressorLimiter initialization and parameters":
    var comp = newAudioCompressor(
      sampleRate = 16000'f32,
      thresholdDb = -14.0'f32,
      ratio = 3.0'f32,
      attackMs = 4.0'f32,
      releaseMs = 75.0'f32,
      makeupGainDb = 5.0'f32
    )
    check comp.sampleRate == 16000'f32
    check comp.makeupGain > 1.5'f32 # +5dB is ~1.778x linear gain
    check comp.envelope == 0.0'f32

  test "Quiet vocal passages receive full makeup gain":
    var comp = newAudioCompressor(sampleRate = 16000'f32, thresholdDb = -14.0'f32, makeupGainDb = 5.0'f32)
    # Quiet 1000 Hz tone at -26 dBFS (amplitude ~1600)
    var samples: array[160, int16]
    for i in 0 ..< samples.len:
      samples[i] = int16(1600.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))
    
    let originalPeak = 1600
    comp.process(samples[0].addr, samples.len)
    
    # Peak should be boosted by ~5 dB (~1.77x) without compression
    var boostedPeak: int16 = 0
    for s in samples:
      if abs(int(s)) > int(boostedPeak):
        boostedPeak = abs(s)
    
    check float(boostedPeak) > float(originalPeak) * 1.5
    check float(boostedPeak) < float(originalPeak) * 2.0

  test "Signals above threshold experience dynamic gain reduction":
    var comp = newAudioCompressor(sampleRate = 16000'f32, thresholdDb = -14.0'f32, ratio = 3.0'f32, makeupGainDb = 0.0'f32)
    # Steady 1000 Hz tone at -10 dBFS (amplitude ~10360, well above -14 dBFS threshold ~6520)
    var samples: array[800, int16]
    for i in 0 ..< samples.len:
      samples[i] = int16(10360.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))

    comp.process(samples[0].addr, samples.len)

    # After attack phase (> 30 ms / 480 samples), steady-state peak must be compressed:
    # 10,360 is ~-10 dBFS (+4dB over -14dBFS threshold). At 3:1 ratio, gain reduction is ~2.67 dB (~0.735x).
    # Expected compressed peak is around 10360 * 0.735 = ~7600
    var compressedPeak: int16 = 0
    for i in 480 ..< samples.len:
      if abs(int(samples[i])) > int(compressedPeak):
        compressedPeak = abs(samples[i])

    check compressedPeak < 8500
    check compressedPeak > 7000


  test "Loud transient spikes are clamped by compression and limiting":
    var comp = newAudioCompressor(sampleRate = 16000'f32, thresholdDb = -14.0'f32, makeupGainDb = 5.0'f32)
    # Extremely loud burst near full scale (amplitude 30,000)
    var samples: array[320, int16]
    for i in 0 ..< samples.len:
      samples[i] = int16(30000.0 * sin(2.0 * PI * 400.0 * float(i) / 16000.0))
    
    comp.process(samples[0].addr, samples.len)
    
    # Envelope must track above threshold (-14 dBFS = ~0.20 linear)
    check comp.envelope > 0.50'f32
    
    # All samples must stay strictly within [-32767, 32767] with zero wraparound / clipping
    var maxPeak: int16 = 0
    for s in samples:
      check s >= -32767 and s <= 32767
      if abs(int(s)) > int(maxPeak): maxPeak = abs(s)
    
    # Without compression, 30,000 * 1.778 (+5dB) = 53,340 (digital clipping).
    # With 3:1 compression and rational soft-knee limiting, peak is clamped between 20,000 and 29,000:
    check maxPeak > 20000 and maxPeak < 29000

  test "Envelope follower smooth decay preserves vocal cadence":
    var comp = newAudioCompressor(sampleRate = 16000'f32, attackMs = 4.0'f32, releaseMs = 75.0'f32)
    # Step impulse
    var impulse: array[16, int16]
    impulse[0] = 20000
    comp.process(impulse[0].addr, impulse.len)
    check comp.envelope > 0.0'f32
    
    # Process silence: envelope must decay smoothly, not jump to 0
    var silence: array[80, int16]
    comp.process(silence[0].addr, silence.len)
    check comp.envelope > 0.0'f32
    check comp.envelope < 0.5'f32

  test "C ABI exported function processes buffer in-place":
    var samples: array[64, int16]
    for i in 0 ..< samples.len: samples[i] = 1000
    nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](samples[0].addr), samples.len)
    # Makeup gain should have increased value from 1000
    check samples[30] > 1400
