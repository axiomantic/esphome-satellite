import unittest
import nim_esphome
import ../src/satellite_fsm

suite "Satellite Typestate FSM - Happy Path & Invariants":
  test "Full happy path lifecycle":
    var idle = Idle(SatelliteContext())
    var woken = idle.onWakeWord("hey assistant", 180)
    var listening = woken.onChimeFinished()
    var thinking = listening.onSpeechEnded()
    var replying = thinking.onTtsStarted()
    var backToIdle = replying.onTtsFinished()
    check backToIdle is Idle

  test "Stop word interrupts during listening, thinking, replying":
    var idle = Idle(SatelliteContext())
    var l = idle.onWakeWord("assistant", 0).onChimeFinished()
    check l.onStopDuringListening() is Idle

    var th = idle.onWakeWord("assistant", 0).onChimeFinished().onSpeechEnded()
    check th.onStopDuringThinking() is Idle

    var rep = idle.onWakeWord("assistant", 0).onChimeFinished().onSpeechEnded().onTtsStarted()
    check rep.onStopDuringReplying() is Idle

suite "Satellite Typestate FSM - Granular Error Handling":
  test "SilentDismiss on silence / inaudible command":
    var idle = Idle(SatelliteContext())
    var listening = idle.onWakeWord("assistant", 0).onChimeFinished()
    var dismissed = listening.onSilenceTimeout()
    check dismissed is SilentDismiss
    check dismissed.onDismiss() is Idle

  test "PipelineError on STT or intent failure":
    var idle = Idle(SatelliteContext())
    var listening = idle.onWakeWord("assistant", 0).onChimeFinished()
    var pErr = listening.onPipelineErrorFromListening("intent-failed")
    check pErr is PipelineError
    check SatelliteContext(pErr).errorCode == "intent-failed"
    check pErr.onResetPipelineError() is Idle

  test "ConnectionError disconnects from Idle and blocks wake words":
    var idle = Idle(SatelliteContext())
    var connErr = idle.onDisconnectFromIdle()
    check connErr is ConnectionError
    # Reconnection recovers to Idle
    check connErr.onConnected() is Idle

  test "ConnectionError drops active session and safely recovers":
    var idle = Idle(SatelliteContext())
    var thinking = idle.onWakeWord("assistant", 45).onChimeFinished().onSpeechEnded()
    var dropped = thinking.onDisconnectFromThinking()
    check dropped is ConnectionError
    check dropped.onConnected() is Idle

suite "Satellite Typestate FSM - Extended Lifecycle States":
  test "Muted privacy state disables wake words":
    var idle = Idle(SatelliteContext())
    var muted = idle.onMute()
    check muted is Muted
    var unmuted = muted.onUnmute()
    check unmuted is Idle

  test "FollowUp continuous conversation":
    var idle = Idle(SatelliteContext())
    var replying = idle.onWakeWord("assistant", 0).onChimeFinished().onSpeechEnded().onTtsStarted()
    var followUp = replying.onFollowUpRequested()
    check followUp is FollowUp
    var listening = followUp.onFollowUpReadyToListen()
    check listening is Listening
    var thinking = listening.onSpeechEnded()
    check thinking is Thinking

  test "PlayingMedia and audio ducking":
    var idle = Idle(SatelliteContext())
    var media = idle.onMediaPlay()
    check media is PlayingMedia
    var woken = media.onWakeWordFromMedia("assistant", 90)
    check woken is Woken
    check SatelliteContext(woken).wasPlayingMedia == true

  test "Alerting and timer ringing":
    var idle = Idle(SatelliteContext())
    var alert = idle.onAlertStart()
    check alert is Alerting
    var dismissed = alert.onAlertDismiss()
    check dismissed is Idle

  test "Server push announcement":
    var idle = Idle(SatelliteContext())
    var announce = idle.onAnnouncementStart()
    check announce is Announcing
    var done = announce.onAnnouncementEnd()
    check done is Idle

  test "OTA firmware update state":
    var idle = Idle(SatelliteContext())
    var updating = idle.onOtaStart()
    check updating is Updating
    var done = updating.onOtaComplete()
    check done is Idle

suite "Compile-Time Invariant Checking (Illegal Error Transitions Rejected)":
  test "Cannot trigger wake word when in ConnectionError":
    var connErr = Idle(SatelliteContext()).onDisconnectFromIdle()
    check not compiles(connErr.onWakeWord("assistant", 0))

  test "Cannot trigger wake word when in SilentDismiss or PipelineError":
    var idle = Idle(SatelliteContext())
    var listening = idle.onWakeWord("assistant", 0).onChimeFinished()
    var dismissed = listening.onSilenceTimeout()
    var pErr = listening.onPipelineErrorFromListening("timeout")
    check not compiles(dismissed.onWakeWord("assistant", 0))
    check not compiles(pErr.onWakeWord("assistant", 0))

  test "Cannot trigger wake word or capture speech when Muted":
    var muted = Idle(SatelliteContext()).onMute()
    check not compiles(muted.onWakeWord("assistant", 0))
    check not compiles(muted.onSpeechEnded())

  test "Cannot trigger wake word during OTA update":
    var updating = Idle(SatelliteContext()).onOtaStart()
    check not compiles(updating.onWakeWord("assistant", 0))
    check not compiles(updating.onSpeechEnded())

suite "Runtime C API Bridge (ESPHome Integration with Extended States)":
  test "Privacy mute via C API":
    check nim_satellite_get_state() == 0 # Idle
    nim_satellite_set_muted(true)
    check nim_satellite_get_state() == 8 # Muted
    check nim_satellite_is_muted() == true

    # Wake word while muted is ignored
    nim_satellite_wake_word("assistant", 0)
    check nim_satellite_get_state() == 8 # Still Muted

    nim_satellite_set_muted(false)
    check nim_satellite_get_state() == 0 # Back to Idle
    check nim_satellite_is_muted() == false

  test "Follow-up conversation flow via C API":
    nim_satellite_wake_word("assistant", 0)
    nim_satellite_chime_done(true)
    nim_satellite_speech_ended()
    nim_satellite_tts_start()
    check nim_satellite_get_state() == 4 # Replying

    # Server signals follow-up
    nim_satellite_follow_up()
    check nim_satellite_get_state() == 9 # FollowUp

    # Device opens mic for answer
    nim_satellite_follow_up()
    check nim_satellite_get_state() == 2 # Listening

    # Follow-up answered
    nim_satellite_speech_ended()
    check nim_satellite_get_state() == 3 # Thinking
    nim_satellite_tts_start()
    nim_satellite_tts_end()
    check nim_satellite_get_state() == 0 # Idle

  test "Media playback and ducking cycle":
    check nim_satellite_get_state() == 0 # Idle
    nim_satellite_media_play()
    check nim_satellite_get_state() == 10 # PlayingMedia
    check nim_satellite_is_media_playing() == true

    # Wake word during media triggers ducked conversation
    nim_satellite_wake_word("assistant", 0)
    check nim_satellite_get_state() == 1 # Woken
    nim_satellite_chime_done(true)
    nim_satellite_speech_ended()
    nim_satellite_tts_start()
    nim_satellite_tts_end()
    # Returns to PlayingMedia because media was playing!
    check nim_satellite_get_state() == 10 # PlayingMedia

    nim_satellite_media_stop()
    check nim_satellite_get_state() == 0 # Idle

  test "Timer alert dismissal":
    check nim_satellite_get_state() == 0
    nim_satellite_alert_start()
    check nim_satellite_get_state() == 11 # Alerting
    check nim_satellite_is_alerting() == true

    # Dismiss via stop word
    nim_satellite_stop_word()
    check nim_satellite_get_state() == 0 # Idle
    check nim_satellite_is_alerting() == false

  test "Server announcement cycle":
    check nim_satellite_get_state() == 0
    nim_satellite_announcement_start()
    check nim_satellite_get_state() == 12 # Announcing
    nim_satellite_announcement_end()
    check nim_satellite_get_state() == 0 # Idle

  test "OTA update lifecycle":
    check nim_satellite_get_state() == 0
    nim_satellite_ota_start()
    check nim_satellite_get_state() == 13 # Updating
    nim_satellite_ota_end(true)
    check nim_satellite_get_state() == 0 # Idle

  test "Processing sound loop and Home Assistant controls":
    check nim_satellite_get_state() == 0
    check not nim_satellite_is_processing()

    # HA entity simulation
    triggerSelectState("processing_sound", "Sonar")
    check configuredProcessingStyle == psSonar

    triggerNumberState("processing_sound_volume", 60.0'f32)
    check configuredProcessingVolume == 60.0'f32

    triggerSwitchState("wake_chime", false)
    check wakeChimeEnabled == false

    # Wake word and speech end
    nim_satellite_wake_word("assistant", 90)
    nim_satellite_chime_done(true)
    check nim_satellite_get_state() == 2 # Listening
    check not nim_satellite_is_processing()

    # User stops speaking -> Thinking begins -> Processing loop starts
    nim_satellite_speech_ended()
    check nim_satellite_get_state() == 3 # Thinking
    check nim_satellite_is_processing()

    # TTS begins -> Replying begins -> Processing loop stops immediately
    nim_satellite_tts_start()
    check nim_satellite_get_state() == 4 # Replying
    check not nim_satellite_is_processing()

    nim_satellite_tts_end()
    check nim_satellite_get_state() == 0 # Idle

