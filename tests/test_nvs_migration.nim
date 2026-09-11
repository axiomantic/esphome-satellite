import std/unittest
import ../src/nvs_migration

suite "NVS Preference Migration & Hash Integrity Suite":
  test "Legacy v0.5.0 FNV-1a preference hashes match exact constants":
    check fnv1aHash("Audio: Voice Volume") == HASH_LEGACY_VOICE_VOLUME
    check fnv1aHash("Audio: Cancel Sound Sound") == HASH_LEGACY_CANCEL_SOUND
    check fnv1aHash("Audio: Wake Chime Sound") == HASH_LEGACY_WAKE_CHIME
    check fnv1aHash("Audio: Processing Sound") == HASH_LEGACY_PROCESSING_SOUND
    check fnv1aHash("Speech: Wake Word Sensitivity") == HASH_LEGACY_SENSITIVITY
    check fnv1aHash("Audio: Wake Chime Enabled") == HASH_LEGACY_WAKE_CHIME_SWITCH
    check fnv1aHash("Audio: Cancel Sound Enabled") == HASH_LEGACY_CANCEL_SOUND_SWITCH

  test "New v0.6.0 Slot 1 FNV-1a preference hashes are distinct and reproducible":
    check fnv1aHash("Slot 1: Volume") == 2638310478'u32
    check fnv1aHash("Slot 1: Cancel Sound") == 2237309249'u32
    check fnv1aHash("Slot 1: Wake Chime") == 3715757824'u32
    check fnv1aHash("Slot 1: Processing Sound") == 3151753516'u32
    check fnv1aHash("Slot 1: Sensitivity") == 511532015'u32
    check fnv1aHash("Slot 1: Wake Chime Enabled") == 1457734337'u32
    check fnv1aHash("Slot 1: Cancel Sound Enabled") == 33816744'u32

    # Verify that slot 1 hashes never collide with legacy hashes
    check fnv1aHash("Slot 1: Volume") != fnv1aHash("Audio: Voice Volume")
    check fnv1aHash("Slot 1: Cancel Sound") != fnv1aHash("Audio: Cancel Sound Sound")
    check fnv1aHash("Slot 1: Sensitivity") != fnv1aHash("Speech: Wake Word Sensitivity")

  test "Legacy sensitivity index-to-option mapping preserves semantic levels":
    check LEGACY_SENSITIVITY_OPTIONS[0] == "Slightly sensitive"
    check LEGACY_SENSITIVITY_OPTIONS[1] == "Moderately sensitive"
    check LEGACY_SENSITIVITY_OPTIONS[2] == "Very sensitive"
    check $nim_nvs_get_legacy_sensitivity(0) == "Slightly sensitive"
    check $nim_nvs_get_legacy_sensitivity(1) == "Moderately sensitive"
    check $nim_nvs_get_legacy_sensitivity(2) == "Very sensitive"

  test "Legacy cancel sound options list contains expected defaults":
    check LEGACY_CANCEL_OPTIONS.len == 18
    check LEGACY_CANCEL_OPTIONS[0] == "Match Wake Chime"
    check LEGACY_CANCEL_OPTIONS[1] == "Bell Ping"
    check LEGACY_CANCEL_OPTIONS[17] == "Aero Chime"
    check $nim_nvs_get_legacy_cancel(0) == "Match Wake Chime"
    check $nim_nvs_get_legacy_cancel(17) == "Aero Chime"
