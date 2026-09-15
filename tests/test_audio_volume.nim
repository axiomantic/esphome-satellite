import std/[unittest, math]
import ../src/audio_volume

suite "Audio Volume Proportional Scaling Suite (TDD)":
  test "Default volume levels produce exact expected multiplier":
    # Master = 100%, Voice = 80%, Slot = 100%
    let vol = calculateEffectiveVoiceVolume(100.0f, 80.0f, 100.0f)
    check abs(vol - 0.8f) < 0.001f

  test "Master volume scales voice dialogue proportionally":
    # Master = 50%, Voice = 80%, Slot = 100% -> 0.4
    let halfMaster = calculateEffectiveVoiceVolume(50.0f, 80.0f, 100.0f)
    check abs(halfMaster - 0.4f) < 0.001f

    # Master = 25%, Voice = 80%, Slot = 100% -> 0.2
    let quarterMaster = calculateEffectiveVoiceVolume(25.0f, 80.0f, 100.0f)
    check abs(quarterMaster - 0.2f) < 0.001f

  test "Slot volume scales relative to global voice volume":
    # Master = 100%, Voice = 80%, Slot = 50% -> 0.4
    let halfSlot = calculateEffectiveVoiceVolume(100.0f, 80.0f, 50.0f)
    check abs(halfSlot - 0.4f) < 0.001f

  test "Master volume scales acoustic cue sounds proportionally":
    # Master = 100%, Chime = 75% -> 0.75
    check abs(calculateEffectiveSoundVolume(100.0f, 75.0f) - 0.75f) < 0.001f
    # Master = 50%, Chime = 75% -> 0.375
    check abs(calculateEffectiveSoundVolume(50.0f, 75.0f) - 0.375f) < 0.001f
    # Master = 0%, Chime = 75% -> 0.0
    check calculateEffectiveSoundVolume(0.0f, 75.0f) == 0.0f

  test "Volume clamping bounds output strictly to [0.0, 1.0]":
    # Exceeding 100%
    check calculateEffectiveVoiceVolume(120.0f, 100.0f, 100.0f) == 1.0f
    check calculateEffectiveSoundVolume(150.0f, 100.0f) == 1.0f

    # Negative inputs
    check calculateEffectiveVoiceVolume(-10.0f, 80.0f, 100.0f) == 0.0f
    check calculateEffectiveSoundVolume(-50.0f, 75.0f) == 0.0f
