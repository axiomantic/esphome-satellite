import std/unittest
import ../src/nim_esphome_satellite

var gTestAbortTriggered = false

proc testHardwareAbortCb() {.cdecl.} =
  gTestAbortTriggered = true

suite "Satellite Watchdog Loop & Typestate Integration (TDD)":
  setup:
    nim_satellite_reset_for_test()
    gTestAbortTriggered = false
    nim_satellite_register_hardware_abort_cb(testHardwareAbortCb)

  test "rsWoken 5s timeout transitions to rsPipelineError (held for 2s) and then to rsIdle":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_wake_word("assistant", 0)
    check nim_satellite_get_state() == ord(rsWoken)

    # Initial tick at 1000ms establishes state entered timestamp
    satelliteLoop(1000'u32)
    check nim_satellite_get_state() == ord(rsWoken)
    check not gTestAbortTriggered

    # At 5999ms (4999ms elapsed < 5000ms), remains in rsWoken
    satelliteLoop(5999'u32)
    check nim_satellite_get_state() == ord(rsWoken)
    check not gTestAbortTriggered

    # At 6000ms (5000ms elapsed >= 5000ms), watchdog fires
    satelliteLoop(6000'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)
    check gTestAbortTriggered

    # rsPipelineError must hold for 2000ms
    satelliteLoop(7000'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)

    satelliteLoop(7999'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)

    # At 8000ms (2000ms elapsed in error), returns to rsIdle
    satelliteLoop(8000'u32)
    check nim_satellite_get_state() == ord(rsIdle)

  test "rsThinking 20s timeout triggers hardware abort, transitions to rsPipelineError, and returns to rsIdle":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_wake_word("assistant", 0)
    satelliteLoop(1000'u32)
    nim_satellite_chime_done(true)
    satelliteLoop(1200'u32)
    check nim_satellite_get_state() == ord(rsListening)

    nim_satellite_speech_ended()
    check nim_satellite_get_state() == ord(rsThinking)
    satelliteLoop(2000'u32)
    check not gTestAbortTriggered

    # At 21999ms (19999ms elapsed), remains in rsThinking
    satelliteLoop(21999'u32)
    check nim_satellite_get_state() == ord(rsThinking)
    check not gTestAbortTriggered

    # At 22000ms (20000ms elapsed), watchdog fires
    satelliteLoop(22000'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)
    check gTestAbortTriggered

    # Held in rsPipelineError until 24000ms (2000ms later)
    satelliteLoop(23000'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)

    satelliteLoop(24000'u32)
    check nim_satellite_get_state() == ord(rsIdle)

  test "TTS streaming with audio DSP feeding does not time out at 3s and completes cleanly":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_wake_word("assistant", 0)
    satelliteLoop(1000'u32)
    nim_satellite_chime_done(true)
    satelliteLoop(1100'u32)
    nim_satellite_speech_ended()
    satelliteLoop(1200'u32)
    nim_satellite_tts_start()
    check nim_satellite_get_state() == ord(rsReplying)

    # Start DMA stream for TTS playback with 2000ms inactivity timeout
    discard nim_dma_stream_start_at(cint(ord(dskTts)), 60000'u32, 2000'u32, false, 1500'u32)
    satelliteLoop(1500'u32)

    # Stream audio chunks every 500ms for 4000ms total (> 2000ms inactivity)
    var dummySamples: array[256, int16]
    for i in 1 .. 8:
      let chunkTime = 1500'u32 + uint32(i * 500)
      setSimulatedMillis(int64(chunkTime))
      # Process audio through DSP - automatically feeds DMA stream tracker via nim_dma_stream_feed
      nim_audio_dsp_process(cast[ptr UncheckedArray[int16]](addr dummySamples[0]), 256)
      satelliteLoop(chunkTime)
      check nim_satellite_get_state() == ord(rsReplying)
      check nim_dma_stream_is_active() == true
      check not gTestAbortTriggered

    # Complete TTS stream cleanly
    nim_dma_stream_finish()
    nim_satellite_tts_end()
    check nim_satellite_get_state() == ord(rsIdle)
    check not gTestAbortTriggered

  test "Media ducking and restoration: Idle -> PlayingMedia -> Woken -> Replying -> tts_end restores PlayingMedia":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_media_play()
    check nim_satellite_get_state() == ord(rsPlayingMedia)
    check nim_satellite_is_media_playing()

    # Wake word ducks media and enters Woken
    nim_satellite_wake_word("assistant", 45)
    check nim_satellite_get_state() == ord(rsWoken)

    nim_satellite_chime_done(true)
    check nim_satellite_get_state() == ord(rsListening)

    nim_satellite_speech_ended()
    check nim_satellite_get_state() == ord(rsThinking)

    nim_satellite_tts_start()
    check nim_satellite_get_state() == ord(rsReplying)

    # TTS ends: must return to rsPlayingMedia via onMediaPlay(ctxIdle)
    nim_satellite_tts_end()
    check nim_satellite_get_state() == ord(rsPlayingMedia)
    check nim_satellite_is_media_playing()

    # Media stops: returns to rsIdle
    nim_satellite_media_stop()
    check nim_satellite_get_state() == ord(rsIdle)
    check not nim_satellite_is_media_playing()

  test "Error during rsWoken when media was playing restores PlayingMedia after error delay":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_media_play()
    check nim_satellite_get_state() == ord(rsPlayingMedia)

    nim_satellite_wake_word("assistant", 90)
    check nim_satellite_get_state() == ord(rsWoken)
    satelliteLoop(1000'u32)

    # Hardware error during chime
    nim_satellite_error("chime-hardware-fail")
    check nim_satellite_get_state() == ord(rsPipelineError)
    check gTestAbortTriggered
    satelliteLoop(1000'u32)

    # Error is held for 2000ms
    satelliteLoop(2000'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)

    # After 2000ms, ducked media is restored
    satelliteLoop(3000'u32)
    check nim_satellite_get_state() == ord(rsPlayingMedia)
    check nim_satellite_is_media_playing()

  test "Silent dismiss when media was playing holds 500ms and restores PlayingMedia":
    check nim_satellite_get_state() == ord(rsIdle)
    nim_satellite_media_play()
    check nim_satellite_get_state() == ord(rsPlayingMedia)

    nim_satellite_wake_word("assistant", 0)
    satelliteLoop(1000'u32)
    nim_satellite_chime_done(true)
    satelliteLoop(1200'u32)
    check nim_satellite_get_state() == ord(rsListening)

    # Inaudible / no speech recognized
    nim_satellite_error("stt-no-text-recognized")
    check nim_satellite_get_state() == ord(rsSilentDismiss)
    satelliteLoop(1200'u32)

    # Held for 500ms
    satelliteLoop(1400'u32)
    check nim_satellite_get_state() == ord(rsSilentDismiss)

    satelliteLoop(1700'u32)
    check nim_satellite_get_state() == ord(rsPlayingMedia)
    check nim_satellite_is_media_playing()

  test "Watchdog loop operates correctly across 32-bit timer rollover (0xFFFFFFFF to 1000)":
    let nearMax = 0xFFFFFFF0'u32
    nim_satellite_wake_word("assistant", 0)
    satelliteLoop(nearMax)
    check nim_satellite_get_state() == ord(rsWoken)

    # 4999ms elapsed across rollover: nearMax + 4999 = 4983'u32
    satelliteLoop(4983'u32)
    check nim_satellite_get_state() == ord(rsWoken)
    check not gTestAbortTriggered

    # 5000ms elapsed across rollover: nearMax + 5000 = 4984'u32
    satelliteLoop(4984'u32)
    check nim_satellite_get_state() == ord(rsPipelineError)
    check gTestAbortTriggered

  test "Cancelling watchdog timeout at 3000ms":
    nim_satellite_wake_word("assistant", 0)
    nim_satellite_stop_word()
    check nim_satellite_get_state() == ord(rsCancelling)

    satelliteLoop(1000'u32)
    satelliteLoop(3999'u32)
    check nim_satellite_get_state() == ord(rsCancelling)
    check not gTestAbortTriggered

    satelliteLoop(4000'u32)
    check nim_satellite_get_state() == ord(rsIdle)
    check gTestAbortTriggered
