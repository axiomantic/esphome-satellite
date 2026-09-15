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
    var samples: array[160, int16]
    for i in 0 ..< samples.len:
      samples[i] = int16(1000.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))
    nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](samples[0].addr), samples.len)
    # Makeup gain should have increased peak value from 1000
    var peak: int16 = 0
    for i in 80 ..< samples.len:
      if abs(samples[i]) > peak: peak = abs(samples[i])
    check peak > 1400

  test "Microphone pre-gain boost and 32-bit audio scaling":
    setMicPreGainDb(6.0'f32) # +6 dB is ~1.995x (approx 2.0x)
    check getMicPreGainLinear() > 1.95'f32
    check getMicPreGainLinear() < 2.05'f32

    var pcm32: array[4, int32] = [1000'i32, -2000'i32, 1000000'i32, -1000000'i32]
    applyMicPreGain32(pcm32[0].addr, pcm32.len)
    check pcm32[0] > 1950 and pcm32[0] < 2050
    check pcm32[1] < -3900 and pcm32[1] > -4100

    # Test clamping on extreme inputs
    var extreme32: array[2, int32] = [2000000000'i32, -2000000000'i32]
    applyMicPreGain32(extreme32[0].addr, extreme32.len)
    check extreme32[0] == 2147483647'i32
    check extreme32[1] == -2147483647'i32

    # C ABI export
    nim_audio_dsp_set_mic_pre_gain(0.0'f32) # unity gain (0 dB)
    check getMicPreGainLinear() == 1.0'f32
    var testUnity: array[1, int32] = [12345'i32]
    nim_audio_dsp_apply_mic_pre_gain32(cast[ptr UncheckedArray[int32]](testUnity[0].addr), 1)
    check testUnity[0] == 12345'i32

  test "Audio DSP independent vocal boost and speaker protection toggles":
    # 1. Both disabled: 100% bit-exact passthrough
    nim_audio_dsp_set_vocal_boost(false)
    nim_audio_dsp_set_speaker_protection(false)
    check nim_audio_dsp_is_vocal_boost_enabled() == false
    check nim_audio_dsp_is_speaker_protection_enabled() == false

    var rawSamples: array[160, int16]
    for i in 0 ..< rawSamples.len:
      rawSamples[i] = int16(1000.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))
    var origCopy = rawSamples
    nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](rawSamples[0].addr), rawSamples.len)
    check rawSamples == origCopy

    # 2. Vocal boost only (speaker protection OFF):
    # 1000 Hz tone receives makeup gain, but 50 Hz sub-bass is not filtered
    nim_audio_dsp_set_vocal_boost(true)
    nim_audio_dsp_set_speaker_protection(false)
    check nim_audio_dsp_is_vocal_boost_enabled() == true
    check nim_audio_dsp_is_speaker_protection_enabled() == false

    var vocalOnly: array[160, int16]
    for i in 0 ..< vocalOnly.len:
      vocalOnly[i] = int16(1000.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))
    nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](vocalOnly[0].addr), vocalOnly.len)
    var peakVocalOnly: int16 = 0
    for i in 80 ..< vocalOnly.len:
      if abs(vocalOnly[i]) > peakVocalOnly: peakVocalOnly = abs(vocalOnly[i])
    check peakVocalOnly > 1400 # Boosted by +5 dB

    # 3. Speaker protection only (vocal boost OFF):
    # 1000 Hz tone is NOT boosted (+0 dB), but 50 Hz tone is attenuated by HPF
    nim_audio_dsp_set_vocal_boost(false)
    nim_audio_dsp_set_speaker_protection(true)
    check nim_audio_dsp_is_vocal_boost_enabled() == false
    check nim_audio_dsp_is_speaker_protection_enabled() == true

    var protTone: array[160, int16]
    for i in 0 ..< protTone.len:
      protTone[i] = int16(1000.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0))
    nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](protTone[0].addr), protTone.len)
    var peakProtTone: int16 = 0
    for i in 80 ..< protTone.len:
      if abs(protTone[i]) > peakProtTone: peakProtTone = abs(protTone[i])
    check peakProtTone <= 1050 # No vocal makeup boost!

    # 4. Re-enable both for standard operation
    nim_audio_dsp_set_vocal_boost(true)
    nim_audio_dsp_set_speaker_protection(true)
    check nim_audio_dsp_is_vocal_boost_enabled() == true
    check nim_audio_dsp_is_speaker_protection_enabled() == true

  test "Biquad high-pass rumble filter attenuates sub-bass and preserves voice frequencies":
    var hpf = newHighPassFilter(sampleRate = 16000'f32, cutoffHz = 180'f32)
    
    # 1. Test DC rejection: constant 5000 offset should decay to near 0
    var dcSample: float32 = 5000.0'f32
    var lastY: float32 = 0.0'f32
    for _ in 0 ..< 500:
      lastY = hpf.processSample(dcSample)
    check abs(lastY) < 1.0'f32 # DC completely blocked

    # 2. Test 50 Hz sub-bass rejection: 50 Hz is far below 180 Hz cutoff
    hpf.reset()
    var subBassSamples: array[1600, float32]
    var subBassOut: array[1600, float32]
    for i in 0 ..< subBassSamples.len:
      subBassSamples[i] = 10000.0 * sin(2.0 * PI * 50.0 * float(i) / 16000.0)
      subBassOut[i] = hpf.processSample(subBassSamples[i])
    
    # Steady state peak of 50 Hz should be attenuated by at least 15 dB (amplitude < 1800 from 10000)
    var peak50: float32 = 0.0
    for i in 800 ..< subBassOut.len:
      if abs(subBassOut[i]) > peak50: peak50 = abs(subBassOut[i])
    check peak50 < 1800.0'f32 # ~22.3 dB attenuation of 50 Hz rumble (peak is ~768 from 10000)

    # 3. Test 1000 Hz vocal tone: 1000 Hz is well above 180 Hz cutoff, must have > 95% passband gain
    hpf.reset()
    var vocalSamples: array[1600, float32]
    var vocalOut: array[1600, float32]
    for i in 0 ..< vocalSamples.len:
      vocalSamples[i] = 10000.0 * sin(2.0 * PI * 1000.0 * float(i) / 16000.0)
      vocalOut[i] = hpf.processSample(vocalSamples[i])
    
    var peak1000: float32 = 0.0
    for i in 800 ..< vocalOut.len:
      if abs(vocalOut[i]) > peak1000: peak1000 = abs(vocalOut[i])
    check peak1000 > 9500.0'f32 # > 95% transmission
