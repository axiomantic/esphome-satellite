import unittest
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

  test "Cannot end speech when in ConnectionError":
    var connErr = Idle(SatelliteContext()).onDisconnectFromIdle()
    check not compiles(connErr.onSpeechEnded())

suite "Runtime C API Bridge (ESPHome Integration with Multiple Errors)":
  test "Silent error code (stt-no-text-recognized) triggers silent reset":
    nim_satellite_wake_word("assistant", 0)
    nim_satellite_chime_done(true)
    check nim_satellite_get_state() == 2 # Listening

    # Emitting stt-no-text-recognized should silently reset to Idle
    nim_satellite_error("stt-no-text-recognized")
    check nim_satellite_get_state() == 0 # Idle

  test "Hard pipeline error code (intent-failed) triggers PipelineError recovery":
    nim_satellite_wake_word("assistant", 0)
    nim_satellite_chime_done(true)
    check nim_satellite_get_state() == 2 # Listening

    nim_satellite_error("intent-failed")
    check nim_satellite_get_state() == 0 # Recovered to Idle

  test "Network disconnect and reconnect cycle":
    check nim_satellite_get_state() == 0
    nim_satellite_disconnected()
    check nim_satellite_get_state() == 7 # ConnectionError

    # Wake word while disconnected must be ignored
    nim_satellite_wake_word("assistant", 0)
    check nim_satellite_get_state() == 7 # Still ConnectionError

    # Server comes back online
    nim_satellite_connected()
    check nim_satellite_get_state() == 0 # Back to Idle
