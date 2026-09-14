## DMA Audio Stream Typestate Tracker in Nim
##
## Implements compile-time verified typestates and bounded lease deadlines
## for audio playback streams (chimes, processing loops, cancel cues, TTS, media).
## Prevents deadlocks and zombie speaker states if hardware/driver events drop.

when not declared(millis):
  import nim_esphome

type
  DmaStreamKind* = enum
    dskNone = 0,
    dskChime = 1,
    dskProcessing = 2,
    dskCancel = 3,
    dskTts = 4,
    dskMedia = 5

  DmaStreamIdle* = object

  DmaStreamPlaying* = object
    kind*: DmaStreamKind
    maxDurationMs*: uint32
    inactivityTimeoutMs*: uint32
    elapsedMs*: uint32
    startMs*: uint32
    lastChunkMs*: uint32
    bytesWritten*: uint64
    isLoop*: bool

  TrackerStateKind = enum
    tskIdle,
    tskPlaying

proc initDmaStreamIdle*(): DmaStreamIdle =
  DmaStreamIdle()

proc startStream*(
    idle: DmaStreamIdle,
    kind: DmaStreamKind,
    maxDurationMs: uint32,
    inactivityTimeoutMs: uint32 = 2000'u32,
    isLoop: bool = false,
    startMs: uint32 = 0'u32
): DmaStreamPlaying =
  DmaStreamPlaying(
    kind: kind,
    maxDurationMs: maxDurationMs,
    inactivityTimeoutMs: inactivityTimeoutMs,
    elapsedMs: 0'u32,
    startMs: startMs,
    lastChunkMs: startMs,
    bytesWritten: 0'u64,
    isLoop: isLoop
  )

proc feedBytes*(playing: var DmaStreamPlaying, bytes: int, currentMs: uint32) =
  if bytes > 0:
    playing.bytesWritten += uint64(bytes)
  playing.lastChunkMs = currentMs
  if currentMs >= playing.startMs:
    playing.elapsedMs = currentMs - playing.startMs
  else:
    playing.elapsedMs = (not 0'u32) - playing.startMs + currentMs + 1'u32

proc tickStream*(
    playing: var DmaStreamPlaying,
    currentMs: uint32
): tuple[active: bool, timedOut: bool, transitionedToIdle: bool] =
  let elapsed = if currentMs >= playing.startMs:
                  currentMs - playing.startMs
                else:
                  (not 0'u32) - playing.startMs + currentMs + 1'u32
  playing.elapsedMs = elapsed

  let idleTime = if currentMs >= playing.lastChunkMs:
                   currentMs - playing.lastChunkMs
                 else:
                   (not 0'u32) - playing.lastChunkMs + currentMs + 1'u32

  let deadlineReached = (playing.maxDurationMs > 0'u32) and (elapsed >= playing.maxDurationMs)
  let stallDetected = (playing.inactivityTimeoutMs > 0'u32) and
                      not (playing.isLoop and playing.bytesWritten == 0'u64) and
                      (idleTime >= playing.inactivityTimeoutMs)

  if deadlineReached or stallDetected:
    result = (active: false, timedOut: true, transitionedToIdle: true)
  else:
    result = (active: true, timedOut: false, transitionedToIdle: false)

proc finishStream*(playing: DmaStreamPlaying): DmaStreamIdle =
  DmaStreamIdle()

proc abortStream*(playing: DmaStreamPlaying): DmaStreamIdle =
  DmaStreamIdle()

# Global runtime tracker state
var
  gTrackerState: TrackerStateKind = tskIdle
  gIdleState: DmaStreamIdle = DmaStreamIdle()
  gPlayingState: DmaStreamPlaying

proc nim_dma_stream_start_at*(
    kind: cint,
    max_duration_ms: uint32,
    inactivity_timeout_ms: uint32,
    is_loop: bool,
    now_ms: uint32
): bool =
  if gTrackerState == tskPlaying:
    gIdleState = abortStream(gPlayingState)
  let streamKind = if kind >= ord(low(DmaStreamKind)) and kind <= ord(high(DmaStreamKind)):
                     DmaStreamKind(kind)
                   else:
                     dskNone
  gPlayingState = startStream(gIdleState, streamKind, max_duration_ms, inactivity_timeout_ms, is_loop, now_ms)
  gTrackerState = tskPlaying
  result = true

proc nim_dma_stream_feed_at*(bytes: csize_t, now_ms: uint32) =
  if gTrackerState == tskPlaying:
    feedBytes(gPlayingState, int(bytes), now_ms)

proc nim_dma_stream_reset*() =
  if gTrackerState == tskPlaying:
    gIdleState = abortStream(gPlayingState)
  gTrackerState = tskIdle

# C ABI Exports
proc nim_dma_stream_start*(
    kind: cint,
    max_duration_ms: uint32,
    inactivity_timeout_ms: uint32,
    is_loop: bool
): bool {.exportc, cdecl.} =
  nim_dma_stream_start_at(kind, max_duration_ms, inactivity_timeout_ms, is_loop, millis())

proc nim_dma_stream_feed*(bytes: csize_t) {.exportc, cdecl.} =
  nim_dma_stream_feed_at(bytes, millis())

proc nim_dma_stream_finish*() {.exportc, cdecl.} =
  if gTrackerState == tskPlaying:
    gIdleState = finishStream(gPlayingState)
    gTrackerState = tskIdle

proc nim_dma_stream_abort*() {.exportc, cdecl.} =
  if gTrackerState == tskPlaying:
    gIdleState = abortStream(gPlayingState)
    gTrackerState = tskIdle

proc nim_dma_stream_tick*(now_ms: uint32): cint {.exportc, cdecl.} =
  if gTrackerState == tskIdle:
    return 0'i32
  let res = tickStream(gPlayingState, now_ms)
  if res.timedOut:
    gIdleState = abortStream(gPlayingState)
    gTrackerState = tskIdle
    return 2'i32
  else:
    return 1'i32

proc nim_dma_stream_is_active*(): bool {.exportc, cdecl.} =
  return gTrackerState == tskPlaying

proc nim_dma_stream_get_kind*(): cint {.exportc, cdecl.} =
  if gTrackerState == tskPlaying:
    return cint(ord(gPlayingState.kind))
  else:
    return cint(ord(dskNone))

proc nim_dma_stream_get_elapsed_ms*(now_ms: uint32): uint32 {.exportc, cdecl.} =
  if gTrackerState == tskPlaying:
    if now_ms >= gPlayingState.startMs:
      return now_ms - gPlayingState.startMs
    else:
      return gPlayingState.elapsedMs
  else:
    return 0'u32
