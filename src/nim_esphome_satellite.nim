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

var gSimulatedMillis*: int64 = -1

proc satelliteNowMs*(): uint32 {.inline.} =
  if gSimulatedMillis >= 0:
    uint32(gSimulatedMillis)
  else:
    millis()

proc setSimulatedMillis*(ms: int64) =
  gSimulatedMillis = ms

include audio_stream_tracker
include audio_volume
include audio_dsp
include xvf3800_hardware
include wake_partition_loader
include pcm_sound_player
include cancellation_matcher
include nvs_migration

type
  SatelliteContext* = object
    wakeWord*: string
    beamAngle*: int
    errorCode*: string
    wasPlayingMedia*: bool

  # --- Steady States ---
  Idle* = distinct SatelliteContext
  WaitingForSpeech* = distinct SatelliteContext
  StreamingSpeech* = distinct SatelliteContext
  StreamingSpeechVerified* = distinct SatelliteContext
  Verifying* = distinct SatelliteContext
  Processing* = distinct SatelliteContext
  Replying* = distinct SatelliteContext
  Cancelling* = distinct SatelliteContext
  ConnectionError* = distinct SatelliteContext

  # --- Reified Evaluation States (Zero-Variable-Branching) ---
  ReplyingBargeInAttempted* = distinct SatelliteContext
  ReplyingBargeInIgnored* = distinct SatelliteContext
  PipelineErrorEvaluating* = distinct SatelliteContext

  # --- Reified Action States ---
  BargedIn* = distinct SatelliteContext
  IntentCompleteNoTts* = distinct SatelliteContext
  ActionSuccess* = distinct SatelliteContext
  SilentDismissing* = distinct SatelliteContext
  ActionableError* = distinct SatelliteContext

  # --- Extended Lifecycle States ---
  Muted* = distinct SatelliteContext
  FollowUp* = distinct SatelliteContext
  PlayingMedia* = distinct SatelliteContext
  Alerting* = distinct SatelliteContext
  Announcing* = distinct SatelliteContext
  Updating* = distinct SatelliteContext

  # Semantic & Backward-Compatibility Aliases
  Woken* = WaitingForSpeech
  Listening* = StreamingSpeech
  Thinking* = Processing
  SilentDismiss* = SilentDismissing
  PipelineError* = ActionableError
  VerifyingWakeWord* = Verifying
  WakeWordVerified* = StreamingSpeechVerified

typestate SatelliteFSM:
  consumeOnTransition = false
  states Idle, WaitingForSpeech, StreamingSpeech, StreamingSpeechVerified, Verifying, Processing, Replying, Cancelling, SilentDismissing, ActionableError, ConnectionError, Muted, FollowUp, PlayingMedia, Alerting, Announcing, Updating, ReplyingBargeInAttempted, ReplyingBargeInIgnored, BargedIn, IntentCompleteNoTts, ActionSuccess, PipelineErrorEvaluating
  transitions:
    Idle -> (WaitingForSpeech | StreamingSpeech | ConnectionError | Muted | PlayingMedia | Alerting | Announcing | Updating) as IdleResult
    WaitingForSpeech -> (StreamingSpeech | Cancelling | SilentDismissing | PipelineErrorEvaluating | ActionableError | ConnectionError | Idle) as WaitingResult
    StreamingSpeech -> (StreamingSpeechVerified | Verifying | Processing | Cancelling | SilentDismissing | PipelineErrorEvaluating | ConnectionError | Idle) as StreamingResult
    StreamingSpeechVerified -> (Processing | Cancelling | SilentDismissing | PipelineErrorEvaluating | ActionableError | ConnectionError | Idle) as VerifiedResult
    Verifying -> (Processing | Cancelling | SilentDismissing | PipelineErrorEvaluating | ActionableError | ConnectionError | Idle) as VerifyingResult
    Processing -> (Replying | IntentCompleteNoTts | Cancelling | SilentDismissing | PipelineErrorEvaluating | ActionableError | ConnectionError | Idle) as ProcessingResult
    Replying -> (Idle | Cancelling | FollowUp | ReplyingBargeInAttempted | PipelineErrorEvaluating | ConnectionError) as ReplyingResult
    Cancelling -> (Idle | PlayingMedia | ConnectionError) as CancelResult
    FollowUp -> (StreamingSpeech | Processing | Cancelling | Idle | PipelineErrorEvaluating | ConnectionError) as FollowUpResult
    SilentDismissing -> (Idle | PlayingMedia) as DismissResult
    ActionableError -> (Idle | PlayingMedia) as ActionErrResult
    ConnectionError -> (Idle | Muted | Updating) as ConnErrResult
    Muted -> (Idle | ConnectionError | Updating) as MutedResult
    PlayingMedia -> (Idle | WaitingForSpeech | StreamingSpeech | Alerting | Announcing | ConnectionError | Updating) as MediaResult
    Alerting -> (Idle | WaitingForSpeech | StreamingSpeech | ConnectionError) as AlertResult
    Announcing -> (Idle | ConnectionError) as AnnounceResult
    Updating -> Idle
    ReplyingBargeInAttempted -> (BargedIn | ReplyingBargeInIgnored) as BargeAttemptResult
    ReplyingBargeInIgnored -> Replying
    BargedIn -> Idle
    IntentCompleteNoTts -> ActionSuccess
    ActionSuccess -> Idle
    PipelineErrorEvaluating -> (SilentDismissing | ActionableError) as ErrorEvalResult

# --- Core Lifecycle Transitions ---

proc onWakeWord*(s: Idle, word: string, angle: int): WaitingForSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: IDLE -> WAITING_FOR_SPEECH (wake_word: " & word & ")")
  result = WaitingForSpeech(ctx)

proc onWakeWordFromMedia*(s: PlayingMedia, word: string, angle: int): WaitingForSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: true)
  info("SatelliteFSM", "State: PLAYING_MEDIA -> WAITING_FOR_SPEECH (ducking audio, wake_word: " & word & ")")
  result = WaitingForSpeech(ctx)

proc onWakeWordDuringAlert*(s: Alerting, word: string, angle: int): WaitingForSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: ALERTING -> WAITING_FOR_SPEECH (dismissing alert, wake_word: " & word & ")")
  result = WaitingForSpeech(ctx)

proc onWakeWordDirect*(s: Idle, word: string, angle: int): StreamingSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: IDLE -> STREAMING_SPEECH (direct wake, wake_word: " & word & ")")
  result = StreamingSpeech(ctx)

proc onWakeWordDirectFromMedia*(s: PlayingMedia, word: string, angle: int): StreamingSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: true)
  info("SatelliteFSM", "State: PLAYING_MEDIA -> STREAMING_SPEECH (ducking audio, direct wake, wake_word: " & word & ")")
  result = StreamingSpeech(ctx)

proc onWakeWordDirectDuringAlert*(s: Alerting, word: string, angle: int): StreamingSpeech {.transition.} =
  var ctx = SatelliteContext(wakeWord: word, beamAngle: angle, wasPlayingMedia: false)
  info("SatelliteFSM", "State: ALERTING -> STREAMING_SPEECH (dismissing alert, direct wake, wake_word: " & word & ")")
  result = StreamingSpeech(ctx)

proc onChimeFinished*(s: WaitingForSpeech): StreamingSpeech {.transition.} =
  info("SatelliteFSM", "State: WAITING_FOR_SPEECH -> STREAMING_SPEECH (chime finished, mic active)")
  result = StreamingSpeech(SatelliteContext(s))

proc onChimeFailed*(s: WaitingForSpeech): SilentDismissing {.transition.} =
  warn("SatelliteFSM", "State: WAITING_FOR_SPEECH -> SILENT_DISMISSING (chime failed)")
  result = SilentDismissing(SatelliteContext(s))

proc onChimeTimeout*(s: WaitingForSpeech): ActionableError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = "chime-timeout"
  error("SatelliteFSM", "State: WAITING_FOR_SPEECH -> ACTIONABLE_ERROR (wake chime playback timeout)")
  result = ActionableError(ctx)

proc onPipelineErrorFromWaiting*(s: WaitingForSpeech, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: WAITING_FOR_SPEECH -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onSilenceTimeoutFromWaiting*(s: WaitingForSpeech): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: WAITING_FOR_SPEECH -> SILENT_DISMISSING (silence timeout)")
  result = SilentDismissing(SatelliteContext(s))

proc onStopDuringWaiting*(s: WaitingForSpeech): Idle {.transition.} =
  info("SatelliteFSM", "State: WAITING_FOR_SPEECH -> IDLE (Stop command received)")
  result = Idle(SatelliteContext())

proc onStopDuringWoken*(s: WaitingForSpeech): Cancelling {.transition.} =
  info("SatelliteFSM", "State: WAITING_FOR_SPEECH -> CANCELLING (Stop command received during chime)")
  result = Cancelling(SatelliteContext(s))

proc onSpeechEnded*(s: StreamingSpeech): Verifying {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> VERIFYING (VAD speech ended, awaiting verification)")
  result = Verifying(SatelliteContext(s))

proc onSpeechEndedDirectToProcessing*(s: StreamingSpeech): Processing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> PROCESSING (direct transition without verification)")
  result = Processing(SatelliteContext(s))

proc onWakeWordVerified*(s: StreamingSpeech): StreamingSpeechVerified {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> STREAMING_SPEECH_VERIFIED (Speculative verification confirmed)")
  result = StreamingSpeechVerified(SatelliteContext(s))

proc onWakeWordVerifiedFromStreaming*(s: StreamingSpeech): StreamingSpeechVerified {.inline.} =
  onWakeWordVerified(s)

proc onSpeechEnded*(s: StreamingSpeechVerified): Processing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> PROCESSING (VAD speech ended, proceeding to intent execution)")
  result = Processing(SatelliteContext(s))

proc onSpeechEndedFromVerified*(s: StreamingSpeechVerified): Processing {.inline.} =
  onSpeechEnded(s)

proc onStopDuringVerified*(s: StreamingSpeechVerified): Cancelling {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> CANCELLING (Stop command received during verified speech)")
  result = Cancelling(SatelliteContext(s))

proc onStopDuringVerifiedToIdle*(s: StreamingSpeechVerified): Idle {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> IDLE (Stop command received during verified speech)")
  result = Idle(SatelliteContext())

proc onSilenceTimeout*(s: StreamingSpeechVerified): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> SILENT_DISMISSING (silence timeout after verification)")
  result = SilentDismissing(SatelliteContext(s))

proc onSilenceTimeoutFromVerified*(s: StreamingSpeechVerified): SilentDismissing {.inline.} =
  onSilenceTimeout(s)

proc onPipelineErrorFromVerified*(s: StreamingSpeechVerified, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onDisconnectFromVerified*(s: StreamingSpeechVerified): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> CONNECTION_ERROR (HA disconnected during verified stream)")
  result = ConnectionError(SatelliteContext(s))

proc onWakeWordVerified*(s: Verifying): Processing {.transition.} =
  info("SatelliteFSM", "State: VERIFYING -> PROCESSING (wake word / intent verified)")
  result = Processing(SatelliteContext(s))

proc onPipelineEndFromVerifying*(s: Verifying): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: VERIFYING -> SILENT_DISMISSING (pipeline ended without verification)")
  result = SilentDismissing(SatelliteContext(s))

proc onStopDuringVerifying*(s: Verifying): Cancelling {.transition.} =
  info("SatelliteFSM", "State: VERIFYING -> CANCELLING (Stop command received during verifying)")
  result = Cancelling(SatelliteContext(s))

proc onStopDuringVerifyingToIdle*(s: Verifying): Idle {.transition.} =
  info("SatelliteFSM", "State: VERIFYING -> IDLE (Stop command received during verifying)")
  result = Idle(SatelliteContext())

proc onVerifyingTimeout*(s: Verifying): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: VERIFYING -> SILENT_DISMISSING (verification timeout)")
  result = SilentDismissing(SatelliteContext(s))

proc onPipelineErrorFromVerifying*(s: Verifying, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: VERIFYING -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onConnectionErrorFromVerifying*(s: Verifying): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: VERIFYING -> CONNECTION_ERROR (Home Assistant disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onSilenceTimeout*(s: StreamingSpeech): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> SILENT_DISMISSING (no speech recognized)")
  result = SilentDismissing(SatelliteContext(s))

proc onStopDuringListening*(s: StreamingSpeech): Cancelling {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> CANCELLING (Stop command received during listening)")
  result = Cancelling(SatelliteContext(s))

proc onStopDuringListeningToIdle*(s: StreamingSpeech): Idle {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> IDLE (Stop command received during listening)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromListening*(s: StreamingSpeech, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: STREAMING_SPEECH -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onTtsStarted*(s: Processing): Replying {.transition.} =
  info("SatelliteFSM", "State: PROCESSING -> REPLYING (TTS playback started)")
  result = Replying(SatelliteContext(s))

proc onIntentCompleteNoTts*(s: Processing): IntentCompleteNoTts {.transition.} =
  info("SatelliteFSM", "State: PROCESSING -> INTENT_COMPLETE_NO_TTS (on_end fired without TTS)")
  result = IntentCompleteNoTts(SatelliteContext(s))

proc onStopDuringThinking*(s: Processing): Cancelling {.transition.} =
  info("SatelliteFSM", "State: PROCESSING -> CANCELLING (Stop command received during thinking)")
  result = Cancelling(SatelliteContext(s))

proc onStopDuringThinkingToIdle*(s: Processing): Idle {.transition.} =
  info("SatelliteFSM", "State: PROCESSING -> IDLE (Stop command received during thinking)")
  result = Idle(SatelliteContext())

proc onDismissFromThinking*(s: Processing): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: PROCESSING -> SILENT_DISMISSING (no speech or intent recognized)")
  result = SilentDismissing(SatelliteContext(s))

proc onProcessingTimeout*(s: Processing): ActionableError {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = "server-timeout"
  error("SatelliteFSM", "State: PROCESSING -> ACTIONABLE_ERROR (server response timeout)")
  result = ActionableError(ctx)

proc onPipelineErrorFromThinking*(s: Processing, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: PROCESSING -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onTtsFinished*(s: Replying): Idle {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> IDLE (TTS playback finished)")
  result = Idle(SatelliteContext())

proc onTtsTimeout*(s: Replying): Idle {.transition.} =
  warn("SatelliteFSM", "State: REPLYING -> IDLE (TTS stream timeout)")
  result = Idle(SatelliteContext())

proc onStopDuringReplying*(s: Replying): Cancelling {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> CANCELLING (Stop command received during TTS)")
  result = Cancelling(SatelliteContext(s))

proc onStopDuringReplyingToIdle*(s: Replying): Idle {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> IDLE (Stop command received during TTS)")
  result = Idle(SatelliteContext())

proc onWakeWordDuringReplying*(s: Replying, word: string, angle: int): ReplyingBargeInAttempted {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.wakeWord = word
  ctx.beamAngle = angle
  info("SatelliteFSM", "State: REPLYING -> REPLYING_BARGE_IN_ATTEMPTED (wake_word: " & word & ")")
  result = ReplyingBargeInAttempted(ctx)

proc onPipelineErrorFromReplying*(s: Replying, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: REPLYING -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

proc onCancelFinished*(s: Cancelling): Idle {.transition.} =
  info("SatelliteFSM", "State: CANCELLING -> IDLE (cancel chime finished)")
  result = Idle(SatelliteContext())

proc onCancelFinishedToMedia*(s: Cancelling): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: CANCELLING -> PLAYING_MEDIA (restoring media audio)")
  result = PlayingMedia(SatelliteContext())

proc onCancelTimeout*(s: Cancelling): Idle {.transition.} =
  warn("SatelliteFSM", "State: CANCELLING -> IDLE (cancel chime timeout)")
  result = Idle(SatelliteContext())

proc onFollowUpRequested*(s: Replying): FollowUp {.transition.} =
  info("SatelliteFSM", "State: REPLYING -> FOLLOW_UP (continuous dialogue requested)")
  result = FollowUp(SatelliteContext(s))

proc onFollowUpReadyToListen*(s: FollowUp): StreamingSpeech {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> STREAMING_SPEECH (mic open for follow-up)")
  result = StreamingSpeech(SatelliteContext(s))

proc onFollowUpSpeechEnded*(s: FollowUp): Processing {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> PROCESSING (speech ended in follow-up)")
  result = Processing(SatelliteContext(s))

proc onStopDuringFollowUp*(s: FollowUp): Cancelling {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> CANCELLING (stop phrase detected in follow-up)")
  result = Cancelling(SatelliteContext(s))

proc onFollowUpTimeout*(s: FollowUp): Idle {.transition.} =
  info("SatelliteFSM", "State: FOLLOW_UP -> IDLE (dialogue timed out)")
  result = Idle(SatelliteContext())

proc onPipelineErrorFromFollowUp*(s: FollowUp, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: FOLLOW_UP -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

# --- Reified Barge-In Evaluation & Action Transitions ---
proc onBargeInConfirm*(s: ReplyingBargeInAttempted): BargedIn {.transition.} =
  info("SatelliteFSM", "State: REPLYING_BARGE_IN_ATTEMPTED -> BARGED_IN (stop word verified)")
  result = BargedIn(SatelliteContext(s))

proc onBargeInIgnore*(s: ReplyingBargeInAttempted): ReplyingBargeInIgnored {.transition.} =
  info("SatelliteFSM", "State: REPLYING_BARGE_IN_ATTEMPTED -> REPLYING_BARGE_IN_IGNORED (echo/non-stop ignored)")
  result = ReplyingBargeInIgnored(SatelliteContext(s))

proc onResumeReplying*(s: ReplyingBargeInIgnored): Replying {.transition.} =
  info("SatelliteFSM", "State: REPLYING_BARGE_IN_IGNORED -> REPLYING (resuming TTS playback)")
  result = Replying(SatelliteContext(s))

proc onResetBargedIn*(s: BargedIn): Idle {.transition.} =
  info("SatelliteFSM", "State: BARGED_IN -> IDLE (TTS playback canceled)")
  result = Idle(SatelliteContext())

# --- Non-TTS Intent Completion Action Transitions ---
proc onActionSuccess*(s: IntentCompleteNoTts): ActionSuccess {.transition.} =
  info("SatelliteFSM", "State: INTENT_COMPLETE_NO_TTS -> ACTION_SUCCESS (intent completed cleanly)")
  result = ActionSuccess(SatelliteContext(s))

proc onResetActionSuccess*(s: ActionSuccess): Idle {.transition.} =
  info("SatelliteFSM", "State: ACTION_SUCCESS -> IDLE (cue complete)")
  result = Idle(SatelliteContext())

# --- Reified Pipeline Error Evaluation Transitions ---
proc onClassifySilentError*(s: PipelineErrorEvaluating): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: PIPELINE_ERROR_EVALUATING -> SILENT_DISMISSING (benign error)")
  result = SilentDismissing(SatelliteContext(s))

proc onClassifyActionableError*(s: PipelineErrorEvaluating): ActionableError {.transition.} =
  warn("SatelliteFSM", "State: PIPELINE_ERROR_EVALUATING -> ACTIONABLE_ERROR (error cue scheduled)")
  result = ActionableError(SatelliteContext(s))

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
  result = Idle(SatelliteContext())

proc onAlertTimeout*(s: Alerting): Idle {.transition.} =
  warn("SatelliteFSM", "State: ALERTING -> IDLE (unattended timer timeout)")
  result = Idle(SatelliteContext())

# --- Announcement / Intercom Transitions ---
proc onAnnouncementStart*(s: Idle): Announcing {.transition.} =
  info("SatelliteFSM", "State: IDLE -> ANNOUNCING (server broadcast started)")
  result = Announcing(SatelliteContext(s))

proc onAnnouncementFromMedia*(s: PlayingMedia): Announcing {.transition.} =
  info("SatelliteFSM", "State: PLAYING_MEDIA -> ANNOUNCING (server broadcast started)")
  result = Announcing(SatelliteContext(s))

proc onAnnouncementEnd*(s: Announcing): Idle {.transition.} =
  info("SatelliteFSM", "State: ANNOUNCING -> IDLE (broadcast finished)")
  result = Idle(SatelliteContext())

proc onAnnouncementTimeout*(s: Announcing): Idle {.transition.} =
  warn("SatelliteFSM", "State: ANNOUNCING -> IDLE (announcement timeout)")
  result = Idle(SatelliteContext())

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

proc onOtaTimeout*(s: Updating): Idle {.transition.} =
  warn("SatelliteFSM", "State: UPDATING -> IDLE (OTA update timeout)")
  result = Idle(SatelliteContext(s))

# --- Offline / Disconnect Transitions ---
proc onDisconnectFromIdle*(s: Idle): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: IDLE -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromWaiting*(s: WaitingForSpeech): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: WAITING_FOR_SPEECH -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromStreaming*(s: StreamingSpeech): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: STREAMING_SPEECH -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromProcessing*(s: Processing): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: PROCESSING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromReplying*(s: Replying): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: REPLYING -> CONNECTION_ERROR (HA disconnected)")
  result = ConnectionError(SatelliteContext(s))

proc onDisconnectFromCancelling*(s: Cancelling): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: CANCELLING -> CONNECTION_ERROR (HA disconnected)")
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
proc onDismiss*(s: SilentDismissing): Idle {.transition.} =
  info("SatelliteFSM", "State: SILENT_DISMISSING -> IDLE (silent reset)")
  result = Idle(SatelliteContext())

proc onDismissToMedia*(s: SilentDismissing): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: SILENT_DISMISSING -> PLAYING_MEDIA (restoring media audio)")
  result = PlayingMedia(SatelliteContext())

proc onResetPipelineError*(s: ActionableError): Idle {.transition.} =
  info("SatelliteFSM", "State: ACTIONABLE_ERROR -> IDLE (error cue finished)")
  result = Idle(SatelliteContext())

proc onResetPipelineErrorToMedia*(s: ActionableError): PlayingMedia {.transition.} =
  info("SatelliteFSM", "State: ACTIONABLE_ERROR -> PLAYING_MEDIA (restoring media audio)")
  result = PlayingMedia(SatelliteContext())

proc onConnected*(s: ConnectionError): Idle {.transition.} =
  info("SatelliteFSM", "State: CONNECTION_ERROR -> IDLE (HA reconnected)")
  result = Idle(SatelliteContext())

proc onConnectedMuted*(s: ConnectionError): Muted {.transition.} =
  info("SatelliteFSM", "State: CONNECTION_ERROR -> MUTED (HA reconnected, mic was muted)")
  result = Muted(SatelliteContext())

# Semantic & Backward compatibility wrappers
proc onDisconnectFromWoken*(s: WaitingForSpeech): ConnectionError {.inline.} = onDisconnectFromWaiting(s)
proc onDisconnectFromListening*(s: StreamingSpeech): ConnectionError {.inline.} = onDisconnectFromStreaming(s)
proc onDisconnectFromThinking*(s: Processing): ConnectionError {.inline.} = onDisconnectFromProcessing(s)
proc onPipelineErrorFromWoken*(s: WaitingForSpeech, err: string): PipelineErrorEvaluating {.inline.} = onPipelineErrorFromWaiting(s, err)

verifyTypestates()

# --- Runtime C API Bridge for ESPHome ---

type
  AcousticFeedbackMode* = enum
    afmPostUtterance = 0
    afmImmediateNonBlocking = 1
    afmLegacyBlocking = 2
    afmVisualOnly = 3

  RuntimeState* = enum
    rsIdle = 0
    rsWaitingForSpeech = 1
    rsStreamingSpeech = 2
    rsProcessing = 3
    rsReplying = 4
    rsSilentDismissing = 5
    rsActionableError = 6
    rsConnectionError = 7
    rsMuted = 8
    rsFollowUp = 9
    rsPlayingMedia = 10
    rsAlerting = 11
    rsAnnouncing = 12
    rsUpdating = 13
    rsCancelling = 14
    rsReplyingBargeInAttempted = 15
    rsReplyingBargeInIgnored = 16
    rsBargedIn = 17
    rsIntentCompleteNoTts = 18
    rsActionSuccess = 19
    rsPipelineErrorEvaluating = 20
    rsVerifying = 21
    rsStreamingSpeechVerified = 22

const
  rsWoken* = rsWaitingForSpeech
  rsListening* = rsStreamingSpeech
  rsThinking* = rsProcessing
  rsSilentDismiss* = rsSilentDismissing
  rsPipelineError* = rsActionableError
  rsVerifyingWakeWord* = rsVerifying
  rsWakeWordVerified* = rsStreamingSpeechVerified

type
  SatelliteFSMInstance* = object
    case state*: RuntimeState
    of rsIdle:
      idleState*: Idle
    of rsWaitingForSpeech:
      waitingState*: WaitingForSpeech
    of rsStreamingSpeech:
      streamingState*: StreamingSpeech
    of rsStreamingSpeechVerified:
      verifiedState*: StreamingSpeechVerified
    of rsVerifying:
      verifyingState*: Verifying
    of rsProcessing:
      processingState*: Processing
    of rsReplying:
      replyingState*: Replying
    of rsCancelling:
      cancellingState*: Cancelling
    of rsSilentDismissing:
      dismissState*: SilentDismissing
    of rsActionableError:
      actErrState*: ActionableError
    of rsConnectionError:
      connErrState*: ConnectionError
    of rsMuted:
      mutedState*: Muted
    of rsFollowUp:
      followUpState*: FollowUp
    of rsPlayingMedia:
      mediaState*: PlayingMedia
    of rsAlerting:
      alertingState*: Alerting
    of rsAnnouncing:
      announcingState*: Announcing
    of rsUpdating:
      updatingState*: Updating
    of rsReplyingBargeInAttempted:
      bargeAttemptState*: ReplyingBargeInAttempted
    of rsReplyingBargeInIgnored:
      bargeIgnoredState*: ReplyingBargeInIgnored
    of rsBargedIn:
      bargedInState*: BargedIn
    of rsIntentCompleteNoTts:
      intentNoTtsState*: IntentCompleteNoTts
    of rsActionSuccess:
      actionSuccessState*: ActionSuccess
    of rsPipelineErrorEvaluating:
      evalErrState*: PipelineErrorEvaluating

var
  fsm*: SatelliteFSMInstance = SatelliteFSMInstance(
    state: rsIdle,
    idleState: Idle(SatelliteContext())
  )
  mediaWasPlaying*: bool = false
  micWasMuted*: bool = false
  configuredFeedbackMode*: AcousticFeedbackMode = afmLegacyBlocking
  speechActive*: bool = false
  lastSpeechActivityMs*: uint32 = 0
  speechStartMs*: uint32 = 0
  lastHeartbeatMs*: uint32 = 0
  lastObservedState*: RuntimeState = rsIdle
  stateEnteredMs*: uint32 = 0
  configuredProcessingStyle* = psSpinner
  configuredProcessingVolume* = 75.0'f32
  configuredWakeChimeSound* = wcBell
  wakeChimeEnabled* = true
  wakeChimeVolume* = 75.0'f32
  satellitePipeline* = newSatellitePipeline()

template currentState*(): RuntimeState = fsm.state

proc `currentState=`*(s: RuntimeState) =
  case s
  of rsIdle: fsm = SatelliteFSMInstance(state: rsIdle, idleState: Idle(SatelliteContext()))
  of rsWaitingForSpeech: fsm = SatelliteFSMInstance(state: rsWaitingForSpeech, waitingState: WaitingForSpeech(SatelliteContext()))
  of rsStreamingSpeech: fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: StreamingSpeech(SatelliteContext()))
  of rsStreamingSpeechVerified: fsm = SatelliteFSMInstance(state: rsStreamingSpeechVerified, verifiedState: StreamingSpeechVerified(SatelliteContext()))
  of rsVerifying: fsm = SatelliteFSMInstance(state: rsVerifying, verifyingState: Verifying(SatelliteContext()))
  of rsProcessing: fsm = SatelliteFSMInstance(state: rsProcessing, processingState: Processing(SatelliteContext()))
  of rsReplying: fsm = SatelliteFSMInstance(state: rsReplying, replyingState: Replying(SatelliteContext()))
  of rsCancelling: fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: Cancelling(SatelliteContext()))
  of rsSilentDismissing: fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: SilentDismissing(SatelliteContext()))
  of rsActionableError: fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: ActionableError(SatelliteContext()))
  of rsConnectionError: fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: ConnectionError(SatelliteContext()))
  of rsMuted: fsm = SatelliteFSMInstance(state: rsMuted, mutedState: Muted(SatelliteContext()))
  of rsFollowUp: fsm = SatelliteFSMInstance(state: rsFollowUp, followUpState: FollowUp(SatelliteContext()))
  of rsPlayingMedia: fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: PlayingMedia(SatelliteContext()))
  of rsAlerting: fsm = SatelliteFSMInstance(state: rsAlerting, alertingState: Alerting(SatelliteContext()))
  of rsAnnouncing: fsm = SatelliteFSMInstance(state: rsAnnouncing, announcingState: Announcing(SatelliteContext()))
  of rsUpdating: fsm = SatelliteFSMInstance(state: rsUpdating, updatingState: Updating(SatelliteContext()))
  of rsReplyingBargeInAttempted: fsm = SatelliteFSMInstance(state: rsReplyingBargeInAttempted, bargeAttemptState: ReplyingBargeInAttempted(SatelliteContext()))
  of rsReplyingBargeInIgnored: fsm = SatelliteFSMInstance(state: rsReplyingBargeInIgnored, bargeIgnoredState: ReplyingBargeInIgnored(SatelliteContext()))
  of rsBargedIn: fsm = SatelliteFSMInstance(state: rsBargedIn, bargedInState: BargedIn(SatelliteContext()))
  of rsIntentCompleteNoTts: fsm = SatelliteFSMInstance(state: rsIntentCompleteNoTts, intentNoTtsState: IntentCompleteNoTts(SatelliteContext()))
  of rsActionSuccess: fsm = SatelliteFSMInstance(state: rsActionSuccess, actionSuccessState: ActionSuccess(SatelliteContext()))
  of rsPipelineErrorEvaluating: fsm = SatelliteFSMInstance(state: rsPipelineErrorEvaluating, evalErrState: PipelineErrorEvaluating(SatelliteContext()))

template ctxIdle*(): Idle = fsm.idleState
template ctxWaiting*(): WaitingForSpeech = fsm.waitingState
template ctxStreaming*(): StreamingSpeech = fsm.streamingState
template ctxVerified*(): StreamingSpeechVerified = fsm.verifiedState
template ctxProcessing*(): Processing = fsm.processingState
template ctxReplying*(): Replying = fsm.replyingState

# Backward-compatibility aliases for legacy code and tests
template ctxWoken*(): WaitingForSpeech = fsm.waitingState
template ctxListening*(): StreamingSpeech = fsm.streamingState
template ctxThinking*(): Processing = fsm.processingState


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



var gHardwareAbortCb: proc() {.cdecl.} = nil

proc nim_satellite_register_hardware_abort_cb*(cb: proc() {.cdecl.}) {.exportc, cdecl.} =
  gHardwareAbortCb = cb

proc notifyHardwareAbort*() =
  if gHardwareAbortCb != nil:
    gHardwareAbortCb()

proc returnFromIdleToMediaOrIdle*() =
  if mediaWasPlaying:
    mediaWasPlaying = false
    let media = onMediaPlay(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: media)
  else:
    if fsm.state != rsIdle:
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: Idle(SatelliteContext()))

proc returnFromSilentDismiss*() =
  if fsm.state == rsSilentDismissing:
    if mediaWasPlaying:
      mediaWasPlaying = false
      let media = onDismissToMedia(fsm.dismissState)
      fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: media)
    else:
      let idle = onDismiss(fsm.dismissState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)

proc returnFromPipelineError*() =
  if fsm.state == rsActionableError:
    if mediaWasPlaying:
      mediaWasPlaying = false
      let media = onResetPipelineErrorToMedia(fsm.actErrState)
      fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: media)
    else:
      let idle = onResetPipelineError(fsm.actErrState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)

proc returnFromCancelFlow*() =
  if fsm.state == rsCancelling:
    if mediaWasPlaying:
      mediaWasPlaying = false
      let media = onCancelFinishedToMedia(fsm.cancellingState)
      fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: media)
    else:
      let idle = onCancelFinished(fsm.cancellingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)

proc nim_satellite_cancel_done*(ok: bool) {.exportc, cdecl.} =
  if fsm.state == rsCancelling:
    returnFromCancelFlow()

proc nim_satellite_is_cancelling*(): bool {.exportc, cdecl.} =
  result = (fsm.state == rsCancelling)

proc nim_set_acoustic_feedback_mode*(mode: cint) {.exportc, cdecl.} =
  if mode >= 0 and mode <= 3:
    configuredFeedbackMode = AcousticFeedbackMode(mode)
    info("Satellite", "Acoustic feedback mode set to: " & $configuredFeedbackMode)

proc nim_get_acoustic_feedback_mode*(): cint {.exportc, cdecl.} =
  result = cint(configuredFeedbackMode)

proc nim_satellite_wake_word*(word: cstring, angle: cint) {.exportc, cdecl.} =
  case fsm.state
  of rsIdle:
    if configuredFeedbackMode in {afmPostUtterance, afmImmediateNonBlocking, afmVisualOnly}:
      let next = onWakeWordDirect(fsm.idleState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: next)
      speechActive = false
      speechStartMs = 0
      lastSpeechActivityMs = satelliteNowMs()
    else:
      let next = onWakeWord(fsm.idleState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsWaitingForSpeech, waitingState: next)
  of rsPlayingMedia:
    mediaWasPlaying = true
    if configuredFeedbackMode in {afmPostUtterance, afmImmediateNonBlocking, afmVisualOnly}:
      let next = onWakeWordDirectFromMedia(fsm.mediaState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: next)
      speechActive = false
      speechStartMs = 0
      lastSpeechActivityMs = satelliteNowMs()
    else:
      let next = onWakeWordFromMedia(fsm.mediaState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsWaitingForSpeech, waitingState: next)
  of rsAlerting:
    if configuredFeedbackMode in {afmPostUtterance, afmImmediateNonBlocking, afmVisualOnly}:
      let next = onWakeWordDirectDuringAlert(fsm.alertingState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: next)
      speechActive = false
      speechStartMs = 0
      lastSpeechActivityMs = satelliteNowMs()
    else:
      let next = onWakeWordDuringAlert(fsm.alertingState, $word, int(angle))
      fsm = SatelliteFSMInstance(state: rsWaitingForSpeech, waitingState: next)
  of rsReplying:
    # Reified Barge-In:
    # In Replying, wake word arrives -> ReplyingBargeInAttempted.
    # Evaluates: if word in {'Stop', 'stop'} -> BargedIn -> Idle. Else -> ReplyingBargeInIgnored -> Replying.
    let attempt = onWakeWordDuringReplying(fsm.replyingState, $word, int(angle))
    fsm = SatelliteFSMInstance(state: rsReplyingBargeInAttempted, bargeAttemptState: attempt)
    let w = ($word).toLowerAscii
    if w == "stop":
      notifyHardwareAbort()
      let barged = onBargeInConfirm(fsm.bargeAttemptState)
      fsm = SatelliteFSMInstance(state: rsBargedIn, bargedInState: barged)
      let idle = onResetBargedIn(fsm.bargedInState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromIdleToMediaOrIdle()
    else:
      let ignored = onBargeInIgnore(fsm.bargeAttemptState)
      let resumed = onResumeReplying(ignored)
      fsm = SatelliteFSMInstance(state: rsReplying, replyingState: resumed)
  else:
    warn("SatelliteFSM", "Wake word ignored: satellite in state " & $fsm.state)

proc nim_satellite_chime_done*(ok: bool) {.exportc, cdecl.} =
  if fsm.state == rsWaitingForSpeech:
    if ok:
      let next = onChimeFinished(fsm.waitingState)
      fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: next)
      speechActive = false
      speechStartMs = 0
      lastSpeechActivityMs = satelliteNowMs()
    else:
      let dismiss = onChimeFailed(fsm.waitingState)
      fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: dismiss)

proc nim_satellite_speech_start*() {.exportc, cdecl.} =
  if fsm.state in {rsStreamingSpeech, rsStreamingSpeechVerified, rsFollowUp}:
    speechActive = true
    let now = satelliteNowMs()
    lastSpeechActivityMs = now
    if speechStartMs == 0:
      speechStartMs = now
    info("SatelliteFSM", "Speech started in state " & $fsm.state)

proc nim_satellite_listening_active*() {.exportc, cdecl.} =
  if fsm.state in {rsStreamingSpeech, rsStreamingSpeechVerified, rsFollowUp}:
    speechActive = false
    lastSpeechActivityMs = satelliteNowMs()
    speechStartMs = 0
    info("SatelliteFSM", "Microphone listening active in state " & $fsm.state)

proc nim_satellite_speech_ended*() {.exportc, cdecl.} =
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsStreamingSpeech:
    let next = onSpeechEnded(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsVerifying, verifyingState: next)
    # Note: In Verifying state, do NOT start processing audio loop!
  elif fsm.state == rsStreamingSpeechVerified:
    let next = onSpeechEnded(fsm.verifiedState)
    fsm = SatelliteFSMInstance(state: rsProcessing, processingState: next)
    satellitePipeline.startProcessingLoop(configuredProcessingStyle)
  elif fsm.state == rsFollowUp:
    let next = onFollowUpSpeechEnded(fsm.followUpState)
    fsm = SatelliteFSMInstance(state: rsProcessing, processingState: next)
    satellitePipeline.startProcessingLoop(configuredProcessingStyle)

proc nim_satellite_wake_word_verified*() {.exportc, cdecl.} =
  if fsm.state == rsStreamingSpeech:
    lastSpeechActivityMs = satelliteNowMs()
    let next = onWakeWordVerified(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsStreamingSpeechVerified, verifiedState: next)
    info("Satellite", "Hardware LED ring locked to Verified while speech streaming continues")
  elif fsm.state == rsVerifying:
    speechActive = false
    speechStartMs = 0
    lastSpeechActivityMs = satelliteNowMs()
    let next = onWakeWordVerified(fsm.verifyingState)
    fsm = SatelliteFSMInstance(state: rsProcessing, processingState: next)
    satellitePipeline.startProcessingLoop(configuredProcessingStyle)

proc nim_satellite_silence_timeout*() {.exportc, cdecl.} =
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsStreamingSpeech:
    let dismiss = onSilenceTimeout(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: dismiss)
  elif fsm.state == rsStreamingSpeechVerified:
    let dismiss = onSilenceTimeout(fsm.verifiedState)
    fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: dismiss)
  elif fsm.state == rsWaitingForSpeech:
    let dismiss = onSilenceTimeoutFromWaiting(fsm.waitingState)
    fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: dismiss)
  elif fsm.state == rsFollowUp:
    let idle = onFollowUpTimeout(fsm.followUpState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
    returnFromIdleToMediaOrIdle()

proc nim_satellite_tts_start*() {.exportc, cdecl.} =
  satellitePipeline.stopProcessingLoop()
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsProcessing:
    let next = onTtsStarted(fsm.processingState)
    fsm = SatelliteFSMInstance(state: rsReplying, replyingState: next)

proc nim_satellite_tts_end*() {.exportc, cdecl.} =
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsReplying:
    let idle = onTtsFinished(fsm.replyingState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
    returnFromIdleToMediaOrIdle()

proc nim_satellite_pipeline_end*() {.exportc, cdecl.} =
  ## Non-TTS Intent Completion: In Processing, when on_end fires without TTS
  ## -> IntentCompleteNoTts -> ActionSuccess -> Idle (resolving thinking deadlock)
  satellitePipeline.stopProcessingLoop()
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsProcessing:
    let intentEnd = onIntentCompleteNoTts(fsm.processingState)
    fsm = SatelliteFSMInstance(state: rsIntentCompleteNoTts, intentNoTtsState: intentEnd)
    let success = onActionSuccess(fsm.intentNoTtsState)
    fsm = SatelliteFSMInstance(state: rsActionSuccess, actionSuccessState: success)
    let idle = onResetActionSuccess(fsm.actionSuccessState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
    returnFromIdleToMediaOrIdle()
  elif fsm.state == rsVerifying:
    let dismiss = onPipelineEndFromVerifying(fsm.verifyingState)
    let idle = onDismiss(dismiss)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
    returnFromIdleToMediaOrIdle()

proc nim_satellite_follow_up*() {.exportc, cdecl.} =
  speechActive = false
  speechStartMs = 0
  lastSpeechActivityMs = satelliteNowMs()
  if fsm.state == rsReplying:
    let next = onFollowUpRequested(fsm.replyingState)
    fsm = SatelliteFSMInstance(state: rsFollowUp, followUpState: next)
  elif fsm.state == rsFollowUp:
    let next = onFollowUpReadyToListen(fsm.followUpState)
    fsm = SatelliteFSMInstance(state: rsStreamingSpeech, streamingState: next)

proc nim_satellite_stop_word*() {.exportc, cdecl.} =
  satellitePipeline.stopProcessingLoop()
  case fsm.state
  of rsWaitingForSpeech:
    let cancel = onStopDuringWoken(fsm.waitingState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsStreamingSpeech:
    let cancel = onStopDuringListening(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsStreamingSpeechVerified:
    let cancel = onStopDuringVerified(fsm.verifiedState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsVerifying:
    let cancel = onStopDuringVerifying(fsm.verifyingState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsProcessing:
    let cancel = onStopDuringThinking(fsm.processingState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsReplying:
    let cancel = onStopDuringReplying(fsm.replyingState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsAlerting:
    let idle = onAlertDismiss(fsm.alertingState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
  of rsFollowUp:
    let cancel = onStopDuringFollowUp(fsm.followUpState)
    fsm = SatelliteFSMInstance(state: rsCancelling, cancellingState: cancel)
  of rsCancelling:
    discard
  else:
    debug("SatelliteFSM", "Stop word ignored in state " & $fsm.state)

proc nim_satellite_error*(code: cstring) {.exportc, cdecl.} =
  let err = $code
  notifyHardwareAbort()
  if satellitePipeline != nil:
    satellitePipeline.stopProcessingLoop()

  var evalState: PipelineErrorEvaluating
  case fsm.state
  of rsWaitingForSpeech:
    evalState = onPipelineErrorFromWaiting(fsm.waitingState, err)
  of rsStreamingSpeech:
    evalState = onPipelineErrorFromListening(fsm.streamingState, err)
  of rsStreamingSpeechVerified:
    evalState = onPipelineErrorFromVerified(fsm.verifiedState, err)
  of rsVerifying:
    evalState = onPipelineErrorFromVerifying(fsm.verifyingState, err)
  of rsProcessing:
    evalState = onPipelineErrorFromThinking(fsm.processingState, err)
  of rsReplying:
    evalState = onPipelineErrorFromReplying(fsm.replyingState, err)
  of rsFollowUp:
    evalState = onPipelineErrorFromFollowUp(fsm.followUpState, err)
  else:
    mediaWasPlaying = false
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: Idle(SatelliteContext()))
    return

  fsm = SatelliteFSMInstance(state: rsPipelineErrorEvaluating, evalErrState: evalState)

  # Reified Error Evaluation (Zero-Variable-Branching Invariant)
  if err in ["stt-no-text-recognized", "duplicate_wake_up_detected", "timeout"]:
    let dismiss = onClassifySilentError(fsm.evalErrState)
    fsm = SatelliteFSMInstance(state: rsSilentDismissing, dismissState: dismiss)
  else:
    let actErr = onClassifyActionableError(fsm.evalErrState)
    fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: actErr)

proc nim_satellite_set_muted*(muted: bool) {.exportc, cdecl.} =
  micWasMuted = muted
  if muted and fsm.state == rsIdle:
    let next = onMute(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsMuted, mutedState: next)
  elif not muted and fsm.state == rsMuted:
    let next = onUnmute(fsm.mutedState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

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
  if fsm.state == rsIdle:
    let next = onMediaPlay(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsPlayingMedia, mediaState: next)

proc nim_satellite_media_stop*() {.exportc, cdecl.} =
  if fsm.state == rsPlayingMedia:
    let next = onMediaStop(fsm.mediaState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

proc nim_satellite_alert_start*() {.exportc, cdecl.} =
  if fsm.state == rsIdle:
    let next = onAlertStart(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsAlerting, alertingState: next)
  elif fsm.state == rsPlayingMedia:
    let next = onAlertFromMedia(fsm.mediaState)
    fsm = SatelliteFSMInstance(state: rsAlerting, alertingState: next)

proc nim_satellite_alert_stop*() {.exportc, cdecl.} =
  if fsm.state == rsAlerting:
    let next = onAlertDismiss(fsm.alertingState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

proc nim_satellite_announcement_start*() {.exportc, cdecl.} =
  if fsm.state == rsIdle:
    let next = onAnnouncementStart(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsAnnouncing, announcingState: next)
  elif fsm.state == rsPlayingMedia:
    let next = onAnnouncementFromMedia(fsm.mediaState)
    fsm = SatelliteFSMInstance(state: rsAnnouncing, announcingState: next)

proc nim_satellite_announcement_end*() {.exportc, cdecl.} =
  if fsm.state == rsAnnouncing:
    let next = onAnnouncementEnd(fsm.announcingState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

proc nim_satellite_ota_start*() {.exportc, cdecl.} =
  case fsm.state
  of rsIdle:
    let next = onOtaStart(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsUpdating, updatingState: next)
  of rsMuted:
    let next = onOtaFromMuted(fsm.mutedState)
    fsm = SatelliteFSMInstance(state: rsUpdating, updatingState: next)
  of rsPlayingMedia:
    let next = onOtaFromMedia(fsm.mediaState)
    fsm = SatelliteFSMInstance(state: rsUpdating, updatingState: next)
  of rsConnectionError:
    let next = onOtaFromConnErr(fsm.connErrState)
    fsm = SatelliteFSMInstance(state: rsUpdating, updatingState: next)
  else:
    discard

proc nim_satellite_ota_end*(ok: bool) {.exportc, cdecl.} =
  if fsm.state == rsUpdating:
    let next = onOtaComplete(fsm.updatingState)
    fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

include satellite_system

proc nim_satellite_disconnected*() {.exportc, cdecl.} =
  case fsm.state
  of rsIdle:
    let next = onDisconnectFromIdle(fsm.idleState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsWaitingForSpeech:
    let next = onDisconnectFromWaiting(fsm.waitingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsStreamingSpeech:
    let next = onDisconnectFromStreaming(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsStreamingSpeechVerified:
    let next = onDisconnectFromVerified(fsm.verifiedState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsVerifying:
    let next = onConnectionErrorFromVerifying(fsm.verifyingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsProcessing:
    let next = onDisconnectFromProcessing(fsm.processingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsReplying:
    let next = onDisconnectFromReplying(fsm.replyingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsFollowUp:
    let next = onDisconnectFromFollowUp(fsm.followUpState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsMuted:
    let next = onDisconnectFromMuted(fsm.mutedState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsPlayingMedia:
    let next = onDisconnectFromMedia(fsm.mediaState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsAlerting:
    let next = onDisconnectFromAlerting(fsm.alertingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsAnnouncing:
    let next = onDisconnectFromAnnouncing(fsm.announcingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  of rsCancelling:
    let next = onDisconnectFromCancelling(fsm.cancellingState)
    fsm = SatelliteFSMInstance(state: rsConnectionError, connErrState: next)
  else:
    discard

proc nim_satellite_connected*() {.exportc, cdecl.} =
  if fsm.state == rsConnectionError:
    if micWasMuted:
      let next = onConnectedMuted(fsm.connErrState)
      fsm = SatelliteFSMInstance(state: rsMuted, mutedState: next)
    else:
      let next = onConnected(fsm.connErrState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: next)

proc nim_satellite_get_state*(): cint {.exportc, cdecl.} =
  result = cint(ord(fsm.state))

proc nim_satellite_is_muted*(): bool {.exportc, cdecl.} =
  result = (fsm.state == rsMuted)

proc nim_satellite_is_media_playing*(): bool {.exportc, cdecl.} =
  result = (fsm.state == rsPlayingMedia)

proc nim_satellite_is_alerting*(): bool {.exportc, cdecl.} =
  result = (fsm.state == rsAlerting)

proc nim_satellite_is_processing*(): bool {.exportc, cdecl.} =
  if satellitePipeline != nil:
    satellitePipeline.isProcessing()
  else:
    false

proc nim_satellite_get_processing_style*(): cint {.exportc, cdecl.} =
  cint(ord(configuredProcessingStyle))

esphomeSetup:
  info("SatelliteFSM", "Reified Event-Typestate Satellite FSM initialized")
  if satellitePipeline != nil and satellitePipeline.processingLoop != nil:
    satellitePipeline.processingLoop.onTick = proc(style: ProcessingSoundStyle, vol: float32, count: int) =
      if style == psCustom:
        debug("SatelliteAudio", "Streaming custom audio sample from flash partition sound_data (count=" & $count & ")")
      else:
        debug("SatelliteAudio", "Processing sound tick: style=" & $style & " count=" & $count)

proc nim_satellite_reset_for_test*() =
  fsm = SatelliteFSMInstance(state: rsIdle, idleState: Idle(SatelliteContext()))
  mediaWasPlaying = false
  micWasMuted = false
  speechActive = false
  lastSpeechActivityMs = 0
  speechStartMs = 0
  lastHeartbeatMs = 0
  lastObservedState = rsIdle
  stateEnteredMs = 0
  gSimulatedMillis = -1
  gHardwareAbortCb = nil
  configuredFeedbackMode = afmLegacyBlocking
  nim_dma_stream_reset()
  if satellitePipeline != nil:
    satellitePipeline.stopProcessingLoop()

proc satelliteLoop*(now: uint32) =
  if fsm.state != lastObservedState:
    let prevState = lastObservedState
    lastObservedState = fsm.state
    stateEnteredMs = now
    lastSpeechActivityMs = now
    if not (prevState == rsStreamingSpeech and fsm.state == rsStreamingSpeechVerified):
      speechActive = false
      speechStartMs = 0

  if satellitePipeline != nil:
    satellitePipeline.tick(now)

  let dmaTickRes = nim_dma_stream_tick(now)
  if dmaTickRes == 2:
    warn("SatelliteDMA", "DMA playback stream lease expired or stalled. Aborting stream.")
    notifyHardwareAbort()
    case fsm.state
    of rsWaitingForSpeech:
      warn("SatelliteFSM", "DMA stream lease expired during Woken chime. Triggering PipelineError.")
      let pErr = onChimeTimeout(fsm.waitingState)
      fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: pErr)
    of rsProcessing:
      warn("SatelliteFSM", "DMA stream lease expired during Thinking loop. Triggering PipelineError.")
      if satellitePipeline != nil:
        satellitePipeline.stopProcessingLoop()
      let pErr = onProcessingTimeout(fsm.processingState)
      fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: pErr)
    of rsReplying:
      warn("SatelliteFSM", "DMA stream lease expired during Replying. Returning to Idle.")
      let idle = onTtsTimeout(fsm.replyingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromIdleToMediaOrIdle()
    of rsCancelling:
      warn("SatelliteFSM", "DMA stream lease expired during Cancelling. Returning to Idle.")
      let idle = onCancelTimeout(fsm.cancellingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromCancelFlow()
    else:
      discard

  let elapsed = diffMs(now, stateEnteredMs)

  case fsm.state
  of rsWaitingForSpeech:
    if elapsed >= 5000:
      warn("SatelliteFSM", "Watchdog: Woken state timed out after 5s. Triggering PipelineError.")
      notifyHardwareAbort()
      let pErr = onChimeTimeout(fsm.waitingState)
      fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: pErr)
  of rsStreamingSpeech, rsStreamingSpeechVerified:
    if speechActive:
      if diffMs(now, speechStartMs) >= 30000:
        warn("SatelliteFSM", "Watchdog: Listening speech exceeded 30s limit. Triggering speech ended.")
        notifyHardwareAbort()
        nim_satellite_speech_ended()
    else:
      let silenceElapsed = diffMs(now, lastSpeechActivityMs)
      if silenceElapsed >= 15000:
        warn("SatelliteFSM", "Watchdog: Listening state timed out after 15s of silence. Returning to Idle.")
        notifyHardwareAbort()
        nim_satellite_silence_timeout()
  of rsVerifying:
    if elapsed >= 10000:
      warn("SatelliteFSM", "Watchdog: Verifying state timed out after 10s. Returning to Idle.")
      notifyHardwareAbort()
      let dismiss = onVerifyingTimeout(fsm.verifyingState)
      let idle = onDismiss(dismiss)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromIdleToMediaOrIdle()
  of rsProcessing:
    if elapsed >= 20000:
      warn("SatelliteFSM", "Watchdog: Thinking state timed out after 20s. Triggering PipelineError.")
      notifyHardwareAbort()
      if satellitePipeline != nil:
        satellitePipeline.stopProcessingLoop()
      let pErr = onProcessingTimeout(fsm.processingState)
      fsm = SatelliteFSMInstance(state: rsActionableError, actErrState: pErr)
  of rsReplying:
    if elapsed >= 60000:
      warn("SatelliteFSM", "Watchdog: Replying state timed out after 60s. Returning to Idle.")
      notifyHardwareAbort()
      let idle = onTtsTimeout(fsm.replyingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromIdleToMediaOrIdle()
  of rsCancelling:
    if elapsed >= 3000:
      warn("SatelliteFSM", "Watchdog: Cancelling state timed out after 3s. Returning to Idle.")
      notifyHardwareAbort()
      let idle = onCancelTimeout(fsm.cancellingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
      returnFromCancelFlow()
  of rsFollowUp:
    if speechActive:
      if diffMs(now, speechStartMs) >= 30000:
        warn("SatelliteFSM", "Watchdog: FollowUp speech exceeded 30s limit. Triggering speech ended.")
        notifyHardwareAbort()
        nim_satellite_speech_ended()
    else:
      let silenceElapsed = diffMs(now, lastSpeechActivityMs)
      if silenceElapsed >= 15000:
        warn("SatelliteFSM", "Watchdog: FollowUp state timed out after 15s of silence. Returning to Idle.")
        notifyHardwareAbort()
        let idle = onFollowUpTimeout(fsm.followUpState)
        fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
        returnFromIdleToMediaOrIdle()
  of rsSilentDismissing:
    if elapsed >= 500:
      returnFromSilentDismiss()
  of rsActionableError:
    if elapsed >= 2000:
      returnFromPipelineError()
  of rsAlerting:
    if elapsed >= 300000:
      warn("SatelliteFSM", "Watchdog: Alerting state timed out after 5m. Returning to Idle.")
      let idle = onAlertTimeout(fsm.alertingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
  of rsAnnouncing:
    if elapsed >= 30000:
      warn("SatelliteFSM", "Watchdog: Announcing state timed out after 30s. Returning to Idle.")
      let idle = onAnnouncementTimeout(fsm.announcingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
  of rsUpdating:
    if elapsed >= 300000:
      warn("SatelliteFSM", "Watchdog: Updating state timed out after 5m. Returning to Idle.")
      let idle = onOtaTimeout(fsm.updatingState)
      fsm = SatelliteFSMInstance(state: rsIdle, idleState: idle)
  else:
    discard

  # Immediately update state tracking if state changed during loop evaluation
  if fsm.state != lastObservedState:
    let prevState = lastObservedState
    lastObservedState = fsm.state
    stateEnteredMs = now
    lastSpeechActivityMs = now
    if not (prevState == rsStreamingSpeech and fsm.state == rsStreamingSpeechVerified):
      speechActive = false
      speechStartMs = 0

  if diffMs(now, lastHeartbeatMs) >= 10000:
    lastHeartbeatMs = now
    info("Satellite", "Heartbeat: state=" & $fsm.state & " uptime=" & $(now div 1000) & "s heap=" & $getFreeHeap())


esphomeLoop:
  satelliteLoop(satelliteNowMs())


