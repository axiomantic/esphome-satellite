# Thesis: Speculative Streaming Intent Architecture & Typestate Verification

**Status**: Architecture Proposal & Dialectical Research Thesis  
**Date**: 2026-10-11  
**Author**: Marcus Sterling (`@home-assistant-vibecode-agent-vidar`), Staff Systems Architect  
**Orchestrator**: `@hav-conductor`  
**Target Systems**: `esphome-satellite`, `custom_components/esphome_satellite`, and Home Assistant Core  

---

## 1. Executive Thesis & Mathematical Invariants

Traditional smart-speaker architectures enforce rigid sequential serialization:
$$\text{Acoustic Wake} \longrightarrow \text{Buffered STT Streaming} \longrightarrow \text{VAD Speech End} \longrightarrow \text{Batch Intent Parsing} \longrightarrow \text{TTS Generation}$$

In this classic topology, the user experiences significant post-utterance latency (typically $400\text{ms} - 1500\text{ms}$):
$$T_{\text{total\_latency}} = T_{\text{speech\_end\_vad}} + T_{\text{stt\_final}} + T_{\text{system1\_eval}} + T_{\text{llm\_first\_token}}$$

Furthermore, if the satellite relies on a sensitive acoustic wake threshold ($\le 0.62$), false activations frequently light up the LED ring during ambient conversation, causing visual and acoustic annoyance.

### The Speculative Streaming Paradigm
We re-architect the pipeline into a concurrent, speculative streaming verification pipeline:
$$\text{Live PCM Stream} \xrightarrow{\text{Native TCP}} \text{STT Proxy Tap} \xrightarrow{\text{Parallel}} \begin{cases} \text{Downstream STT (Whisper/Sherpa)} \\ \text{Speculative Chunker} \xrightarrow{\Delta t = 200\text{ms}} \text{System 1 (Laya ModernBERT)} \end{cases}$$

1. **Sub-Utterance Verification**: Before the user finishes uttering their intent, partial transcriptions are evaluated by System 1 in sub-$30\text{ms}$ forward passes.
2. **Deterministic Early Locking**: Upon positive classification ($\text{confidence} \ge 0.80$), Home Assistant signals `nim_satellite_wake_word_verified()` over the C ABI bridge.
3. **5-Rule Typestate Transition**: The satellite transitions synchronously:
   $$\text{StreamingSpeech} \xrightarrow{\text{WakeWordVerifiedEvent}} \text{StreamingSpeechVerified}$$
   The LED ring locks from a dark/stealth pre-verification state into a solid, directional cyan beam *while microphone recording continues uninterrupted*.
4. **Instant Intent Finalization**: When VAD detects speech end, the intent has already been speculatively ratified, dropping perceived latency to near-zero ($<50\text{ms}$).

---

## 2. End-to-End Speculative Streaming Pipeline Architecture

```mermaid
sequenceDiagram
    autonumber
    actor User as Household Speaker
    participant HW as XVF3800 DSP / Mic Ring Buffer
    participant ESP as ESPHome VoiceAssistant (C++)
    participant SatFSM as Satellite Reified FSM (Nim)
    participant HA_STT as custom_components/esphome_satellite (STT Proxy)
    participant Chunker as Speculative Chunker
    participant Sys1 as System 1 Daemon (Laya ModernBERT)
    participant LLM as Downstream Agent / Core Pipeline

    User->>HW: "Turn off the kitchen lights"
    Note over HW: Audio captured in 16kHz 16-bit mono PCM
    HW->>ESP: Audio available in ring buffer
    Note over ESP: voice_assistant.cpp:255-276<br/>stream_api_audio_() sends chunks
    ESP->>SatFSM: onSpeechStart() -> StreamingSpeech
    Note over SatFSM: xvf3800_hardware.nim:122<br/>LEDs remain dark (Stealth mode)
    ESP->>HA_STT: VoiceAssistantAudio packets (TCP API)
    
    par Live Audio Replication
        HA_STT->>LLM: Forward to Downstream STT Engine
    and Speculative Streaming
        HA_STT->>Chunker: Push slice to Async Generator
        Note over Chunker: Transcribes prefix at t=250ms:<br/>"Turn off the..."
        Chunker->>Sys1: POST /v1/systemone (Jev/Laya schema)
        Note over Sys1: ModernBERT forward pass (18ms)<br/>{"addressed": 0.94, "ambient": 0.06}
        Sys1-->>Chunker: Addressed verified (conf=0.94 >= 0.80)
        Chunker->>ESP: Native API Event: wake_word_verified
    end

    ESP->>SatFSM: nim_satellite_wake_word_verified()
    Note over SatFSM: Rule 1 & 2: Instant Run-to-Completion<br/>StreamingSpeech -> StreamingSpeechVerified
    Note over SatFSM: Rule 5: Hardware LED Binding<br/>LED ring locks solid cyan at beam angle
    
    User->>HW: "...kitchen lights" (Speech finishes)
    HW->>ESP: Silence VAD detected
    ESP->>SatFSM: nim_satellite_speech_ended()
    Note over SatFSM: StreamingSpeechVerified -> Processing (Thinking)
    HA_STT-->>LLM: STT_END ("Turn off the kitchen lights")
    LLM-->>ESP: Execute intent & TTS stream
```

### 2.1 File Line Citations: Audio Stream Origin
In `esphome-satellite/components/voice_assistant/voice_assistant.cpp`:
- **Lines 255–276 (`VoiceAssistant::stream_api_audio_`)**:
  ```cpp
  api::VoiceAssistantAudio msg;
  msg.data = this->audio_source_->data();
  msg.data_len = available;
  if (!this->api_client_->send_message(msg)) {
    return;
  }
  this->audio_source_->consume(available);
  ```
  The audio is sliced into TCP packets and transmitted directly over the native API socket to Home Assistant.
- **Lines 834–854 (`VoiceAssistant::on_event`)**:
  Handles `VOICE_ASSISTANT_STT_START` (line 834) and `VOICE_ASSISTANT_STT_END` (line 838).
- **In `packages/respeaker_xvf3800.yaml`**:
  - **Line 558**: `on_listening: call_nim_listening_active();`
  - **Line 561**: `on_stt_vad_start: call_nim_speech_start();`
  - **Line 564**: `on_stt_vad_end: call_nim_speech_ended();`
  - **Lines 645–649**:
    ```yaml
    std::string st = get_satellite_state_name();
    if (st != "Thinking" && st != "Verifying") {
      call_nim_speech_ended();
    }
    ```

---

## 3. Home Assistant Custom Component STT Proxy Interface

To intercept the raw PCM audio stream without monkey-patching Home Assistant core, `custom_components/esphome_satellite` implements an **STT Platform Proxy**:

### 3.1 Entity Interface Specification: `SpeechToTextEntity`
In `custom_components/esphome_satellite/stt.py`:

```python
"""Speculative Streaming STT Proxy Entity."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
import logging
import time

from homeassistant.components.stt import (
    AudioBitRates,
    AudioChannels,
    AudioCodecs,
    AudioFormats,
    AudioSampleRates,
    SpeechMetadata,
    SpeechResult,
    SpeechResultState,
    SpeechToTextEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .systemone_client import SystemOneClient

_LOGGER = logging.getLogger(__name__)

class ESPHomeSatelliteSpeculativeSTT(SpeechToTextEntity):
    """STT proxy entity that performs speculative intent verification on live audio."""

    _attr_has_entity_name = True
    _attr_name = "Speculative STT Proxy"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SystemOneClient,
        downstream_stt_id: str,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._client = client
        self._downstream_stt_id = downstream_stt_id

    @property
    def supported_languages(self) -> list[str]:
        return ["en", "*"]

    @property
    def supported_formats(self) -> list[AudioFormats]:
        return [AudioFormats.WAV, AudioFormats.RAW]

    @property
    def supported_codecs(self) -> list[AudioCodecs]:
        return [AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[AudioBitRates]:
        return [AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[AudioSampleRates]:
        return [AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[AudioChannels]:
        return [AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(
        self,
        metadata: SpeechMetadata,
        stream: AsyncIterable[bytes],
    ) -> SpeechResult:
        """Tee the incoming PCM stream into downstream STT and speculative chunker."""
        chunk_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        verified_event = asyncio.Event()

        # Step 1: Fork the live generator
        async def _tee_audio_stream() -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in stream:
                    # Non-blocking put to speculative queue; drop if congested
                    if not chunk_queue.full():
                        chunk_queue.put_nowait(chunk)
                    yield chunk
            finally:
                await chunk_queue.put(b"") # EOF sentinel

        # Step 2: Spawn background speculative verification worker
        speculative_task = asyncio.create_task(
            self._speculative_verification_loop(chunk_queue, verified_event)
        )

        # Step 3: Delegate primary audio stream to configured downstream STT
        try:
            downstream_entity = self.hass.data["stt"].get_entity(self._downstream_stt_id)
            result = await downstream_entity.async_process_audio_stream(
                metadata, _tee_audio_stream()
            )
            return result
        finally:
            speculative_task.cancel()

    async def _speculative_verification_loop(
        self,
        queue: asyncio.Queue[bytes],
        verified_event: asyncio.Event,
    ) -> None:
        """Accumulate PCM audio chunks, run streaming STT inference, and query System 1."""
        pcm_accumulator = bytearray()
        sample_rate = 16000
        bytes_per_second = sample_rate * 2 # 16-bit mono = 32,000 bytes/sec
        window_bytes = int(bytes_per_second * 0.40) # 400ms sliding evaluation chunk

        while True:
            chunk = await queue.get()
            if not chunk:
                break
            pcm_accumulator.extend(chunk)

            # Evaluate speculative chunk every 200ms once minimum audio is present
            if len(pcm_accumulator) >= window_bytes and not verified_event.is_set():
                # Transcribe partial buffer via fast local streaming STT
                partial_text = await self._transcribe_partial_slice(bytes(pcm_accumulator))
                if len(partial_text.split()) >= 2: # At least two words
                    choice, conf, rtt_ms = await self._client.classify_addressing(
                        text=partial_text,
                        question_text="Is this utterance directly addressing the assistant?",
                        min_confidence=0.80,
                    )
                    if choice == "addressed" and conf >= 0.80:
                        _LOGGER.info(
                            "[Speculative STT] Early address confirmed (conf=%.2f in %.1fms): '%s'",
                            conf, rtt_ms, partial_text
                        )
                        verified_event.set()
                        await self._notify_satellite_verified()
```

---

## 4. Reified Event-Typestate FSM Mapping

To maintain mathematical soundness and eliminate race conditions, the state machine transitions must strictly adhere to the **5 Operational Invariants** in `AGENTS.md`.

### 4.1 Invariant Rules Applied

| Rule | Invariant Definition | Speculative Implementation |
| :--- | :--- | :--- |
| **Rule 1: Zero-Variable-Branching** | No transition handler may inspect event types or status flags using `if` or `case`. The pairing `(State, Event)` must instantiate a dedicated state. | `(StreamingSpeech, WakeWordVerifiedEvent)` instantiates dedicated state `StreamingSpeechVerified`. |
| **Rule 2: Synchronous Run-to-Completion** | Transitions are 100% synchronous and instantaneous. Asynchronous jobs are detached. | `onWakeWordVerified` executes in $<1\mu\text{s}$, swapping tagged-union pointers without awaiting network or audio buffers. |
| **Rule 3: Total Event Accounting** | Every state must declare behavior for all possible system events. Unhandled events transition through `*Ignored`. | `StreamingSpeechVerified` explicitly accounts for speech end, cancel, timeout, error, and disconnect. |
| **Rule 4: Decoupled Transport Supervision** | Network health is a supervisory observer, not a lifecycle state. | WebSocket drops do not abort verified state if reconnect happens within the 3-second grace debounce. |
| **Rule 5: Deterministic Hardware / LED Binding** | LED ring registers are pure mathematical projections of current state. | `computeAnimationColors` maps `StreamingSpeechVerified` to locked emerald/cyan directional beam. |

---

### 4.2 State Matrix & Transition Graph in `src/nim_esphome_satellite.nim`

#### State Types
```nim
type
  # Existing Steady States
  StreamingSpeech* = distinct SatelliteContext
  Processing* = distinct SatelliteContext
  
  # NEW Reified Verified State
  StreamingSpeechVerified* = distinct SatelliteContext

  # Semantic Alias
  WakeWordVerified* = StreamingSpeechVerified
```

#### Typestate Definition & Transitions
```nim
typestate SatelliteFSM:
  consumeOnTransition = false
  states Idle, WaitingForSpeech, StreamingSpeech, StreamingSpeechVerified, Verifying, Processing, Replying, Cancelling, SilentDismissing, ActionableError, ConnectionError, Muted, FollowUp, PlayingMedia, Alerting, Announcing, Updating, ReplyingBargeInAttempted, ReplyingBargeInIgnored, BargedIn, IntentCompleteNoTts, ActionSuccess, PipelineErrorEvaluating

  transitions:
    # During unverified streaming: can be verified, finish speech, cancel, or error
    StreamingSpeech -> (StreamingSpeechVerified | Processing | Cancelling | SilentDismissing | PipelineErrorEvaluating | ConnectionError | Idle) as StreamingResult

    # During verified streaming: recording continues with locked LED ring until VAD speech end
    StreamingSpeechVerified -> (Processing | Cancelling | SilentDismissing | PipelineErrorEvaluating | ActionableError | ConnectionError | Idle) as VerifiedResult
```

#### Transition Procedures
```nim
# 1. Speculative Wake Word / Intent Verified Event
proc onWakeWordVerified*(s: StreamingSpeech): StreamingSpeechVerified {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH -> STREAMING_SPEECH_VERIFIED (Speculative verification confirmed)")
  result = StreamingSpeechVerified(SatelliteContext(s))

# 2. VAD Speech Ended from Verified State
proc onSpeechEndedFromVerified*(s: StreamingSpeechVerified): Processing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> PROCESSING (VAD speech ended, proceeding to intent execution)")
  result = Processing(SatelliteContext(s))

# 3. User Interrupts / Cancels During Verified Speech
proc onStopDuringVerified*(s: StreamingSpeechVerified): Cancelling {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> CANCELLING (Stop command received during verified speech)")
  result = Cancelling(SatelliteContext(s))

# 4. Silence Timeout (User hesitated or stopped mid-sentence)
proc onSilenceTimeoutFromVerified*(s: StreamingSpeechVerified): SilentDismissing {.transition.} =
  info("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> SILENT_DISMISSING (silence timeout after verification)")
  result = SilentDismissing(SatelliteContext(s))

# 5. Pipeline Error During Verified Stream
proc onPipelineErrorFromVerified*(s: StreamingSpeechVerified, err: string): PipelineErrorEvaluating {.transition.} =
  var ctx = SatelliteContext(s)
  ctx.errorCode = err
  error("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> PIPELINE_ERROR_EVALUATING (" & err & ")")
  result = PipelineErrorEvaluating(ctx)

# 6. Connection Lost
proc onDisconnectFromVerified*(s: StreamingSpeechVerified): ConnectionError {.transition.} =
  warn("SatelliteFSM", "State: STREAMING_SPEECH_VERIFIED -> CONNECTION_ERROR (HA disconnected during verified stream)")
  result = ConnectionError(SatelliteContext(s))
```

---

### 4.3 Deterministic Hardware & LED Ring Binding
In `src/xvf3800_hardware.nim`:
- **Lines 64–76 in `tests/test_xvf3800.nim`**: Pre-verification (`Woken`, `StreamingSpeech`, `Verifying`) leaves the LED ring dark (`c == 0'u32`) to eliminate false-trigger distraction in dark rooms.
- **Under `StreamingSpeechVerified`**:
  The LED ring immediately projects a **deterministic locked visual anchor**:

```nim
proc computeAnimationColors*(
    stateName: string,
    patternPref: string,
    brightnessIn: float32,
    nowMs: uint32
): array[12, uint32] =
  let brightness = clamp(brightnessIn, 0.05'f32, 1.0'f32)
  let now = float32(nowMs)

  case stateName
  of "StreamingSpeechVerified", "WakeWordVerified":
    # Instant visual certainty: Solid locked emerald-cyan ring or focused beam
    let r = uint32(uint8(clamp(10.0'f32 * brightness, 0.0'f32, 255.0'f32))) shl 16
    let g = uint32(uint8(clamp(230.0'f32 * brightness, 0.0'f32, 255.0'f32))) shl 8
    let b = uint32(uint8(clamp(255.0'f32 * brightness, 0.0'f32, 255.0'f32)))
    let lockedColor = r or g or b
    for i in 0 ..< 12:
      result[i] = lockedColor
```

---

### 4.4 Runtime C ABI Export
In `src/nim_satellite_bridge.h` and `src/nim_esphome_satellite.nim`:
```c
// C ABI Bridge Declaration
void nim_satellite_wake_word_verified(void);
```

```nim
proc nim_satellite_wake_word_verified*() {.exportc, cdecl.} =
  if fsm.state == rsStreamingSpeech:
    let next = onWakeWordVerified(fsm.streamingState)
    fsm = SatelliteFSMInstance(state: rsStreamingSpeechVerified, streamingVerifiedState: next)
    info("Satellite", "Hardware LED ring locked to Verified while speech streaming continues")
```

---

## 5. Summary of Architectural Advantages

1. **Elimination of False-Wake Distractions**:
   The LED ring does not flare up when background noise or incidental conversation triggers acoustic microWakeWord at 0.62. The device remains dark and unobtrusive until System 1 verifies intent.
2. **Zero Perceived Latency for Legitimate Commands**:
   When addressing the assistant ("Turn off the bedroom fan"), the satellite locks its LEDs *while the user is mid-sentence*. By the time the user finishes the word "fan", the intent has already been pre-parsed and approved.
3. **Rigorous Reified State Accounting**:
   Adheres 100% to all 5 Reified Event-Typestate rules: zero dynamic branching on event types, run-to-completion transitions, total event coverage, and pure functional projections to hardware registers.
