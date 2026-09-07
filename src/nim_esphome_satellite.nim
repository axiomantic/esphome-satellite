## Satellite Voice Assistant State Machine using nim-esphome + nim-typestates
##
## Distinct States:
## 1. Idle: Satellite awaiting wake word or background activity.
## 2. Woken: Wake word detected, playing chime / ducking audio.
## 3. Listening: Microphone capturing speech, VAD detecting speech boundary.
## 4. Thinking: Speech ended, server processing intent / generating TTS.
## 5. Replying: Server streaming TTS playback.
## 6. SilentDismiss: Inaudible / silence (stt-no-text-recognized) or duplicate wakeup.
## 7. PipelineError: STT, intent, or TTS stream processing failure.
## 8. ConnectionError: Home Assistant server offline or WiFi lost.
## 9. Muted: Hardware or software microphone privacy mute.
## 10. FollowUp: Multi-turn continuous conversation mode.
## 11. PlayingMedia: Background music / radio playback active with auto-ducking.
## 12. Alerting: Kitchen timer or alarm buzzer ringing.
## 13. Announcing: Unprompted server broadcast / intercom announcement.
## 14. Updating: OTA firmware update in progress, DSP audio suppressed.

import nim_esphome
import typestates
import std/strutils
import nim_esphome/dsl/actions

type
  SatelliteContext* = object
    wakeWord*: string
    beamAngle*: int
    errorCode*: string
    wasPlayingMedia*: bool

  Idle* = distinct SatelliteContext
  Woken* = distinct SatelliteContext
  Listening* = distinct SatelliteContext
  Thinking* = distinct SatelliteContext
  Replying* = distinct SatelliteContext

  # Error & Offline States
  SilentDismiss* = distinct SatelliteContext
  PipelineError* = distinct SatelliteContext
  ConnectionError* = distinct SatelliteContext

  # Extended Lifecycle States
  Muted* = distinct SatelliteContext
  FollowUp* = distinct SatelliteContext
  PlayingMedia* = distinct SatelliteContext
  Alerting* = distinct SatelliteContext
  Announcing* = distinct SatelliteContext
  Updating* = distinct SatelliteContext

typestate SatelliteFSM:
  consumeOnTransition = false
  states Idle, Woken, Listening, Thinking, Replying, SilentDismiss, PipelineError, ConnectionError, Muted, FollowUp, PlayingMedia, Alerting, Announcing, Updating
  transitions:
    Idle -> (Woken | ConnectionError | Muted | PlayingMedia | Alerting | Announcing | Updating) as IdleResult
    Woken -> (Listening | SilentDismiss | ConnectionError) as WokenResult
    Listening -> (Thinking | SilentDismiss | PipelineError | ConnectionError | Idle) as ListenResult
    Thinking -> (Replying | PipelineError | ConnectionError | Idle) as ThinkResult
    Replying -> (Idle | FollowUp | PipelineError | ConnectionError) as ReplyResult
    FollowUp -> (Listening | Idle | ConnectionError) as FollowUpResult
    SilentDismiss -> (Idle | PlayingMedia) as DismissResult
    PipelineError -> (Idle | PlayingMedia) as PipeErrResult
    ConnectionError -> (Idle | Muted | Updating) as ConnErrResult
    Muted -> (Idle | ConnectionError | Updating) as MutedResult
    PlayingMedia -> (Idle | Woken | Alerting | Announcing | ConnectionError | Updating) as MediaResult
    Alerting -> (Idle | Woken | ConnectionError) as AlertResult
    Announcing -> (Idle | ConnectionError) as AnnounceResult
    Updating -> Idle

# --- Core Lifecycle Transitions ---

proc onWakeWord*(s: Idle, word: string, angle: int): Woken {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: IDLE -> WOKEN (wake_word: " & word & ")")
  result = Woken(ctx)

proc onWakeWordFromMedia*(s: PlayingMedia, word: string, angle: int): Woken {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: true)
  info("SatelliteFSM", "State: PLAYING_MEDIA -> WOKEN (ducking audio, wake_word: " & word & ")")
  result = Woken(ctx)

proc onWakeWordDuringAlert*(s: Alerting, word: string, angle: int): Woken {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: ALERTING -> WOKEN (dismissing alert, wake_word: " & word & ")")
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

proc onFollowUpRequested*(s: Replying): FollowUp {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> FOLLOW_UP (continuous dialogue requested)")
  result = FollowUp(SatelliteContext(s))

proc onFollowUpReadyToListen*(s: FollowUp): Listening {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> LISTENING (mic open for follow-up)")
  result = Listening(SatelliteContext(s))

proc onFollowUpTimeout*(s: FollowUp): Idle {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> IDLE (dialogue timed out)")
  result = Idle(SatelliteContext())

proc onStopDuringReplying*(s: Replying): Idle {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> IDLE (Stop command received during TTS)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromReplying*(s: Replying, err: string): PipelineError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: REPLYING -> PIPELINE_ERROR (" & err & ")")
  result = PipelineError(ctx)

# --- Privacy Mute Transitions ---

proc onMute*(s: Idle): Muted {.transition.} =
  warn("SatelliteFSM", "State: IDLE -> MUTED (mic muted)")
  result = Muted(SatelliteContext(s))

proc onUnmute*(s: Muted): Idle {.transition.} =
  info("SatelliteFSM", "State: MUTED -> IDLE (mic unmuted)")
  result = Idle(SatelliteContext(s))

# --- Media Playback & Ducking Transitions ---

proc onMediaPlay*(s: Idle): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: IDLE -> PLAYING_MEDIA (media playback started)")
  result = PlayingMedia(SatelliteContext(s))

proc onMediaStop*(s: PlayingMedia): Idle {.transition.} =
  info("SatelliteFSM", "State: PLAYING_MEDIA -> IDLE (media playback stopped)")
  result = Idle(SatelliteContext(s))

# --- Alerting / Timer Transitions ---

proc onAlertStart*(s: Idle): Alerting {.transition.} =
  warn("SatelliteFSM", "State: IDLE -> ALERTING (timer/alarm ringing)")
  result = Alerting(SatelliteContext(s))

proc onAlertFromMedia*(s: PlayingMedia): Alerting {.transition.} =
  warn("SatelliteFSM", "State: PLAYING_MEDIA -> ALERTING (timer/alarm ringing)")
  result = Alerting(SatelliteContext(s))

proc onAlertDismiss*(s: Alerting): Idle {.transition.} =
  info("SatelliteFSM", "State: ALERTING -> IDLE (alert dismissed)")
  result = Idle(SatelliteContext(s))

# --- Announcement / Intercom Transitions ---

proc onAnnouncementStart*(s: Idle): Announcing {.transition.} =
  info("SatelliteFSM", "State: IDLE -> ANNOUNCING (server broadcast started)")
  result = Announcing(SatelliteContext(s))

proc onAnnouncementFromMedia*(s: PlayingMedia): Announcing {.transition.} =
  info("SatelliteFSM", "State: PLAYING_MEDIA -> ANNOUNCING (server broadcast started)")
  result = Announcing(SatelliteContext(s))

proc onAnnouncementEnd*(s: Announcing): Idle {.transition.} =
  info("SatelliteFSM", "State: ANNOUNCING -> IDLE (broadcast finished)")
  result = Idle(SatelliteContext(s))

# --- OTA Update Transitions ---

proc onOtaStart*(s: Idle): Updating {.transition.} =
  warn("SatelliteFSM", "State: IDLE -> UPDATING (OTA flash in progress)")
  result = Updating(SatelliteContext(s))

proc onOtaFromMuted*(s: Muted): Updating {.transition.} =
  warn("SatelliteFSM", "State: MUTED -> UPDATING (OTA flash in progress)")
  result = Updating(SatelliteContext(s))

proc onOtaFromMedia*(s: PlayingMedia): Updating {.transition.} =
  warn("SatelliteFSM", "State: PLAYING_MEDIA -> UPDATING (OTA flash in progress)")
  result = Updating(SatelliteContext(s))

proc onOtaFromConnErr*(s: ConnectionError): Updating {.transition.} =
  warn("SatelliteFSM", "State: CONNECTION_ERROR -> UPDATING (OTA flash in progress)")
  result = Updating(SatelliteContext(s))

proc onOtaComplete*(s: Updating): Idle {.transition.} =
  info("SatelliteFSM", "State: UPDATING -> IDLE (OTA flash complete)")
  result = Idle(SatelliteContext(s))

# --- Offline / Disconnect Transitions ---

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

proc onDisconnectFromFollowUp*(s: FollowUp): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: FOLLOW_UP -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromMuted*(s: Muted): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: MUTED -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromMedia*(s: PlayingMedia): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: PLAYING_MEDIA -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromAlerting*(s: Alerting): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: ALERTING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromAnnouncing*(s: Announcing): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: ANNOUNCING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

# --- Recovery Transitions ---

proc onDismiss*(s: SilentDismiss): Idle {.transition.} =
  info("SatelliteFSM", "State: SILENT_DISMISS -> IDLE (silent reset)")
  result = Idle(SatelliteContext())

proc onDismissToMedia*(s: SilentDismiss): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: SILENT_DISMISS -> PLAYING_MEDIA (restoring media audio)")
  result = PlayingMedia(SatelliteContext())

proc onResetPipelineError*(s: PipelineError): Idle {.transition.} =
  info("SatelliteFSM", "State: PIPELINE_ERROR -> IDLE (error cue finished)")
  result = Idle(SatelliteContext())

proc onResetPipelineErrorToMedia*(s: PipelineError): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: PIPELINE_ERROR -> PLAYING_MEDIA (restoring media audio)")
  result = PlayingMedia(SatelliteContext())

proc onConnected*(s: ConnectionError): Idle {.transition.} =
  info("SatelliteFSM", "State: CONNECTION_ERROR -> IDLE (HA reconnected)")
  result = Idle(SatelliteContext())

proc onConnectedMuted*(s: ConnectionError): Muted {.transition.} =
  info("SatelliteFSM", "State: CONNECTION_ERROR -> MUTED (HA reconnected, mic was muted)")
  result = Muted(SatelliteContext())

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
    rsMuted = 8
    rsFollowUp = 9
    rsPlayingMedia = 10
    rsAlerting = 11
    rsAnnouncing = 12
    rsUpdating = 13

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
  ctxMuted: Muted
  ctxFollowUp: FollowUp
  ctxMedia: PlayingMedia
  ctxAlerting: Alerting
  ctxAnnouncing: Announcing
  ctxUpdating: Updating
  mediaWasPlaying: bool = false
  micWasMuted: bool = false
  configuredProcessingStyle* = psSpinner
  configuredProcessingVolume* = 75.0'f32
  configuredWakeChimeSound* = wcBell
  wakeChimeEnabled* = true
  wakeChimeVolume* = 75.0'f32
  satellitePipeline* = newSatellitePipeline()

esphomeControls:
  select[ProcessingSoundStyle]("processing_sound"):
    name = "Processing Sound"
    default = psSpinner
    persist = true
    onSelect(style):
      configuredProcessingStyle = style
      satellitePipeline.processingLoop.style = style

  select[WakeChimeSound]("wake_chime_sound"):
    name = "Wake Chime Sound"
    default = wcBell
    persist = true
    onSelect(sound):
      configuredWakeChimeSound = sound
      satellitePipeline.wakeChimeSound = sound

  number("processing_sound_volume"):
    name = "Processing Sound Volume"
    min = 0.0
    max = 100.0
    step = 5.0
    default = 75.0
    persist = true
    onChange(vol):
      configuredProcessingVolume = vol
      satellitePipeline.processingLoop.volume = vol / 100.0

  number("wake_chime_volume"):
    name = "Wake Chime Volume"
    min = 0.0
    max = 100.0
    step = 5.0
    default = 75.0
    persist = true
    onChange(vol):
      wakeChimeVolume = vol
      satellitePipeline.wakeChimeVolume = vol / 100.0

  switch("wake_chime"):
    name = "Wake Chime"
    default = true
    persist = true
    onToggle(enabled):
      wakeChimeEnabled = enabled
      satellitePipeline.wakeChimeEnabled = enabled

proc parseSoundStyle*(s: string): ProcessingSoundStyle =
  case s.toLowerAscii
  of "spinner": psSpinner
  of "pulse": psPulse
  of "sonar": psSonar
  of "tick": psTick
  of "typewriter": psTypewriter
  of "clockwork": psClockwork
  of "water droplets", "water_droplets", "water": psWaterDroplets
  of "custom": psCustom
  else: psSilent

proc parseWakeChimeSound*(s: string): WakeChimeSound =
  case s.toLowerAscii
  of "bell ping", "bell": wcBell
  of "modern chime", "modern": wcModern
  of "crystal glass", "crystal": wcCrystal
  of "warm kalimba", "kalimba": wcKalimba
  of "meditation bell", "meditation": wcMeditation
  of "marimba": wcMarimba
  of "subtle beep", "subtle": wcSubtle
  of "custom", "custom chime audio": wcCustom
  else: wcSilent

proc previewAudioFeedback*(styleStr: string, vol: float) =
  info("SatelliteAction", "Previewing audio feedback: " & styleStr & " at " & $vol & "%")
  let st = parseSoundStyle(styleStr)
  configuredProcessingStyle = st
  if satellitePipeline != nil and satellitePipeline.processingLoop != nil:
    satellitePipeline.processingLoop.style = st
    satellitePipeline.processingLoop.volume = float32(vol / 100.0)
    satellitePipeline.startProcessingLoop(st)

haAction("test_audio_feedback"):
  def.description = "Preview voice satellite sound style or chime from Home Assistant"
  param "style", pkString, defaultVal = "Spinner", description = "Sound style: Spinner, Pulse, Sonar, Tick, Typewriter, Clockwork, Water Droplets, Custom, Silent"
  param "volume", pkFloat, min = 0.0, max = 100.0, defaultVal = "75.0", description = "Playback volume percentage (0-100)"
  onExecute(ctx):
    let styleStr = ctx.getString("style", "Spinner")
    let vol = ctx.getFloat("volume", 75.0)
    previewAudioFeedback(styleStr, vol)

proc nim_action_test_audio*(style: cstring, volume: cfloat) {.exportc, cdecl.} =
  previewAudioFeedback($style, float(volume))

proc nim_action_set_processing_sound*(sound: cstring) {.exportc, cdecl.} =
  let st = parseSoundStyle($sound)
  configuredProcessingStyle = st
  if satellitePipeline != nil and satellitePipeline.processingLoop != nil:
    satellitePipeline.processingLoop.style = st

proc nim_action_set_processing_volume*(volume: cfloat) {.exportc, cdecl.} =
  configuredProcessingVolume = float32(volume)
  if satellitePipeline != nil and satellitePipeline.processingLoop != nil:
    satellitePipeline.processingLoop.volume = float32(volume / 100.0)

proc nim_action_set_chime_sound*(sound: cstring) {.exportc, cdecl.} =
  let chime = parseWakeChimeSound($sound)
  configuredWakeChimeSound = chime
  if satellitePipeline != nil:
    satellitePipeline.wakeChimeSound = chime

proc nim_action_set_chime_volume*(volume: cfloat) {.exportc, cdecl.} =
  wakeChimeVolume = float32(volume)
  if satellitePipeline != nil:
    satellitePipeline.wakeChimeVolume = float32(volume / 100.0)



proc returnFromVoiceFlow() =
  if mediaWasPlaying:
    mediaWasPlaying = false
    ctxMedia = onDismissToMedia(ctxDismiss)
    currentState = rsPlayingMedia
  else:
    currentState = rsIdle

proc returnFromPipelineError() =
  if mediaWasPlaying:
    mediaWasPlaying = false
    ctxMedia = onResetPipelineErrorToMedia(ctxPipelineErr)
    currentState = rsPlayingMedia
  else:
    currentState = rsIdle

proc nim_satellite_wake_word*(word: cstring, angle: cint) {.exportc, cdecl.} =
  case currentState
  of rsIdle:
    ctxWoken = onWakeWord(ctxIdle, $word, int(angle))
    currentState = rsWoken
  of rsPlayingMedia:
    mediaWasPlaying = true
    ctxWoken = onWakeWordFromMedia(ctxMedia, $word, int(angle))
    currentState = rsWoken
  of rsAlerting:
    ctxWoken = onWakeWordDuringAlert(ctxAlerting, $word, int(angle))
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
      returnFromVoiceFlow()

proc nim_satellite_speech_ended*() {.exportc, cdecl.} =
  if currentState == rsListening:
    ctxThinking = onSpeechEnded(ctxListening)
    currentState = rsThinking
    satellitePipeline.startProcessingLoop(configuredProcessingStyle)

proc nim_satellite_silence_timeout*() {.exportc, cdecl.} =
  if currentState == rsListening:
    ctxDismiss = onSilenceTimeout(ctxListening)
    ctxIdle = onDismiss(ctxDismiss)
    returnFromVoiceFlow()
  elif currentState == rsFollowUp:
    ctxIdle = onFollowUpTimeout(ctxFollowUp)
    returnFromVoiceFlow()

proc nim_satellite_tts_start*() {.exportc, cdecl.} =
  satellitePipeline.stopProcessingLoop()
  if currentState == rsThinking:
    ctxReplying = onTtsStarted(ctxThinking)
    currentState = rsReplying

proc nim_satellite_tts_end*() {.exportc, cdecl.} =
  if currentState == rsReplying:
    ctxIdle = onTtsFinished(ctxReplying)
    returnFromVoiceFlow()

proc nim_satellite_follow_up*() {.exportc, cdecl.} =
  if currentState == rsReplying:
    ctxFollowUp = onFollowUpRequested(ctxReplying)
    currentState = rsFollowUp
  elif currentState == rsFollowUp:
    ctxListening = onFollowUpReadyToListen(ctxFollowUp)
    currentState = rsListening

proc nim_satellite_stop_word*() {.exportc, cdecl.} =
  satellitePipeline.stopProcessingLoop()
  case currentState
  of rsWoken:
    ctxDismiss = onChimeFailed(ctxWoken)
    ctxIdle = onDismiss(ctxDismiss)
    returnFromVoiceFlow()
  of rsListening:
    ctxIdle = onStopDuringListening(ctxListening)
    returnFromVoiceFlow()
  of rsThinking:
    ctxIdle = onStopDuringThinking(ctxThinking)
    returnFromVoiceFlow()
  of rsReplying:
    ctxIdle = onStopDuringReplying(ctxReplying)
    returnFromVoiceFlow()
  of rsAlerting:
    ctxIdle = onAlertDismiss(ctxAlerting)
    currentState = rsIdle
  of rsFollowUp:
    ctxIdle = onFollowUpTimeout(ctxFollowUp)
    returnFromVoiceFlow()
  else:
    debug("SatelliteFSM", "Stop word ignored in state " & $currentState)

proc nim_satellite_error*(code: cstring) {.exportc, cdecl.} =
  let err = $code
  if err == "stt-no-text-recognized" or err == "duplicate_wake_up_detected":
    if currentState == rsListening:
      ctxDismiss = onSilenceTimeout(ctxListening)
      ctxIdle = onDismiss(ctxDismiss)
      returnFromVoiceFlow()
    elif currentState == rsFollowUp:
      ctxIdle = onFollowUpTimeout(ctxFollowUp)
      returnFromVoiceFlow()
    return

  case currentState
  of rsListening:
    ctxPipelineErr = onPipelineErrorFromListening(ctxListening, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    returnFromPipelineError()
  of rsThinking:
    ctxPipelineErr = onPipelineErrorFromThinking(ctxThinking, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    returnFromPipelineError()
  of rsReplying:
    ctxPipelineErr = onPipelineErrorFromReplying(ctxReplying, err)
    ctxIdle = onResetPipelineError(ctxPipelineErr)
    returnFromPipelineError()
  else:
    currentState = rsIdle

proc nim_satellite_set_muted*(muted: bool) {.exportc, cdecl.} =
  micWasMuted = muted
  if muted and currentState == rsIdle:
    ctxMuted = onMute(ctxIdle)
    currentState = rsMuted
  elif not muted and currentState == rsMuted:
    ctxIdle = onUnmute(ctxMuted)
    currentState = rsIdle

proc setPrivacyMute*(muted: bool) =
  info("SatelliteAction", "Privacy mute requested: " & $muted)
  nim_satellite_set_muted(muted)

haService("set_privacy_mute"):
  def.description = "Set microphone privacy mute state"
  param "muted", pkBool, defaultVal = "true", description = "Mute microphone"
  onExecute(ctx):
    let mute = ctx.getBool("muted", true)
    setPrivacyMute(mute)

proc nim_action_set_mute*(muted: bool) {.exportc, cdecl.} =
  setPrivacyMute(muted)

proc nim_satellite_media_play*() {.exportc, cdecl.} =
  if currentState == rsIdle:
    ctxMedia = onMediaPlay(ctxIdle)
    currentState = rsPlayingMedia

proc nim_satellite_media_stop*() {.exportc, cdecl.} =
  if currentState == rsPlayingMedia:
    ctxIdle = onMediaStop(ctxMedia)
    currentState = rsIdle

proc nim_satellite_alert_start*() {.exportc, cdecl.} =
  if currentState == rsIdle:
    ctxAlerting = onAlertStart(ctxIdle)
    currentState = rsAlerting
  elif currentState == rsPlayingMedia:
    ctxAlerting = onAlertFromMedia(ctxMedia)
    currentState = rsAlerting

proc nim_satellite_alert_stop*() {.exportc, cdecl.} =
  if currentState == rsAlerting:
    ctxIdle = onAlertDismiss(ctxAlerting)
    currentState = rsIdle

proc nim_satellite_announcement_start*() {.exportc, cdecl.} =
  if currentState == rsIdle:
    ctxAnnouncing = onAnnouncementStart(ctxIdle)
    currentState = rsAnnouncing
  elif currentState == rsPlayingMedia:
    ctxAnnouncing = onAnnouncementFromMedia(ctxMedia)
    currentState = rsAnnouncing

proc nim_satellite_announcement_end*() {.exportc, cdecl.} =
  if currentState == rsAnnouncing:
    ctxIdle = onAnnouncementEnd(ctxAnnouncing)
    currentState = rsIdle

proc nim_satellite_ota_start*() {.exportc, cdecl.} =
  case currentState
  of rsIdle:
    ctxUpdating = onOtaStart(ctxIdle)
  of rsMuted:
    ctxUpdating = onOtaFromMuted(ctxMuted)
  of rsPlayingMedia:
    ctxUpdating = onOtaFromMedia(ctxMedia)
  of rsConnectionError:
    ctxUpdating = onOtaFromConnErr(ctxConnErr)
  else:
    discard
  currentState = rsUpdating

proc nim_satellite_ota_end*(ok: bool) {.exportc, cdecl.} =
  if currentState == rsUpdating:
    ctxIdle = onOtaComplete(ctxUpdating)
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
  of rsFollowUp:
    ctxConnErr = onDisconnectFromFollowUp(ctxFollowUp)
  of rsMuted:
    ctxConnErr = onDisconnectFromMuted(ctxMuted)
  of rsPlayingMedia:
    ctxConnErr = onDisconnectFromMedia(ctxMedia)
  of rsAlerting:
    ctxConnErr = onDisconnectFromAlerting(ctxAlerting)
  of rsAnnouncing:
    ctxConnErr = onDisconnectFromAnnouncing(ctxAnnouncing)
  else:
    discard
  currentState = rsConnectionError

proc nim_satellite_connected*() {.exportc, cdecl.} =
  if currentState == rsConnectionError:
    if micWasMuted:
      ctxMuted = onConnectedMuted(ctxConnErr)
      currentState = rsMuted
    else:
      ctxIdle = onConnected(ctxConnErr)
      currentState = rsIdle

proc nim_satellite_get_state*(): cint {.exportc, cdecl.} =
  result = cint(ord(currentState))

proc nim_satellite_is_muted*(): bool {.exportc, cdecl.} =
  result = (currentState == rsMuted)

proc nim_satellite_is_media_playing*(): bool {.exportc, cdecl.} =
  result = (currentState == rsPlayingMedia)

proc nim_satellite_is_alerting*(): bool {.exportc, cdecl.} =
  result = (currentState == rsAlerting)

proc nim_satellite_is_processing*(): bool {.exportc, cdecl.} =
  if satellitePipeline != nil:
    satellitePipeline.isProcessing()
  else:
    false

proc nim_satellite_get_processing_style*(): cint {.exportc, cdecl.} =
  cint(ord(configuredProcessingStyle))

esphomeSetup:
  info("SatelliteFSM", "14-state verified voice satellite state machine initialized")
  if satellitePipeline != nil and satellitePipeline.processingLoop != nil:
    satellitePipeline.processingLoop.onTick = proc(style: ProcessingSoundStyle, vol: float32, count: int) =
      if style == psCustom:
        debug("SatelliteAudio", "Streaming custom audio sample from flash partition sound_data (count=" & $count & ")")
      else:
        debug("SatelliteAudio", "Processing sound tick: style=" & $style & " count=" & $count)

var lastHeartbeatMs: uint32 = 0
var lastObservedState: RuntimeState = rsIdle
var stateEnteredMs: uint32 = 0

esphomeLoop:
  let now = millis()
  if currentState != lastObservedState:
    lastObservedState = currentState
    stateEnteredMs = now

  if satellitePipeline != nil:
    satellitePipeline.tick(now)

  if currentState == rsWoken and now - stateEnteredMs >= 3000:
    warn("SatelliteFSM", "Watchdog: Woken state timed out after 3s. Returning to Idle.")
    nim_satellite_stop_word()
  elif currentState == rsListening and now - stateEnteredMs >= 10000:
    warn("SatelliteFSM", "Watchdog: Listening state timed out after 10s. Returning to Idle.")
    nim_satellite_stop_word()
  elif currentState == rsThinking and now - stateEnteredMs >= 25000:
    warn("SatelliteFSM", "Watchdog: Thinking state timed out after 25s. Returning to Idle.")
    nim_satellite_stop_word()

  if now - lastHeartbeatMs >= 10000:
    lastHeartbeatMs = now
    info("Satellite", "Heartbeat: state=" & $currentState & " uptime=" & $(now div 1000) & "s heap=" & $getFreeHeap())


