## Audio Volume Scaling in Nim
##
## Provides proportional scaling and clamping for master, voice, and acoustic cue volumes.

func calculateEffectiveVoiceVolume*(masterPct, voicePct, slotPct: float32): float32 {.inline.} =
  result = (masterPct / 100.0f) * (voicePct / 100.0f) * (slotPct / 100.0f)
  if result > 1.0f: result = 1.0f
  elif result < 0.0f: result = 0.0f

func calculateEffectiveSoundVolume*(masterPct, soundPct: float32): float32 {.inline.} =
  result = (masterPct / 100.0f) * (soundPct / 100.0f)
  if result > 1.0f: result = 1.0f
  elif result < 0.0f: result = 0.0f
