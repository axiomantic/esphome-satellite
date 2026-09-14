import std/unittest
import ../src/audio_stream_tracker

suite "DMA Audio Stream Typestate Tracker Suite (TDD)":
  setup:
    nim_dma_stream_reset()

  test "DmaStreamIdle initialization and DmaStreamPlaying start":
    let idle = initDmaStreamIdle()
    check idle is DmaStreamIdle

    let playing = startStream(
      idle,
      dskChime,
      maxDurationMs = 5000'u32,
      inactivityTimeoutMs = 2000'u32,
      isLoop = false,
      startMs = 1000'u32
    )
    check playing is DmaStreamPlaying
    check playing.kind == dskChime
    check playing.maxDurationMs == 5000'u32
    check playing.inactivityTimeoutMs == 2000'u32
    check playing.startMs == 1000'u32
    check playing.lastChunkMs == 1000'u32
    check playing.bytesWritten == 0'u64
    check playing.isLoop == false
    check playing.elapsedMs == 0'u32

  test "Default parameters for startStream":
    let idle = initDmaStreamIdle()
    let playing = startStream(idle, dskCancel, 3000'u32)
    check playing.kind == dskCancel
    check playing.maxDurationMs == 3000'u32
    check playing.inactivityTimeoutMs == 2000'u32
    check playing.isLoop == false
    check playing.startMs == 0'u32

  test "feedBytes updates chunk time, elapsed time, and total bytes":
    let idle = initDmaStreamIdle()
    var playing = startStream(idle, dskTts, 60000'u32, 3000'u32, false, 500'u32)

    feedBytes(playing, 512, 700'u32)
    check playing.bytesWritten == 512'u64
    check playing.lastChunkMs == 700'u32
    check playing.elapsedMs == 200'u32

    feedBytes(playing, 1024, 1200'u32)
    check playing.bytesWritten == 1536'u64
    check playing.lastChunkMs == 1200'u32
    check playing.elapsedMs == 700'u32

  test "finishStream transitions playing typestate to idle":
    let idle = initDmaStreamIdle()
    let playing = startStream(idle, dskChime, 5000'u32)
    let finished = finishStream(playing)
    check finished is DmaStreamIdle

  test "abortStream transitions playing typestate to idle":
    let idle = initDmaStreamIdle()
    let playing = startStream(idle, dskProcessing, 25000'u32, isLoop = true)
    let aborted = abortStream(playing)
    check aborted is DmaStreamIdle

  test "tickStream remains active while within duration and activity bounds":
    let idle = initDmaStreamIdle()
    var playing = startStream(idle, dskChime, 5000'u32, 2000'u32, false, 1000'u32)

    let res1 = tickStream(playing, 1500'u32)
    check res1.active == true
    check res1.timedOut == false
    check res1.transitionedToIdle == false
    check playing.elapsedMs == 500'u32

    feedBytes(playing, 256, 1800'u32)
    let res2 = tickStream(playing, 2200'u32)
    check res2.active == true
    check res2.timedOut == false
    check res2.transitionedToIdle == false
    check playing.elapsedMs == 1200'u32

  test "tickStream triggers deadline lease timeout":
    let idle = initDmaStreamIdle()
    var playing = startStream(idle, dskChime, 3000'u32, 2000'u32, false, 1000'u32)

    # Keep feeding to prevent inactivity timeout
    feedBytes(playing, 128, 1500'u32)
    feedBytes(playing, 128, 2500'u32)
    feedBytes(playing, 128, 3500'u32)

    # At 3999ms, elapsed is 2999ms (< 3000ms deadline)
    let resPre = tickStream(playing, 3999'u32)
    check resPre.active == true
    check resPre.timedOut == false

    # At 4000ms, elapsed is 3000ms (>= 3000ms deadline)
    let resPost = tickStream(playing, 4000'u32)
    check resPost.active == false
    check resPost.timedOut == true
    check resPost.transitionedToIdle == true

  test "tickStream triggers inactivity stall timeout":
    let idle = initDmaStreamIdle()
    var playing = startStream(idle, dskTts, 60000'u32, 2000'u32, false, 1000'u32)

    feedBytes(playing, 512, 1200'u32)
    let resOk = tickStream(playing, 2500'u32)
    check resOk.active == true
    check resOk.timedOut == false

    # At 3201ms, idle time since 1200ms is 2001ms (>= 2000ms inactivityTimeoutMs)
    let resStall = tickStream(playing, 3201'u32)
    check resStall.active == false
    check resStall.timedOut == true
    check resStall.transitionedToIdle == true

  test "Loop without data feeding ignores inactivity but honors max duration":
    let idle = initDmaStreamIdle()
    # isLoop = true, bytesWritten = 0
    var playing = startStream(idle, dskProcessing, 10000'u32, 1500'u32, true, 1000'u32)

    # At 5000ms (4000ms idle > 1500ms inactivity), should NOT stall because loop without data feeding
    let res1 = tickStream(playing, 5000'u32)
    check res1.active == true
    check res1.timedOut == false

    # At 11000ms (elapsed 10000ms >= 10000ms deadline), should time out on deadline
    let res2 = tickStream(playing, 11000'u32)
    check res2.active == false
    check res2.timedOut == true
    check res2.transitionedToIdle == true

  test "Loop with data feeding detects stall when chunk stream ceases":
    let idle = initDmaStreamIdle()
    # isLoop = true, bytesWritten > 0
    var playing = startStream(idle, dskProcessing, 25000'u32, 2000'u32, true, 1000'u32)

    feedBytes(playing, 256, 1200'u32)
    let resActive = tickStream(playing, 2000'u32)
    check resActive.active == true

    # At 3201ms (2001ms since chunk at 1200ms >= 2000ms), stall is detected
    let resStall = tickStream(playing, 3201'u32)
    check resStall.active == false
    check resStall.timedOut == true

suite "Runtime C ABI Wrapper Suite":
  setup:
    nim_dma_stream_reset()

  test "C ABI functions track state transitions and kinds":
    check nim_dma_stream_is_active() == false
    check nim_dma_stream_get_kind() == cint(ord(dskNone))
    check nim_dma_stream_tick(1000'u32) == 0'i32 # idle

    let started = nim_dma_stream_start_at(cint(ord(dskChime)), 5000'u32, 2000'u32, false, 1000'u32)
    check started == true
    check nim_dma_stream_is_active() == true
    check nim_dma_stream_get_kind() == cint(ord(dskChime))
    check nim_dma_stream_get_elapsed_ms(1500'u32) == 500'u32

    nim_dma_stream_feed_at(512'u, 1500'u32)
    check nim_dma_stream_tick(2000'u32) == 1'i32 # active

    nim_dma_stream_finish()
    check nim_dma_stream_is_active() == false
    check nim_dma_stream_get_kind() == cint(ord(dskNone))
    check nim_dma_stream_tick(2500'u32) == 0'i32 # idle

  test "C ABI tick returns 2 on timeout and auto-resets to idle":
    let started = nim_dma_stream_start_at(cint(ord(dskCancel)), 2000'u32, 1000'u32, false, 1000'u32)
    check started == true
    check nim_dma_stream_is_active() == true

    # Tick at 2500ms (elapsed 1500ms, idle 1500ms >= 1000ms inactivity)
    let tickRes = nim_dma_stream_tick(2500'u32)
    check tickRes == 2'i32 # timed out and aborted
    check nim_dma_stream_is_active() == false
    check nim_dma_stream_get_kind() == cint(ord(dskNone))

    # Next tick is idle (0)
    check nim_dma_stream_tick(2600'u32) == 0'i32

  test "Starting a stream while active cleanly replaces the prior stream":
    check nim_dma_stream_start_at(cint(ord(dskChime)), 5000'u32, 2000'u32, false, 1000'u32) == true
    check nim_dma_stream_get_kind() == cint(ord(dskChime))

    # Start TTS stream
    check nim_dma_stream_start_at(cint(ord(dskTts)), 60000'u32, 3000'u32, false, 2000'u32) == true
    check nim_dma_stream_get_kind() == cint(ord(dskTts))
    check nim_dma_stream_get_elapsed_ms(2500'u32) == 500'u32

    nim_dma_stream_abort()
    check nim_dma_stream_is_active() == false

suite "DMA Audio Stream - 32-bit Timer Rollover (TDD)":
  setup:
    nim_dma_stream_reset()

  test "diffMs calculates elapsed time across 0xFFFFFFFF boundary":
    # Normal case: now >= since
    check diffMs(1500'u32, 1000'u32) == 500'u32
    check diffMs(1000'u32, 1000'u32) == 0'u32

    # Rollover case: since is near 0xFFFFFFFF, now is past 0
    let nearMax = 0xFFFFFFF0'u32
    let afterZero = 1000'u32
    # Elapsed should be 16 + 1000 = 1016ms
    check diffMs(afterZero, nearMax) == 1016'u32

    # Immediate wraparound
    check diffMs(0'u32, 0xFFFFFFFF'u32) == 1'u32

  test "Stream tracking and feeding across 0xFFFFFFFF boundary":
    let startTimestamp = 0xFFFFFFF0'u32
    let idle = initDmaStreamIdle()
    var playing = startStream(idle, dskTts, 60000'u32, 2000'u32, false, startTimestamp)

    # 500ms later, time has wrapped around to 484 (0xFFFFFFF0 + 500 = 484)
    let time1 = 484'u32
    feedBytes(playing, 512, time1)
    check playing.elapsedMs == 500'u32
    check playing.lastChunkMs == 484'u32
    check playing.bytesWritten == 512'u64

    # Tick at 1000ms elapsed (time = 984'u32)
    let res1 = tickStream(playing, 984'u32)
    check res1.active == true
    check res1.timedOut == false
    check playing.elapsedMs == 1000'u32

  test "C ABI functions handle timer rollover correctly":
    let startTimestamp = 0xFFFFFFF0'u32
    check nim_dma_stream_start_at(cint(ord(dskChime)), 5000'u32, 2000'u32, false, startTimestamp) == true
    check nim_dma_stream_is_active() == true

    # Check elapsed time across boundary
    check nim_dma_stream_get_elapsed_ms(1000'u32) == 1016'u32

    # Feed across boundary
    nim_dma_stream_feed_at(256'u, 1000'u32)
    check nim_dma_stream_tick(1500'u32) == 1'i32 # active (500ms since feed, 1516ms elapsed)

    # Tick after lease timeout (5000ms lease expires at start + 5000 = 4984)
    check nim_dma_stream_tick(5000'u32) == 2'i32 # timed out
    check nim_dma_stream_is_active() == false

