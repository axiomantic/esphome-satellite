## Satellite Voice Assistant State Machine using nim-esphome + nim-typestates
##
## Distinct Error States:
## 1. SilentDismiss: Inaudible / silence (stt-no-text-recognized) or duplicate wakeup.
##    Instant silent return to Idle without disturbing the user.
## 2. PipelineError: STT, intent, or TTS stream processing failure.
##    Plays brief error indicator and returns to Idle.
## 3. ConnectionError: Home Assistant server offline or WiFi lost.
##    Suppresses wake word detection until connection is restored.

import nim_esphome
import typestates

type
  SatelliteContext* = object
    wakeWord*: string
    beamAngle*: int
    errorCode*: string

  Idle* = distinct SatelliteContext
  Woken* = distinct SatelliteContext
  Listening* = distinct SatelliteContext
  Thinking* = distinct SatelliteContext
  Replying* = distinct SatelliteContext

  # Distinct Error & Offline States
  SilentDismiss* = distinct SatelliteContext
  PipelineError* = distinct SatelliteContext
  ConnectionError* = distinct SatelliteContext

typestate SatelliteFSM:
  consumeOnTransition = false
  states Idle, Woken, Listening, Thinking, Replying, SilentDismiss, PipelineError, ConnectionError
  transitions:
    Idle -> (Woken | ConnectionError) as IdleResult
    Woken -> (Listening | SilentDismiss | ConnectionError) as ChimeResult
    Listening -> (Thinking | SilentDismiss | PipelineError | ConnectionError | Idle) as ListenResult
    Thinking -> (Replying | PipelineError | ConnectionError | Idle) as ThinkResult
    Replying -> (Idle | PipelineError | ConnectionError) as ReplyResult
    SilentDismiss -> Idle
    PipelineError -> Idle
    ConnectionError -> Idle

# --- Transitions ---

proc onWakeWord*(s: Idle, word: string, angle: int): Woken {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle)
  info("SatelliteFSM", "State: IDLE -> WOKEN (wake_word: " & word & ")")
  result = Woken(ctx)

proc onChimeFinished*(s: Woken): Listening {.transition.} =
  info("SatelliteFSM", "State: WOKEN -> LISTENING (chime finished, mic active)")
  result = Listening(SatelliteContext(s))

proc onChimeFailed*(s: Woken): SilentDismiss {.transition.} =
  warn("SatelliteFSM", "State: WOKEN -> SILENT_DISMISS (chime failed)")
  result = SilentDismiss(SatelliteContext(s))

proc onSpeechEnded*(s: Listening): Thinking {.transition.} =
  info("SatelliteFSM", "State: LISTENING -> THINKING (VAD speech ended)")
  result = Thinking(SatelliteContext(s))

proc onSilenceTimeout*(s: Listening): SilentDismiss {.transition.} =
  info("SatelliteFSM", "State: LISTENING -> SILENT_DISMISS (no speech recognized)")
  result = SilentDismiss(SatelliteContext(s))

proc onStopDuringListening*(s: Listening): Idle {.transition.} =
  info("SatelliteFSM", "State: LISTENING -> IDLE (Stop command received)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromListening*(s: Listening, err: string): PipelineError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: LISTENING -> PIPELINE_ERROR (" & err & ")")
  result = PipelineError(ctx)

proc onTtsStarted*(s: Thinking): Replying {.transition.} =
  info("SatelliteFSM", "State: THINKING -> REPLYING (TTS playback started)")
  result = Replying(SatelliteContext(s))

proc onStopDuringThinking*(s: Thinking): Idle {.transition.} =
  info("SatelliteFSM", "State: THINKING -> IDLE (Stop command received)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromThinking*(s: Thinking, err: string): PipelineError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: THINKING -> PIPELINE_ERROR (" & err & ")")
  result = PipelineError(ctx)

proc onTtsFinished*(s: Replying): Idle {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> IDLE (TTS playback finished)")
  result = Idle(SatelliteContext())

proc onStopDuringReplying*(s: Replying): Idle {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> IDLE (Stop command received during TTS)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromReplying*(s: Replying, err: string): PipelineError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: REPLYING -> PIPELINE_ERROR (" & err & ")")
  result = PipelineError(ctx)

# Offline / Disconnect transitions
proc onDisconnectFromIdle*(s: Idle): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: IDLE -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromWoken*(s: Woken): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: WOKEN -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromListening*(s: Listening): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: LISTENING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromThinking*(s: Thinking): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: THINKING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromReplying*(s: Replying): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: REPLYING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

# Recovery transitions
proc onDismiss*(s: SilentDismiss): Idle {.transition.} =
  info("SatelliteFSM", "State: SILENT_DISMISS -> IDLE (silent reset)")
  result = Idle(SatelliteContext())

proc onResetPipelineError*(s: PipelineError): Idle {.transition.} =
  info("SatelliteFSM", "State: PIPELINE_ERROR -> IDLE (error cue finished)")
  result = Idle(SatelliteContext())

proc onConnected*(s: ConnectionError): Idle {.transition.} =
  info("SatelliteFSM", "State: CONNECTION_ERROR -> IDLE (HA reconnected)")
  result = Idle(SatelliteContext())

verifyTypestates()

# --- Runtime C API Bridge for ESPHome ---
type
  RuntimeState* = enum
    rsIdle = 0
    rsWoken = 1
    rsListening = 2
    rsThinking = 3
    rsReplying = 4
    rsSilentDismiss = 5
    rsPipelineError = 6
    rsConnectionError = 7

var
  currentState: RuntimeState = rsIdle
  ctxIdle: Idle = Idle(SatelliteContext())
  ctxWoken: Woken
  ctxListening: Listening
  ctxThinking: Thinking
  ctxReplying: Replying
  ctxDismiss: SilentDismiss
  ctxPipelineErr: PipelineError
  ctxConnErr: ConnectionError

proc nim_satellite_wake_word*(word: cstring, angle: cint) {.exportc, cdecl.} =
  if currentState == rsIdle:
    ctxWoken = onWakeWord(ctxIdle, $word, int(angle))
    currentState = rsWoken
  else:
    warn("SatelliteFSM", "Wake word ignored: satellite in state " & $currentState)

proc nim_satellite_chime_done*(ok: bool) {.exportc, cdecl.} =
  if currentState == rsWoken:
    if ok:
      ctxListening = onChimeFinished(ctxWoken)
      currentState = rsListening
    else:
      ctxDismiss = onChimeFailed(ctxWoken)
      ctxIdle = onDismiss(ctxDismiss)
      currentState = rsIdle

proc nim_satellite_speech_ended*() {.exportc, cdecl.} =
  if currentState == rsListening:
    ctxThinking = onSpeechEnded(ctxListening)
    currentState = rsThinking

proc nim_satellite_silence_timeout*() {.exportc, cdecl.} =
  if currentState == rsListening:
    ctxDismiss = onSilenceTimeout(ctxListening)
    ctxIdle = onDismiss(ctxDismiss)
    currentState = rsIdle

proc nim_satellite_tts_start*() {.exportc, cdecl.} =
  if currentState == rsThinking:
    ctxReplying = onTtsStarted(ctxThinking)
    currentState = rsReplying

proc nim_satellite_tts_end*() {.exportc, cdecl.} =
  if currentState == rsReplying:
    ctxIdle = onTtsFinished(ctxReplying)
    currentState = rsIdle

proc nim_satellite_stop_word*() {.exportc, cdecl.} =
  case currentState
  of rsListening:
    ctxIdle = onStopDuringListening(ctxListening)
    currentState = rsIdle
  of rsThinking:
    ctxIdle = onStopDuringThinking(ctxThinking)
    currentState = rsIdle
  of rsReplying:
    ctxIdle = onStopDuringReplying(ctxReplying)
    currentState = rsIdle
  else:
    debug("SatelliteFSM", "Stop word ignored in state " & $currentState)

proc nim_satellite_error*(code: cstring) {.exportc, cdecl.} =
  let err = $code
  if err == "stt-no-text-recognized" or err == "duplicate_wake_up_detected":
    if currentState == rsListening:
      ctxDismiss = onSilenceTimeout(ctxListening)
      ctxIdle = onDismiss(ctxDismiss)
      currentState = rsIdle
    return

  case currentState
  of rsListening:
    ctxPipelineErr = onPipelineErrorFromListening(ctxListening, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    currentState = rsIdle
  of rsThinking:
    ctxPipelineErr = onPipelineErrorFromThinking(ctxThinking, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    currentState = rsIdle
  of rsReplying:
    ctxPipelineErr = onPipelineErrorFromReplying(ctxReplying, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    currentState = rsIdle
  else:
    currentState = rsIdle

proc nim_satellite_disconnected*() {.exportc, cdecl.} =
  case currentState
  of rsIdle:
    ctxConnErr = onDisconnectFromIdle(ctxIdle)
  of rsWoken:
    ctxConnErr = onDisconnectFromWoken(ctxWoken)
  of rsListening:
    ctxConnErr = onDisconnectFromListening(ctxListening)
  of rsThinking:
    ctxConnErr = onDisconnectFromThinking(ctxThinking)
  of rsReplying:
    ctxConnErr = onDisconnectFromReplying(ctxReplying)
  else:
    discard
  currentState = rsConnectionError

proc nim_satellite_connected*() {.exportc, cdecl.} =
  if currentState == rsConnectionError:
    ctxIdle = onConnected(ctxConnErr)
    currentState = rsIdle

proc nim_satellite_get_state*(): cint {.exportc, cdecl.} =
  result = cint(ord(currentState))

esphomeSetup:
  info("SatelliteFSM", "Multi-error typestate machine initialized")
