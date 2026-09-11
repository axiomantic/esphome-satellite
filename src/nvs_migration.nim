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
  LEGACY_SENSITIVITY_OPTIONS*: array[3, string] = [
    "Slightly sensitive", "Moderately sensitive", "Very sensitive"
  ]

  LEGACY_CHIME_OPTIONS*: array[18, string] = [
    "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
    "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
    "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime",
    "Silent"
  ]

  LEGACY_PROC_OPTIONS*: array[18, string] = [
    "Spinner", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets",
    "Raindrops", "Forest Stream", "Campfire Ember", "Shishi-Odoshi", "Soft Footsteps",
    "Radar Ping", "Data Crunch", "Telemetry Blip", "Quantum Flux", "Retro Terminal",
    "Silent"
  ]

  LEGACY_CANCEL_OPTIONS*: array[18, string] = [
    "Match Wake Chime", "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba",
    "Meditation Bell", "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl",
    "Acoustic Harp", "Woodblock", "Ceramic Bell", "Neon Shimmer", "Prism Ping",
    "Cyber Bloom", "Quantum Beep", "Aero Chime"
  ]

proc getLegacySensitivityOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_SENSITIVITY_OPTIONS.len:
    LEGACY_SENSITIVITY_OPTIONS[idx]
  else:
    ""

proc getLegacyChimeOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_CHIME_OPTIONS.len:
    LEGACY_CHIME_OPTIONS[idx]
  else:
    ""

proc getLegacyProcOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_PROC_OPTIONS.len:
    LEGACY_PROC_OPTIONS[idx]
  else:
    ""

proc getLegacyCancelOption*(idx: int): string =
  if idx >= 0 and idx < LEGACY_CANCEL_OPTIONS.len:
    LEGACY_CANCEL_OPTIONS[idx]
  else:
    ""

# C ABI bridge exports
proc nim_nvs_get_legacy_sensitivity*(idx: csize_t): cstring {.exportc, cdecl.} =
  let opt = getLegacySensitivityOption(int(idx))
  if opt.len > 0: cstring(opt) else: nil

proc nim_nvs_get_legacy_chime*(idx: csize_t): cstring {.exportc, cdecl.} =
  let opt = getLegacyChimeOption(int(idx))
  if opt.len > 0: cstring(opt) else: nil

proc nim_nvs_get_legacy_proc*(idx: csize_t): cstring {.exportc, cdecl.} =
  let opt = getLegacyProcOption(int(idx))
  if opt.len > 0: cstring(opt) else: nil

proc nim_nvs_get_legacy_cancel*(idx: csize_t): cstring {.exportc, cdecl.} =
  let opt = getLegacyCancelOption(int(idx))
  if opt.len > 0: cstring(opt) else: nil
