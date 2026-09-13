## Legacy NVS Preference Migration & Hash Mapping in Nim
##
## Computes deterministic FNV-1a hashes and handles legacy v0.5.0 entity preference
## value migrations to v0.6.0 dual-slot architecture.

func fnv1aHash*(s: string): uint32 =
  ## 32-bit FNV-1a hash algorithm matching ESPHome preference hashing.
  var h: uint32 = 2166136261'u32
  for c in s:
    h = (h xor uint32(ord(c))) * 16777619'u32
  return h

# Legacy v0.5.0 FNV-1a preference hashes computed from pre-v0.6.0 entity names
const
  HASH_LEGACY_VOICE_VOLUME* = 1848069015'u32           ## "Audio: Voice Volume"
  HASH_LEGACY_CANCEL_SOUND* = 1728718513'u32           ## "Audio: Cancel Sound Sound"
  HASH_LEGACY_WAKE_CHIME* = 817734680'u32              ## "Audio: Wake Chime Sound"
  HASH_LEGACY_PROCESSING_SOUND* = 3079313095'u32        ## "Audio: Processing Sound"
  HASH_LEGACY_SENSITIVITY* = 4098752856'u32             ## "Speech: Wake Word Sensitivity"
  HASH_LEGACY_WAKE_CHIME_SWITCH* = 3930144138'u32       ## "Audio: Wake Chime Enabled"
  HASH_LEGACY_CANCEL_SOUND_SWITCH* = 483196759'u32       ## "Audio: Cancel Sound Enabled"
  NVS_MIGRATION_VERSION_KEY* = 3847291045'u32

# Legacy option arrays for deterministic string-based mapping
const
  LEGACY_SENSITIVITY_OPTIONS*: array[3, cstring] = [
    cstring"Slightly sensitive", cstring"Moderately sensitive", cstring"Very sensitive"
  ]

  LEGACY_CHIME_OPTIONS*: array[18, cstring] = [
    cstring"Bell Ping", cstring"Modern Chime", cstring"Crystal Glass", cstring"Warm Kalimba", cstring"Meditation Bell",
    cstring"Marimba", cstring"Subtle Beep", cstring"Bamboo Chime", cstring"Tibetan Bowl", cstring"Acoustic Harp", cstring"Woodblock",
    cstring"Ceramic Bell", cstring"Neon Shimmer", cstring"Prism Ping", cstring"Cyber Bloom", cstring"Quantum Beep", cstring"Aero Chime",
    cstring"Silent"
  ]

  LEGACY_PROC_OPTIONS*: array[18, cstring] = [
    cstring"Spinner", cstring"Pulse", cstring"Sonar", cstring"Tick", cstring"Typewriter", cstring"Clockwork", cstring"Water Droplets",
    cstring"Raindrops", cstring"Forest Stream", cstring"Campfire Ember", cstring"Shishi-Odoshi", cstring"Soft Footsteps",
    cstring"Radar Ping", cstring"Data Crunch", cstring"Telemetry Blip", cstring"Quantum Flux", cstring"Retro Terminal",
    cstring"Silent"
  ]

  LEGACY_CANCEL_OPTIONS*: array[18, cstring] = [
    cstring"Match Wake Chime", cstring"Bell Ping", cstring"Modern Chime", cstring"Crystal Glass", cstring"Warm Kalimba",
    cstring"Meditation Bell", cstring"Marimba", cstring"Subtle Beep", cstring"Bamboo Chime", cstring"Tibetan Bowl",
    cstring"Acoustic Harp", cstring"Woodblock", cstring"Ceramic Bell", cstring"Neon Shimmer", cstring"Prism Ping",
    cstring"Cyber Bloom", cstring"Quantum Beep", cstring"Aero Chime"
  ]

proc getLegacySensitivityOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_SENSITIVITY_OPTIONS.len:
    $LEGACY_SENSITIVITY_OPTIONS[idx]
  else:
    ""

proc getLegacyChimeOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_CHIME_OPTIONS.len:
    $LEGACY_CHIME_OPTIONS[idx]
  else:
    ""

proc getLegacyProcOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_PROC_OPTIONS.len:
    $LEGACY_PROC_OPTIONS[idx]
  else:
    ""

proc getLegacyCancelOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_CANCEL_OPTIONS.len:
    $LEGACY_CANCEL_OPTIONS[idx]
  else:
    ""

# C ABI bridge exports
proc nim_nvs_get_legacy_sensitivity*(idx: csize_t): cstring {.exportc, cdecl.} =
  let i = int(idx)
  if i >= 0 and i < LEGACY_SENSITIVITY_OPTIONS.len:
    LEGACY_SENSITIVITY_OPTIONS[i]
  else:
    nil

proc nim_nvs_get_legacy_chime*(idx: csize_t): cstring {.exportc, cdecl.} =
  let i = int(idx)
  if i >= 0 and i < LEGACY_CHIME_OPTIONS.len:
    LEGACY_CHIME_OPTIONS[i]
  else:
    nil

proc nim_nvs_get_legacy_proc*(idx: csize_t): cstring {.exportc, cdecl.} =
  let i = int(idx)
  if i >= 0 and i < LEGACY_PROC_OPTIONS.len:
    LEGACY_PROC_OPTIONS[i]
  else:
    nil

proc nim_nvs_get_legacy_cancel*(idx: csize_t): cstring {.exportc, cdecl.} =
  let i = int(idx)
  if i >= 0 and i < LEGACY_CANCEL_OPTIONS.len:
    LEGACY_CANCEL_OPTIONS[i]
  else:
    nil
