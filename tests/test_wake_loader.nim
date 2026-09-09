import std/unittest

import ../src/wake_partition_loader

suite "Wake Partition Loader Suite (TDD)":
  test "WakeModelHeader packed size":
    check sizeof(WakeModelHeader) == 64

  test "Valid wake model header parses correctly":
    var raw = newSeq[uint8](64 + 5000)
    # Magic 0x57414B45 in little-endian: 45 4B 41 57
    raw[0] = 0x45'u8
    raw[1] = 0x4B'u8
    raw[2] = 0x41'u8
    raw[3] = 0x57'u8
    
    # header_version = 1
    raw[4] = 1'u8
    raw[5] = 0'u8
    
    # model_size = 5000 (0x1388)
    raw[8] = 0x88'u8
    raw[9] = 0x13'u8
    raw[10] = 0'u8
    raw[11] = 0'u8
    
    # cutoff = 150
    raw[12] = 150'u8
    # sliding window = 7
    raw[13] = 7'u8
    # arena kb = 48
    raw[14] = 48'u8
    raw[15] = 0'u8
    
    # wake_word = "Hey Computer"
    let name = "Hey Computer"
    for i in 0 ..< name.len:
      raw[16 + i] = uint8(name[i])
      
    let parsed = parseWakeModelHeader(raw, uint32(raw.len), slotIndex = 1)
    check parsed.valid
    check parsed.modelSize == 5000'u32
    check parsed.probabilityCutoff == 150'u8
    check parsed.slidingWindowSize == 7
    check parsed.tensorArenaBytes == 48 * 1024
    check parsed.wakeWord == "Hey Computer"

  test "Invalid magic is rejected":
    var raw = newSeq[uint8](64 + 2000)
    raw[0] = 0x11'u8
    let parsed = parseWakeModelHeader(raw, uint32(raw.len), slotIndex = 1)
    check not parsed.valid

  test "Model size out of partition bounds is rejected":
    var raw = newSeq[uint8](64 + 2000)
    # Magic
    raw[0] = 0x45'u8; raw[1] = 0x4B'u8; raw[2] = 0x41'u8; raw[3] = 0x57'u8
    # model_size = 100000 (exceeds raw.len)
    raw[8] = 0xA0'u8; raw[9] = 0x86'u8; raw[10] = 0x01'u8; raw[11] = 0'u8
    let parsed = parseWakeModelHeader(raw, uint32(raw.len), slotIndex = 1)
    check not parsed.valid

  test "Empty name falls back to slot index name":
    var raw = newSeq[uint8](64 + 2000)
    raw[0] = 0x45'u8; raw[1] = 0x4B'u8; raw[2] = 0x41'u8; raw[3] = 0x57'u8
    # model_size = 2000
    raw[8] = 0xD0'u8; raw[9] = 0x07'u8; raw[10] = 0'u8; raw[11] = 0'u8
    let parsed = parseWakeModelHeader(raw, uint32(raw.len), slotIndex = 3)
    check parsed.valid
    check parsed.wakeWord == "Custom Wake Word 3"

  test "Wake word sensitivity cutoff scaling":
    let baseCutoff: uint8 = 100
    check calculateCutoffForSensitivity(baseCutoff, "Extreme sensitivity") == 45'u8
    check calculateCutoffForSensitivity(baseCutoff, "Very sensitive") == 70'u8
    check calculateCutoffForSensitivity(baseCutoff, "Moderately sensitive") == 100'u8
    check calculateCutoffForSensitivity(baseCutoff, "Slightly sensitive") == 135'u8
    check calculateCutoffForSensitivity(baseCutoff, "Unknown") == 100'u8
