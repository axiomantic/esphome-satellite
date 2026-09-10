## Dynamic microWakeWord Partition Loader in Nim
##
## Scans flash partitions, validates WakeModelHeader metadata, and maps custom models.

const
  WAKE_MAGIC* = 0x57414B45'u32  ## 'WAKE' in little-endian

type
  WakeModelHeader* {.packed.} = object
    magic*: uint32                 ## 0x57414B45 ("WAKE")
    headerVersion*: uint16        ## 1
    flags*: uint16                ## 0
    modelSize*: uint32            ## Size in bytes of the tflite model
    probabilityCutoff*: uint8     ## Quantized cutoff (0-255). 0 = default (102 for 0.40)
    slidingWindowSize*: uint8     ## Default 5
    tensorArenaKb*: uint16        ## Tensor arena size in KB (e.g. 40 = 40960 bytes)
    wakeWord*: array[32, char]    ## Null-terminated wake word string
    reserved*: array[16, uint8]   ## Padding to 64 bytes

  WakeModelInfo* = object
    valid*: bool
    modelSize*: uint32
    probabilityCutoff*: uint8
    slidingWindowSize*: int
    tensorArenaBytes*: int
    wakeWord*: string

proc parseWakeModelHeader*(
    data: openArray[uint8],
    partitionSize: uint32,
    slotIndex: int = 1
): WakeModelInfo =
  if data.len < sizeof(WakeModelHeader) or partitionSize < uint32(sizeof(WakeModelHeader)):
    return

  let hdr = cast[ptr WakeModelHeader](unsafeAddr data[0])
  if hdr.magic != WAKE_MAGIC:
    return

  let maxAllowed = partitionSize - uint32(sizeof(WakeModelHeader))
  if hdr.modelSize < 1000'u32 or hdr.modelSize > maxAllowed:
    return

  var nameBuf: string = ""
  for c in hdr.wakeWord:
    if c == '\0': break
    nameBuf.add(c)

  let name = if nameBuf.len > 0: nameBuf else: "Custom Wake Word " & $slotIndex
  let cutoff = if hdr.probabilityCutoff > 0'u8: hdr.probabilityCutoff else: 102'u8
  let window = if hdr.slidingWindowSize > 0'u8: int(hdr.slidingWindowSize) else: 5
  let arena = if hdr.tensorArenaKb > 0'u16: int(hdr.tensorArenaKb) * 1024 else: 40960

  result = WakeModelInfo(
    valid: true,
    modelSize: hdr.modelSize,
    probabilityCutoff: cutoff,
    slidingWindowSize: window,
    tensorArenaBytes: arena,
    wakeWord: name
  )

# C ABI bridge exports
proc nim_wake_loader_validate_header*(
    data: ptr uint8,
    partSize: uint32,
    slotIndex: cint,
    outModelSize: ptr uint32,
    outCutoff: ptr uint8,
    outWindow: ptr csize_t,
    outArena: ptr csize_t,
    outName: cstring,
    maxNameLen: csize_t
): bool {.exportc, cdecl.} =
  if data == nil or partSize < uint32(sizeof(WakeModelHeader)):
    return false

  let arr = cast[ptr UncheckedArray[uint8]](data)
  let info = parseWakeModelHeader(toOpenArray(arr, 0, int(partSize) - 1), partSize, int(slotIndex))
  if not info.valid:
    return false

  if outModelSize != nil: outModelSize[] = info.modelSize
  if outCutoff != nil: outCutoff[] = info.probabilityCutoff
  if outWindow != nil: outWindow[] = csize_t(info.slidingWindowSize)
  if outArena != nil: outArena[] = csize_t(info.tensorArenaBytes)

  if outName != nil and maxNameLen > 0:
    let copyLen = min(info.wakeWord.len, int(maxNameLen) - 1)
    if copyLen > 0:
      copyMem(outName, cstring(info.wakeWord), copyLen)
    cast[ptr UncheckedArray[char]](outName)[copyLen] = '\0'

  return true

proc calculateCutoffForSensitivity*(baseCutoff: uint8, level: string): uint8 =
  ## Scales quantized probability cutoff based on sensitivity level:
  ## "Extreme sensitivity" -> 0.45x cutoff (ultra-low threshold for high recall/female voice/distance)
  ## "Very sensitive" -> 0.70x cutoff (lower threshold, easier trigger)
  ## "Moderately sensitive" -> 1.0x cutoff (nominal baseline)
  ## "Slightly sensitive" -> 1.35x cutoff (higher threshold, strict rejection)
  case level
  of "Extreme sensitivity":
    let scaled = int(float(baseCutoff) * 0.45)
    uint8(max(10, min(scaled, 245)))
  of "Very sensitive":
    let scaled = int(float(baseCutoff) * 0.70)
    uint8(max(10, min(scaled, 245)))
  of "Slightly sensitive":
    let scaled = int(float(baseCutoff) * 1.35)
    uint8(max(10, min(scaled, 245)))
  else:
    baseCutoff

proc nim_wake_loader_scale_cutoff*(baseCutoff: uint8, levelCStr: cstring): uint8 {.exportc, cdecl.} =
  if levelCStr == nil: return baseCutoff
  calculateCutoffForSensitivity(baseCutoff, $levelCStr)

proc packWakeModelHeader*(
    name: string,
    modelSize: uint32,
    cutoff: uint8 = 102'u8,
    window: uint8 = 5'u8,
    arenaKb: uint16 = 40'u16
): array[64, uint8] =
  ## Packs a 64-byte WakeModelHeader matching the binary layout expected by wake_partition_loader.
  var hdr: WakeModelHeader
  hdr.magic = WAKE_MAGIC
  hdr.headerVersion = 1'u16
  hdr.flags = 0'u16
  hdr.modelSize = modelSize
  hdr.probabilityCutoff = if cutoff > 0'u8: cutoff else: 102'u8
  hdr.slidingWindowSize = if window > 0'u8: window else: 5'u8
  hdr.tensorArenaKb = if arenaKb > 0'u16: arenaKb else: 40'u16

  let nameLen = min(name.len, 31)
  for i in 0 ..< nameLen:
    hdr.wakeWord[i] = name[i]
  hdr.wakeWord[nameLen] = '\0'

  copyMem(addr result[0], addr hdr, sizeof(WakeModelHeader))

proc validateTfliteBuffer*(data: openArray[uint8]): bool =
  ## Validates that data starts with valid TFLite flatbuffer signature 'TFL3' at offset 4..7
  ## and has a reasonable size (>= 1000 bytes).
  if data.len < 1000:
    return false
  if data.len < 8:
    return false
  result = (data[4] == uint8('T') and
            data[5] == uint8('F') and
            data[6] == uint8('L') and
            data[7] == uint8('3'))

proc getSlotPartitionName*(slot: int): string =
  case slot
  of 1: "wake_model"
  of 2: "wake_model_2"
  of 3: "wake_model_3"
  else: ""

# C ABI bridge exports for installer
proc nim_wake_installer_pack_header*(
    outBuf: ptr uint8,
    maxLen: csize_t,
    name: cstring,
    modelSize: uint32,
    cutoff: uint8,
    window: uint8,
    arenaKb: uint16
): bool {.exportc, cdecl.} =
  if outBuf == nil or maxLen < csize_t(sizeof(WakeModelHeader)):
    return false
  let nameStr = if name != nil: $name else: "Custom Wake Word"
  let hdrBytes = packWakeModelHeader(nameStr, modelSize, cutoff, window, arenaKb)
  copyMem(outBuf, unsafeAddr hdrBytes[0], sizeof(WakeModelHeader))
  return true

proc nim_wake_installer_validate_tflite*(data: ptr uint8, len: csize_t): bool {.exportc, cdecl.} =
  if data == nil or len < 1000:
    return false
  let arr = cast[ptr UncheckedArray[uint8]](data)
  validateTfliteBuffer(toOpenArray(arr, 0, int(len) - 1))

proc nim_wake_installer_get_partition_name*(slot: cint, outBuf: cstring, maxLen: csize_t): bool {.exportc, cdecl.} =
  if outBuf == nil or maxLen == 0:
    return false
  let name = getSlotPartitionName(int(slot))
  if name.len == 0 or name.len >= int(maxLen):
    return false
  copyMem(outBuf, cstring(name), name.len)
  cast[ptr UncheckedArray[char]](outBuf)[name.len] = '\0'
  return true

