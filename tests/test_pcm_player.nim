import std/unittest
import ../src/pcm_sound_player

suite "PCM Sound Player & Decoder Suite (TDD)":
  test "CAUD header and entry struct sizes":
    check sizeof(CustomAudioHeader) == 32
    check sizeof(CustomAudioEntry) == 48

  test "RIFF WAVE header parser identifies 16kHz mono 16-bit PCM":
    var wav = newSeq[uint8](44 + 320)
    # "RIFF"
    wav[0] = ord('R'); wav[1] = ord('I'); wav[2] = ord('F'); wav[3] = ord('F')
    # File size - 8
    let fileSize = uint32(wav.len - 8)
    copyMem(addr wav[4], unsafeAddr fileSize, 4)
    # "WAVE"
    wav[8] = ord('W'); wav[9] = ord('A'); wav[10] = ord('V'); wav[11] = ord('E')
    # "fmt "
    wav[12] = ord('f'); wav[13] = ord('m'); wav[14] = ord('t'); wav[15] = ord(' ')
    # Subchunk1Size = 16
    let sub1Size = 16'u32
    copyMem(addr wav[16], unsafeAddr sub1Size, 4)
    # AudioFormat = 1 (PCM)
    let fmt = 1'u16
    copyMem(addr wav[20], unsafeAddr fmt, 2)
    # NumChannels = 1
    let channels = 1'u16
    copyMem(addr wav[22], unsafeAddr channels, 2)
    # SampleRate = 16000
    let sampleRate = 16000'u32
    copyMem(addr wav[24], unsafeAddr sampleRate, 4)
    # ByteRate = 32000
    let byteRate = 32000'u32
    copyMem(addr wav[28], unsafeAddr byteRate, 4)
    # BlockAlign = 2
    let blockAlign = 2'u16
    copyMem(addr wav[32], unsafeAddr blockAlign, 2)
    # BitsPerSample = 16
    let bits = 16'u16
    copyMem(addr wav[34], unsafeAddr bits, 2)
    # "data"
    wav[36] = ord('d'); wav[37] = ord('a'); wav[38] = ord('t'); wav[39] = ord('a')
    # Subchunk2Size = 320
    let dataSize = 320'u32
    copyMem(addr wav[40], unsafeAddr dataSize, 4)

    let info = parseWavHeader(wav)
    check info.valid
    check info.channels == 1'u16
    check info.sampleRate == 16000'u32
    check info.bitsPerSample == 16'u16
    check info.pcmOffset == 44
    check info.pcmLen == 320

  test "IMA-ADPCM decoding expands 4:1 into valid 16-bit PCM":
    # 4 bytes of ADPCM = 8 samples of PCM
    var adpcm: array[4, uint8] = [0x00'u8, 0x00'u8, 0x11'u8, 0x22'u8]
    var pcm: seq[int16]
    decodeAdpcmBuffer(adpcm, pcm, volume = 1.0'f32)
    check pcm.len == 8
    # Exact decoded samples from standard IMA-ADPCM spec:
    check pcm == @[0'i16, 0, 0, 0, 1, 2, 5, 8]

    # Test half volume scaling:
    var pcmHalf: seq[int16]
    decodeAdpcmBuffer(adpcm, pcmHalf, volume = 0.5'f32)
    check pcmHalf == @[0'i16, 0, 0, 0, 0, 1, 2, 4]

    # Test negative delta decoding:
    var adpcmNeg: array[2, uint8] = [0x88'u8, 0x99'u8]
    var pcmNeg: seq[int16]
    decodeAdpcmBuffer(adpcmNeg, pcmNeg, volume = 1.0'f32)
    check pcmNeg == @[0'i16, 0, -1, -2]

    # Test C ABI chunk decoding with state preservation:
    var valprev: int16 = 0
    var index: int8 = 0
    var outBuf: array[8, int16]
    let written = nim_pcm_decode_adpcm_chunk(
      addr adpcm[0],
      csize_t(adpcm.len),
      addr outBuf[0],
      1.0'f32,
      addr valprev,
      addr index
    )
    check written == 8
    check outBuf == [0'i16, 0, 0, 0, 1, 2, 5, 8]
    check valprev == 8'i16
    check index == 0'i8

  test "CAUD partition parsing extracts sound entries":
    var caud = newSeq[uint8](32 + 48 * 2)
    # Magic CAUD = 0x44554143 ('C','A','U','D' in le: 43 41 55 44)
    caud[0] = 0x43'u8; caud[1] = 0x41'u8; caud[2] = 0x55'u8; caud[3] = 0x44'u8
    # version = 1
    caud[4] = 1'u8; caud[5] = 0'u8
    # count = 2
    caud[6] = 2'u8; caud[7] = 0'u8
    
    # Entry 0 name: "Test Bell"
    let name0 = "Test Bell"
    for i in 0 ..< name0.len: caud[32 + i] = uint8(name0[i])
    # offset = 1000, size = 500
    let off0 = 1000'u32
    let sz0 = 500'u32
    copyMem(addr caud[32 + 32], unsafeAddr off0, 4)
    copyMem(addr caud[32 + 36], unsafeAddr sz0, 4)

    # Entry 1 name: "Chime Two"
    let name1 = "Chime Two"
    for i in 0 ..< name1.len: caud[32 + 48 + i] = uint8(name1[i])
    let off1 = 1500'u32
    let sz1 = 600'u32
    copyMem(addr caud[32 + 48 + 32], unsafeAddr off1, 4)
    copyMem(addr caud[32 + 48 + 36], unsafeAddr sz1, 4)

    let entries = parseCaudEntries(caud, uint32(caud.len + 2000))
    check entries.len == 2
    check entries[0].name == "Test Bell"
    check entries[0].offset == 1000'u32
    check entries[0].size == 500'u32
    check entries[1].name == "Chime Two"
