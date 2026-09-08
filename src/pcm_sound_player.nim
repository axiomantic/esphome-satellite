## Embedded PCM & IMA-ADPCM Sound Player in Nim
##
## Implements CAUD partition metadata parsing, RIFF/WAVE header parsing,
## and zero-heap IMA-ADPCM 4:1 decompression with volume scaling.

const
  CAUD_MAGIC* = 0x44554143'u32  ## 'CAUD' in little-endian

  # Standard IMA/DVI ADPCM Step Size and Index tables
  INDEX_TABLE*: array[16, int8] = [
    -1'i8, -1, -1, -1, 2, 4, 6, 8,
    -1'i8, -1, -1, -1, 2, 4, 6, 8
  ]

  STEP_SIZE_TABLE*: array[89, int16] = [
    7'i16, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
  ]

type
  CustomAudioHeader* {.packed.} = object
    magic*: uint32         ## 0x44554143 ("CAUD")
    version*: uint16       ## 1
    count*: uint16         ## Number of sound entries
    reserved*: array[24, uint8]

  CustomAudioEntry* {.packed.} = object
    name*: array[32, char] ## Null-terminated sound name
    offset*: uint32        ## Byte offset from partition start
    size*: uint32          ## Byte length of WAV file
    reserved*: array[8, uint8]

  ParsedAudioEntry* = object
    name*: string
    offset*: uint32
    size*: uint32

  WavHeaderInfo* = object
    valid*: bool
    channels*: uint16
    sampleRate*: uint32
    bitsPerSample*: uint16
    pcmOffset*: int
    pcmLen*: int

proc parseWavHeader*(data: openArray[uint8]): WavHeaderInfo =
  if data.len < 44: return

  # Check "RIFF" and "WAVE"
  if data[0] != ord('R') or data[1] != ord('I') or data[2] != ord('F') or data[3] != ord('F'):
    return
  if data[8] != ord('W') or data[9] != ord('A') or data[10] != ord('V') or data[11] != ord('E'):
    return

  var offset = 12
  var foundFmt = false
  var foundData = false

  while offset + 8 <= data.len:
    var chunkSize: uint32
    copyMem(addr chunkSize, unsafeAddr data[offset + 4], 4)

    if data[offset] == ord('f') and data[offset+1] == ord('m') and data[offset+2] == ord('t') and data[offset+3] == ord(' '):
      if chunkSize >= 16:
        var format: uint16
        copyMem(addr format, unsafeAddr data[offset + 8], 2)
        if format != 1'u16: # PCM only
          return
        copyMem(addr result.channels, unsafeAddr data[offset + 10], 2)
        copyMem(addr result.sampleRate, unsafeAddr data[offset + 12], 4)
        copyMem(addr result.bitsPerSample, unsafeAddr data[offset + 22], 2)
        foundFmt = true
    elif data[offset] == ord('d') and data[offset+1] == ord('a') and data[offset+2] == ord('t') and data[offset+3] == ord('a'):
      result.pcmOffset = offset + 8
      let available = data.len - (offset + 8)
      result.pcmLen = min(int(chunkSize), available)
      foundData = true
      break

    offset += 8 + int(chunkSize)
    if chunkSize mod 2 != 0:
      offset += 1

  if foundFmt and foundData and result.pcmLen > 0:
    result.valid = true

proc decodeAdpcmNibble*(nibble: uint8, valprev: var int16, index: var int8): int16 {.inline.} =
  let delta = nibble and 0x0F'u8
  var step = int32(STEP_SIZE_TABLE[index])
  var diff = step shr 3
  if (delta and 4'u8) != 0'u8: diff += step
  if (delta and 2'u8) != 0'u8: diff += (step shr 1)
  if (delta and 1'u8) != 0'u8: diff += (step shr 2)

  var vp = int32(valprev)
  if (delta and 8'u8) != 0'u8:
    vp -= diff
  else:
    vp += diff

  if vp > 32767: vp = 32767
  elif vp < -32768: vp = -32768
  valprev = int16(vp)

  var idx = int(index) + int(INDEX_TABLE[delta])
  if idx < 0: idx = 0
  elif idx > 88: idx = 88
  index = int8(idx)

  result = valprev

proc decodeAdpcmBuffer*(adpcmData: openArray[uint8], outPcm: var seq[int16], volume: float32 = 1.0'f32) =
  outPcm.setLen(adpcmData.len * 2)
  var valprev: int16 = 0
  var index: int8 = 0
  let scale = clamp(volume, 0.0'f32, 1.0'f32)

  var outIdx = 0
  for b in adpcmData:
    let s0 = decodeAdpcmNibble(b and 0x0F'u8, valprev, index)
    outPcm[outIdx] = if scale < 0.999'f32: int16(float32(s0) * scale) else: s0
    outIdx += 1

    let s1 = decodeAdpcmNibble((b shr 4) and 0x0F'u8, valprev, index)
    outPcm[outIdx] = if scale < 0.999'f32: int16(float32(s1) * scale) else: s1
    outIdx += 1

proc parseCaudEntries*(data: openArray[uint8], partitionSize: uint32): seq[ParsedAudioEntry] =
  if data.len < sizeof(CustomAudioHeader) or partitionSize < uint32(sizeof(CustomAudioHeader)):
    return

  let hdr = cast[ptr CustomAudioHeader](unsafeAddr data[0])
  if hdr.magic != CAUD_MAGIC:
    return

  let maxEntries = (partitionSize - uint32(sizeof(CustomAudioHeader))) div uint32(sizeof(CustomAudioEntry))
  let count = min(int(hdr.count), int(maxEntries))

  let entriesBase = sizeof(CustomAudioHeader)
  for i in 0 ..< count:
    let entryOffset = entriesBase + i * sizeof(CustomAudioEntry)
    if entryOffset + sizeof(CustomAudioEntry) > data.len:
      break
    let entry = cast[ptr CustomAudioEntry](unsafeAddr data[entryOffset])
    if entry.offset >= partitionSize or (entry.offset + entry.size) > partitionSize or entry.size < 44:
      continue

    var nameStr = ""
    for c in entry.name:
      if c == '\0': break
      nameStr.add(c)

    result.add(ParsedAudioEntry(
      name: nameStr,
      offset: entry.offset,
      size: entry.size
    ))

# C ABI bridge exports
proc nim_pcm_parse_wav*(
    data: ptr uint8,
    len: csize_t,
    outSampleRate: ptr uint32,
    outChannels: ptr uint16,
    outBits: ptr uint16,
    outPcmOffset: ptr csize_t,
    outPcmLen: ptr csize_t
): bool {.exportc, cdecl.} =
  if data == nil or len < 44: return false
  let arr = cast[ptr UncheckedArray[uint8]](data)
  let info = parseWavHeader(toOpenArray(arr, 0, int(len) - 1))
  if not info.valid: return false

  if outSampleRate != nil: outSampleRate[] = info.sampleRate
  if outChannels != nil: outChannels[] = info.channels
  if outBits != nil: outBits[] = info.bitsPerSample
  if outPcmOffset != nil: outPcmOffset[] = csize_t(info.pcmOffset)
  if outPcmLen != nil: outPcmLen[] = csize_t(info.pcmLen)
  return true

proc nim_pcm_decode_adpcm_chunk*(
    adpcmData: ptr uint8,
    adpcmLen: csize_t,
    outSamples: ptr int16,
    volume: cfloat,
    valprev: ptr int16,
    index: ptr int8
): csize_t {.exportc, cdecl.} =
  if adpcmData == nil or outSamples == nil or adpcmLen == 0:
    return 0

  let inArr = cast[ptr UncheckedArray[uint8]](adpcmData)
  let outArr = cast[ptr UncheckedArray[int16]](outSamples)
  var vp: int16 = if valprev != nil: valprev[] else: 0'i16
  var idx: int8 = if index != nil: index[] else: 0'i8
  let scale = clamp(float32(volume), 0.0'f32, 1.0'f32)

  var written: csize_t = 0
  for i in 0 ..< int(adpcmLen):
    let b = inArr[i]
    let s0 = decodeAdpcmNibble(b and 0x0F'u8, vp, idx)
    outArr[written] = if scale < 0.999'f32: int16(float32(s0) * scale) else: s0
    written += 1

    let s1 = decodeAdpcmNibble((b shr 4) and 0x0F'u8, vp, idx)
    outArr[written] = if scale < 0.999'f32: int16(float32(s1) * scale) else: s1
    written += 1

  if valprev != nil: valprev[] = vp
  if index != nil: index[] = idx
  return written
