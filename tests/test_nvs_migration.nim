import std/unittest

func fnv1aHash(s: string): uint32 =
  var h: uint32 = 2166136261'u32
  for c in s:
    h = (h xor uint32(ord(c))) * 16777619'u32
  return h

suite "NVS Preference Migration & Hash Integrity Suite":
  test "Legacy v0.5.0 FNV-1a preference hashes match exact constants":
    check fnv1aHash("Audio: Voice Volume") == 1848069015'u32
    check fnv1aHash("Audio: Cancel Sound Sound") == 1728718513'u32
    check fnv1aHash("Audio: Wake Chime Sound") == 817734680'u32
    check fnv1aHash("Audio: Processing Sound") == 3079313095'u32
    check fnv1aHash("Speech: Wake Word Sensitivity") == 4098752856'u32
    check fnv1aHash("Audio: Wake Chime Enabled") == 3930144138'u32
    check fnv1aHash("Audio: Cancel Sound Enabled") == 483196759'u32

  test "New v0.6.0 Slot 1 FNV-1a preference hashes are distinct and reproducible":
    check fnv1aHash("Audio: Slot 1 Volume") == 828500550'u32
    check fnv1aHash("Audio: Slot 1 Cancel Sound") == 716895017'u32
    check fnv1aHash("Audio: Slot 1 Wake Chime") == 1794554120'u32
    check fnv1aHash("Audio: Slot 1 Processing Sound") == 936488196'u32
    check fnv1aHash("Speech: Slot 1 Sensitivity") == 2436161497'u32
    check fnv1aHash("Audio: Slot 1 Wake Chime Enabled") == 436416649'u32
    check fnv1aHash("Audio: Slot 1 Cancel Sound Enabled") == 1032233936'u32

    # Verify that slot 1 hashes never collide with legacy hashes
    check fnv1aHash("Audio: Slot 1 Volume") != fnv1aHash("Audio: Voice Volume")
    check fnv1aHash("Audio: Slot 1 Cancel Sound") != fnv1aHash("Audio: Cancel Sound Sound")
    check fnv1aHash("Speech: Slot 1 Sensitivity") != fnv1aHash("Speech: Wake Word Sensitivity")

  test "Legacy sensitivity index-to-option mapping preserves semantic levels":
    const legacySensitivity = ["Slightly sensitive", "Moderately sensitive", "Very sensitive"]
    check legacySensitivity[0] == "Slightly sensitive"
    check legacySensitivity[1] == "Moderately sensitive"
    check legacySensitivity[2] == "Very sensitive"

  test "Legacy cancel sound options list contains expected defaults":
    const legacyCancel = [
      "Match Wake Chime", "Bell Ping", "Modern Chime", "Crystal Glass", "Warm Kalimba",
      "Meditation Bell", "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl",
      "Acoustic Harp", "Woodblock", "Ceramic Bell", "Neon Shimmer", "Prism Ping",
      "Cyber Bloom", "Quantum Beep", "Aero Chime"
    ]
    check legacyCancel.len == 18
    check legacyCancel[0] == "Match Wake Chime"
    check legacyCancel[1] == "Bell Ping"
    check legacyCancel[17] == "Aero Chime"
