import unittest
import nim_esphome
import ../src/nim_esphome_satellite

suite "Acoustic Feedback Modes & FSM Transitions (TDD)":
  setup:
    setSimulatedMillis(0)
    currentState = rsIdle
    mediaWasPlaying = false
    configuredFeedbackMode = afmPostUtterance

  test "Mode getter and setter with bounds protection":
    nim_set_acoustic_feedback_mode(0)
    check nim_get_acoustic_feedback_mode() == 0
    check configuredFeedbackMode == afmPostUtterance

    nim_set_acoustic_feedback_mode(1)
    check nim_get_acoustic_feedback_mode() == 1
    check configuredFeedbackMode == afmImmediateNonBlocking

    nim_set_acoustic_feedback_mode(2)
    check nim_get_acoustic_feedback_mode() == 2
    check configuredFeedbackMode == afmLegacyBlocking

    nim_set_acoustic_feedback_mode(3)
    check nim_get_acoustic_feedback_mode() == 3
    check configuredFeedbackMode == afmVisualOnly

    # Out of bounds should be ignored
    nim_set_acoustic_feedback_mode(4)
    check nim_get_acoustic_feedback_mode() == 3
    nim_set_acoustic_feedback_mode(-1)
    check nim_get_acoustic_feedback_mode() == 3

  test "Post-Utterance Cue mode: direct transition Idle -> Listening":
    nim_set_acoustic_feedback_mode(0) # afmPostUtterance
    check currentState == rsIdle

    nim_satellite_wake_word("Mr. Clemens", 90)
    check currentState == rsListening
    check ctxListening.SatelliteContext.wakeWord == "Mr. Clemens"
    check ctxListening.SatelliteContext.beamAngle == 90

    # User speaks, VAD detects speech
    nim_satellite_speech_start()
    check speechActive == true

    # User finishes speaking, VAD ends
    nim_satellite_speech_ended()
    check currentState == rsThinking
    check speechActive == false

    # TTS begins
    nim_satellite_tts_start()
    check currentState == rsReplying

    # TTS ends
    nim_satellite_tts_end()
    check currentState == rsIdle

  test "Legacy Blocking mode: transitions Idle -> Woken -> Listening on chime done":
    nim_set_acoustic_feedback_mode(2) # afmLegacyBlocking
    check currentState == rsIdle

    nim_satellite_wake_word("Mr. Clemens", 180)
    check currentState == rsWoken
    check ctxWoken.SatelliteContext.wakeWord == "Mr. Clemens"

    # Chime finishes
    nim_satellite_chime_done(true)
    check currentState == rsListening

    # VAD speech end
    nim_satellite_speech_ended()
    check currentState == rsThinking

    # TTS ends
    nim_satellite_tts_start()
    nim_satellite_tts_end()
    check currentState == rsIdle

  test "Post-Utterance Cue with background media: ducks audio and restores media after flow":
    nim_set_acoustic_feedback_mode(0) # afmPostUtterance
    currentState = rsPlayingMedia
    mediaWasPlaying = false

    nim_satellite_wake_word("Mr. Clemens", 0)
    check currentState == rsListening
    check mediaWasPlaying == true
    check ctxListening.SatelliteContext.wasPlayingMedia == true

    # User speaks and finishes
    nim_satellite_speech_ended()
    check currentState == rsThinking

    # TTS responds
    nim_satellite_tts_start()
    check currentState == rsReplying

    # TTS finishes -> restores PlayingMedia!
    nim_satellite_tts_end()
    check currentState == rsPlayingMedia
    check mediaWasPlaying == false

  test "Immediate Non-Blocking mode: direct transition Idle -> Listening with AEC concurrent chime":
    nim_set_acoustic_feedback_mode(1) # afmImmediateNonBlocking
    check currentState == rsIdle

    nim_satellite_wake_word("Okay Nabu", 270)
    check currentState == rsListening
    check ctxListening.SatelliteContext.wakeWord == "Okay Nabu"

    # In non-blocking mode, if chime_done callback fires later, it is a no-op
    nim_satellite_chime_done(true)
    check currentState == rsListening

  test "Visual Only mode: direct transition Idle -> Listening":
    nim_set_acoustic_feedback_mode(3) # afmVisualOnly
    check currentState == rsIdle

    nim_satellite_wake_word("Mr. Clemens", 45)
    check currentState == rsListening
    check ctxListening.SatelliteContext.wakeWord == "Mr. Clemens"
