# esphome-satellite

[![CI](https://github.com/axiomantic/esphome-satellite/actions/workflows/ci.yml/badge.svg)](https://github.com/axiomantic/esphome-satellite/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`esphome-satellite`** is an on-device state supervisor for [ESPHome](https://esphome.io) and [Home Assistant](https://www.home-assistant.io/) voice satellites (including Seeed ReSpeaker XVF3800 and Home Assistant Voice PE), built with [`nim-esphome`](https://github.com/axiomantic/nim-esphome) and [`nim-typestates`](https://github.com/elijahr/nim-typestates).

Standard ESPHome voice setups rely on loose asynchronous network events and C++ callbacks that frequently fall out of sync—causing wake chimes to clip microphones, ambient TV noise to trigger false "stop" commands while idle, volume ducking to get orphaned, or satellites to freeze when the server drops connection.

`esphome-satellite` moves state coordination directly onto the ESP32 microcontroller, enforcing strict rules so your audio hardware and the Home Assistant server always stay in lockstep:

- **Self-Hearing Protection**: Discards microphone input until the wake chime has completely finished, eliminating false silence errors caused by the speaker clipping the mic.
- **Context-Aware Wake Words**: Stop words are strictly ignored when the device is idle, eliminating phantom cancellations from background TV or conversation.
- **Fail-Safe Media & State Recovery**: If Home Assistant drops connection or a pipeline errors mid-stream, media automatically un-ducks and the device safely resets to idle instead of freezing.
- **Compile-Time Verified**: Every valid state transition is proven at compile time—dead ends, impossible states, and race conditions are caught before firmware is ever flashed.
- **Drop-In Integration**: Integrates with standard ESPHome voice assistant pipelines and hardware.

---

### Quick Install

#### Option 1: In-Browser Web Installer (Recommended)

Connect your ESP32 device via USB and flash pre-compiled firmware directly from Chrome or Edge:

[![Install with ESP-Web-Tools](https://img.shields.io/badge/Web_Install-Connect_%26_Flash-2563eb?style=for-the-badge&logo=espressif&logoColor=white)](https://axiomantic.github.io/esphome-satellite/)

#### Option 2: ESPHome YAML Package

If you build firmware with ESPHome CLI or the ESPHome Dashboard, add the remote package to your device configuration:

```yaml
packages:
  satellite: github://axiomantic/esphome-satellite/packages/respeaker_xvf3800.yaml
```

---

### Post-Installation Setup

Follow these steps right after flashing to connect the satellite to your network and Home Assistant:

#### Step 1: Power-Cycle the Board (Required on ESP32-S3)

> [!IMPORTANT]
> **ESP32-S3 Native USB Bootloader Quirk:**
> Devices using the ESP32-S3 native USB-Serial-JTAG controller (such as the Seeed ReSpeaker Lite XVF3800) remain halted in the ROM Bootloader after flashing or erasing via WebSerial. Because native USB lacks hardware RTS/DTR auto-reset circuits, the browser cannot trigger a cold boot.
>
> **You must physically unplug and reconnect the USB-C cable** (or tap the **RST** button on the board) right after flashing!
> 
> *If you attempt to configure Wi-Fi before power-cycling, the installer will report `An error occurred. Improv Wi-Fi Serial not detected` because the firmware has not booted yet.*

#### Step 2: Connect to Wi-Fi

Once the board has rebooted into ESPHome, connect using either method:

- **Method A: USB Serial (Improv Wi-Fi)**:
  On the [Web Installer page](https://axiomantic.github.io/esphome-satellite/), click the **Configure Wi-Fi** button. The browser will discover the device via Improv Serial and prompt you to select your Wi-Fi network and enter your password.
- **Method B: Fallback Wi-Fi Hotspot**:
  On your phone or laptop, open your Wi-Fi settings and connect to the temporary open access point named **`Satellite Fallback Hotspot`**. The captive portal will open automatically at `http://192.168.4.1` where you can enter your Wi-Fi credentials.

#### Step 3: Adopt in Home Assistant

1. In Home Assistant, open **Settings > Devices & Services**.
2. Your satellite will automatically appear highlighted at the top under **Discovered** as **Voice Satellite** (e.g., `Voice Satellite ba2c6c` or `Voice Satellite 46cbe8`).
3. Click **Configure**, then click **Submit**.
4. Assign the device to an area.

> [!TIP]
> **No Encryption Key Required & Troubleshooting "Encryption Key" Prompt:**
>
> - **Zero Encryption Key**: `esphome-satellite` connects via standard ESPHome API without requiring an encryption key (`noise_psk: ""`).
> - **Why Home Assistant might ask for an "Encryption key"**:
>   Brand-new Seeed ReSpeaker boards ship with Seeed's proprietary encrypted ESPHome firmware pre-installed. If Home Assistant discovered the board before it was erased and flashed, Home Assistant created an in-memory discovery session marked with `noise_required: true`. In Home Assistant's schema, this makes the Encryption Key field mandatory—submitting a blank field is rejected with *"not all required fields are filled in"*.
> - **How to Solve in 10 Seconds (Direct Manual Add)**:
>   1. Cancel or close the prompt.
>   2. In Home Assistant, go to **Settings > Devices & Services > Add Integration > ESPHome**.
>   3. In **Host**, enter the device IP (or `esphome-satellite-<mac>.local`) and port `6053`.
>   4. Click **Submit**—Home Assistant connects immediately with zero prompts for an encryption key!
> - **Clear Stale Discovery Cache**: Alternatively, click **Ignore** on the discovered card and restart Home Assistant Core (**Developer Tools > YAML > Restart**) to flush the cached discovery session.
> - **Clean Factory Erase**: When flashing a brand-new board from Seeed for the first time, always select **"Erase device"** in the Web Installer so all factory NVS encryption tokens and partitions are completely wiped.

#### Step 4: Configure Multi-Assistant Pipelines & Audio Presets

1. In Home Assistant, navigate to **Settings > Voice Assistants**.
2. Create or verify your voice assistant pipelines (for example, a general smart home pipeline, a local Ollama LLM persona like *Mark Twain*, or a specialized assistant like *Jarvis*).
3. Navigate to **Settings > Devices & Services > ESPHome** and click on your satellite device:
   - **Assistant (Slot 1)**: Select your primary pipeline (e.g., *Mark Twain*).
   - **Wake word (Slot 1)**: Select which wake word triggers Slot 1 (e.g., *Mr. Clemens*).
   - **Assistant 2 (Slot 2)**: Select your secondary pipeline (e.g., *Jarvis* or *Home Assistant*).
   - **Wake word 2 (Slot 2)**: Select which wake word triggers Slot 2 (e.g., *Okay Nabu* or your uploaded custom model).
4. On the device card, customize your audio feedback across 17 pre-compiled acoustic themes:
   - **Wake Chime**: *Bell Ping*, *Modern Chime*, *Crystal Glass*, *Warm Kalimba*, *Meditation Bell*, *Marimba*, *Subtle Beep*, *Bamboo Chime*, *Tibetan Bowl*, *Acoustic Harp*, *Woodblock*, *Ceramic Bell*, *Neon Shimmer*, *Prism Ping*, *Cyber Bloom*, *Quantum Beep*, *Aero Chime*, or *Silent*.
   - **Processing Sound**: *Spinner*, *Pulse*, *Sonar*, *Tick*, *Typewriter*, *Clockwork* (seamless zero-gap loop), *Water Droplets*, *Raindrops*, *Forest Stream*, *Campfire Ember*, *Shishi-Odoshi*, *Soft Footsteps*, *Radar Ping*, *Data Crunch*, *Telemetry Blip*, *Quantum Flux*, *Retro Terminal*, or *Silent*.
   - **Cancel Sound**: *Match Wake Chime*, any of the 17 themed cancel resolves, or *Silent*.
   - **Wake Word Sensitivity**: *Slightly sensitive*, *Moderately sensitive*, or *Very sensitive*.

> **Manual / Source Builds**: See the full [**Integration Guide for ESPHome**](#integration-guide-for-esphome) below for custom YAML overrides, external component configuration, and C ABI bridge bindings.

---

## Table of Contents

- [Quick Install](#quick-install)
- [Post-Installation Setup](#post-installation-setup)
- [Multi-Wake-Word to Multi-Assistant Pipeline Mapping](#multi-wake-word-to-multi-assistant-pipeline-mapping)
  - [Dual-Assistant Profiles & Independent Feedback](#dual-assistant-profiles--independent-feedback)
  - [5-Minute Conversation Memory & Context Isolation](#5-minute-conversation-memory--context-isolation)
  - [Dynamic Partition Loader for Custom Models](#dynamic-partition-loader-for-custom-models)
- [Acoustic Tuning & Female Voice Equalization](#acoustic-tuning--female-voice-equalization)
  - [Microphone Pre-Gain Boost](#microphone-pre-gain-boost)
  - [Sliding Window Size Tuning](#sliding-window-size-tuning)
  - [Extreme Sensitivity Tier](#extreme-sensitivity-tier)
- [Real-Time Audio DSP & Speech Optimization](#real-time-audio-dsp--speech-optimization)
- [Discrete Partition Flashing & NVS State Preservation](#discrete-partition-flashing--nvs-state-preservation)
- [The Voice Satellite Race Condition Problem](#the-voice-satellite-race-condition-problem)
- [How Compile-Time Typestates Solve It](#how-compile-time-typestates-solve-it)
- [State Machine Architecture](#state-machine-architecture)
- [Granular Error Handling](#granular-error-handling)
- [Extended Lifecycle States](#extended-lifecycle-states)
- [Audio Feedback, Processing Loops & Cancel Sounds](#audio-feedback-processing-loops--cancel-sounds)
- [In-Browser Audio Transcoding & WebSerial Diagnostics](#in-browser-audio-transcoding--webserial-diagnostics)
- [Synthetic Wake Word Corpus Generator & Trainer](#synthetic-wake-word-corpus-generator--trainer)
  - [Synthesis Backends](#synthesis-backends)
  - [Curated Voice Demographic Balance](#curated-voice-demographic-balance)
  - [Exhaustive Phonetic Variations](#exhaustive-phonetic-variations)
  - [Interactive TUI Wizard & Headless CLI](#interactive-tui-wizard--headless-cli)
  - [Exporting to microWakeWord Training Pipeline](#exporting-to-microwakeword-training-pipeline)
  - [Roadmap: F5-TTS & Zero-Shot Household Voice Cloning](#roadmap-f5-tts--zero-shot-household-voice-cloning)
- [Home Assistant Surface Controls & Entities](#home-assistant-surface-controls--entities)
- [Integration Guide for ESPHome](#integration-guide-for-esphome)
  - [Step 1: Include External Components](#step-1-include-external-components)
  - [Step 2: Add the C Bridge Header](#step-2-add-the-c-bridge-header)
  - [Step 3: Connect Voice Assistant & Extended Event Hooks](#step-3-connect-voice-assistant--extended-event-hooks)
  - [Step 4: (Alternative) Using the Drop-in Package](#step-4-alternative-using-the-drop-in-package)
- [Supported Hardware](#supported-hardware)
- [Local Host Testing](#local-host-testing)
- [Project Layout](#project-layout)
- [Changelog](#changelog)
---

## Multi-Wake-Word to Multi-Assistant Pipeline Mapping

In modern Home Assistant voice environments, a single satellite device often needs to address multiple distinct personas, languages, or language models. For instance:
- *"Mr. Clemens"* can invoke a specialized, literary Mark Twain Ollama LLM persona.
- *"Okay Nabu"* can invoke the fast local Home Assistant pipeline for home automation commands.
- *"Hey Jarvis"* or a custom trained model can invoke an uncensored cloud conversational pipeline.

### How On-Device Concurrent Multi-Wake-Word Works
`esphome-satellite` harnesses the ESP32-S3 vector instructions and hardware neural network accelerator to evaluate up to **3 wake word models concurrently in real time**.

1. **Model Advertisement**: When the satellite connects to Home Assistant over the encrypted Native API, the firmware exposes all available on-device models (*Mr. Clemens*, *Okay Nabu*, plus any custom models loaded from dedicated flash partitions).
2. **Dual-Assistant Configuration**: In the Home Assistant device panel, Home Assistant maps these models into dual-assistant slots:
   - **Assistant (Slot 1)**: Maps your primary pipeline (e.g. *Mark Twain*) to its trigger wake word (e.g. *Mr. Clemens*).
   - **Assistant 2 (Slot 2)**: Maps your secondary pipeline (e.g. *Jarvis* or *Home Assistant*) to its trigger wake word (e.g. *Okay Nabu*).
3. **Zero-Latency Routing**: When speech is detected, the on-device microWakeWord engine identifies which specific wake word was matched and transmits the recognized phrase (`wake_word_phrase`) directly inside the `VoiceAssistantRequest` packet.
4. **Deterministic Server Dispatch**: Home Assistant inspects the incoming phrase and automatically dispatches the audio stream to the exact pipeline bound to that wake word slot. No complex automations, blueprint scripts, or server-side audio rerouting required.

### Dual-Assistant Profiles & Independent Feedback
Each assistant slot operates as a fully independent profile with its own acoustic identity:
- **Dedicated Volume Levels**: Set independent volume controls for Slot 1 (`Audio: Slot 1 Volume`) and Slot 2 (`Audio: Slot 2 Volume`), enabling quiet, unobtrusive volume for administrative commands while preserving full fidelity for literary or conversational assistants.
- **Independent Acoustic Themes**: Select distinct Wake Chimes, Processing Loops, and Cancel Sounds per slot. For instance, Slot 1 can play a warm acoustic kalimba chime with a vintage typewriter processing loop, while Slot 2 plays a crisp digital bell ping with a subtle spinner loop.
- **Per-Slot Wake Word Selectors**: Home Assistant device configuration panels restrict wake word selection to a single active wake word per device. `esphome-satellite` bypasses this limitation with native on-device template selectors (`Speech: Slot 1 Wake Word` and `Speech: Slot 2 Wake Word`), allowing you to assign any built-in or custom partition model to either slot independently.
- **Slot 2 Disable Option**: Setting Slot 2's wake word to `Disabled` safely reverts the satellite to dedicated single-assistant mode with zero overhead.

### 5-Minute Conversation Memory & Context Isolation
Voice interactions often span multi-turn dialogue where context should persist across pauses:
1. **Extended Conversation Memory (300 Seconds)**: `conversation_timeout` is set to `300s` (5 minutes), perfectly aligning with Home Assistant Core's `chat_session.py` garbage collection window. You can issue a command, pause for several minutes, trigger the wake word again, and ask contextual follow-up questions (such as *"repeat what you just did and undo it"*).
2. **Slot-Level Context Isolation**: To prevent personas from bleeding context into each other, the satellite tracks the active assistant slot. When a wake word activates a different slot than the preceding turn, the satellite immediately invokes `id(va).reset_conversation_id()`. This forces Home Assistant to spin up a clean conversation context for the new assistant.
3. **Spoken Conversation Reset**: Saying *"forget our conversation"*, *"clear history"*, *"reset conversation"*, *"new conversation"*, or *"forget everything"* is intercepted directly in `on_stt_end`. The satellite wipes the Home Assistant conversation ID, dismisses the turn, and plays the cancel sound as an audible confirmation cue without sending unnecessary LLM prompts.
4. **Manual Reset Button**: The dashboard exposes `Speech: Reset Conversation History` for one-tap memory clearing.

### Dynamic Partition Loader for Custom Models
Using [`src/wake_partition_loader.nim`](src/wake_partition_loader.nim), users can flash up to 3 custom microWakeWord `.tflite` models into dedicated flash partitions (`wake_model`, `wake_model_2`, `wake_model_3` at `0x510000`, `0x550000`, `0x590000`). At boot time, the partition loader validates 64-byte `WAKE` headers, extracts tensor arena sizes and probability cutoffs, memory-maps the weights directly from SPI flash (avoiding heap allocation), and dynamically registers them into the active detection pool.

---

## Acoustic Tuning & Female Voice Equalization

Far-field microWakeWord neural networks frequently exhibit acoustic bias toward male voices. Female speech generally exhibits:
- Higher fundamental frequencies ($F_0 \approx 200-260 \text{ Hz}$ vs. $100-140 \text{ Hz}$ for adult males).
- Shorter vowel durations and faster formant transitions across consonants.
- Lower acoustic energy in the lower register where small voice satellite microphones have the highest SNR.

`esphome-satellite` provides three runtime acoustic equalization controls to eliminate gender bias and maximize detection reliability across all household members:

### Microphone Pre-Gain Boost
- **Entity**: `Speech: Mic Pre-Gain Boost` (`number.speech_mic_pre_gain_boost`)
- **Range**: `0 dB` to `+12 dB` (step `1 dB`, default `3 dB`)
- **Implementation**: Written in Nim ([`src/audio_dsp.nim`](src/audio_dsp.nim)), applying 64-bit precision linear gain scaling directly to 32-bit microphone samples in the I2S capture loop before microWakeWord 40-band Mel-frequency spectrogram extraction.
- **Tuning**: A `+3 dB` to `+6 dB` boost brings female vocal energy up to parity with male speech without clipping the XVF3800 beamformed microphone stream.

### Sliding Window Size Tuning
- **Entity**: `Speech: Wake Window Size` (`number.speech_wake_window_size`)
- **Range**: `2` to `5` frames (default `3` frames, where 1 frame = ~100 ms)
- **Implementation**: Dynamically resizes the sliding probability window in the microWakeWord `StreamingModel` neural network runtime.
- **Tuning**: Standard wake word engines require 4 to 5 consecutive frames above threshold to trigger. Because female speech often articulates syllables more briskly, a 5-frame window can reject valid wake words during fast cadence. Lowering the window to `2` or `3` frames captures shorter syllable bursts cleanly.

### Extreme Sensitivity Tier
- **Entities**: `Speech: Slot 1 Sensitivity` and `Speech: Slot 2 Sensitivity`
- **Options**: `Slightly sensitive` (1.35x cutoff), `Moderately sensitive` (1.0x cutoff), `Very sensitive` (0.70x cutoff), `Extreme sensitivity` (0.45x cutoff).
- **Implementation**: Scales the neural network's activation threshold cutoff dynamically in SPI flash memory structures. Selecting `Extreme sensitivity` drops the required activation barrier by 55%, enabling effortless far-field triggers across quiet voices, soft accents, or high ambient noise environments.

---

## Real-Time Audio DSP & Speech Optimization

Small voice satellites typically operate on compact 1W to 2W onboard speakers driven by miniature Class-D amplifiers. These drivers have narrow dynamic ranges and clip aggressively when driven with uncompressed text-to-speech audio.

`esphome-satellite` implements a real-time, zero-allocation audio DSP pipeline written in Nim ([`src/audio_dsp.nim`](src/audio_dsp.nim)) that runs on the ESP32 CPU directly on audio buffers before I2S DMA transmission:

### 1. Dynamic Range Compression
- **Threshold**: `-14.0 dBFS`
- **Compression Ratio**: `3:1`
- **Envelope Follower**: Smooth ballistic tracking with a `5ms` attack time and a `100ms` release time.

Signals above `-14 dBFS` undergo smooth gain reduction, preventing loud passages and transient voice bursts from overpowering the amplifier or driving the speaker cone into physical distortion.

### 2. Dialogue Makeup Boost
- **Makeup Gain**: `+5.0 dB`

Speech synthesis often includes subtle whispers, breath sounds, and soft cadence drops. A static `+5.0 dB` makeup boost raises quiet vocal passages, ensuring clarity and intelligibility across the room even at lower overall volume levels.

### 3. Soft-Knee Rational Limiting
A rational transfer limiter clamps any remaining peak overshoots above `-1.0 dBFS` using a smooth non-linear knee:
```text
limiter(x) = x / (1.0 + |x|)
```
This guarantees that digital audio values never wrap or hard-clip, providing warm, distortion-free playback even when driving the speaker at maximum volume.

---

## Discrete Partition Flashing & NVS State Preservation

Standard ESPHome web installations flash a single merged `firmware.factory.bin` starting at flash address `0x0` and extending across `~1.88 MB`. Because this contiguous binary covers the Non-Volatile Storage (NVS) address space (`0x9000` to `0xE000`) with blank `0xFF` padding bytes, flashing a firmware update traditionally wiped all saved device state—forcing users to re-enter Wi-Fi credentials, re-select wake words, and reconfigure volume levels after every release.

`esphome-satellite` implements **discrete partition flashing**:

| Binary Component | Flash Offset | Size | Purpose |
|---|---|---|---|
| **`bootloader.bin`** | `0x00000` (`0`) | ~21 KB | ESP-IDF 2nd-stage bootloader |
| **`partitions.bin`** | `0x08000` (`32768`) | 3 KB | Partition table layout |
| *NVS Storage* | *`0x09000` - `0x0E000`* | *20 KB* | **Untouched / Preserved** (Wi-Fi, volumes, preferences) |
| **`ota_data_initial.bin`** | `0x0E000` (`57344`) | 8 KB | OTA boot selection metadata |
| **`firmware-ota.bin`** | `0x10000` (`65536`) | ~1.82 MB | Core firmware application (`app0` slot) |

When updating an existing satellite via the [Web Installer](https://axiomantic.github.io/esphome-satellite/), leaving **"Erase device"** unchecked preserves all stored Wi-Fi credentials, volume preferences, wake word assignments, and sound theme selections across flashes.

---

## The Voice Satellite Race Condition Problem

In conventional ESPHome voice satellites, state is distributed across asynchronous Home Assistant server events, network callbacks, and C++ lambdas. Under real-world acoustic and network conditions, this causes severe UX bugs:

1. **Stop Word Clobbering**: Ambient noise or TV audio false-triggers the `Stop` wake word when the satellite is already idle, causing confusing audio stops and state corruption.
2. **Premature Chime & VAD Clipping**: If the microphone opens while the wake chime is still playing, the VAD algorithm hears the satellite's own speaker and immediately triggers `stt-no-text-recognized`.
3. **Double Wake / Rapid Re-triggering**: A wake word detected while already processing speech can corrupt audio buffers or cause duplicate requests.
4. **Offline Phantom Triggers**: On-device micro wake word models continuing to trigger while the WiFi or Home Assistant API connection is dropped.
5. **Ducking Clobbering**: Music streaming volume is not properly ducked or fails to un-duck when conversations finish or fail.

---

## How Compile-Time Typestates Solve It

With [`nim-typestates`](https://github.com/elijahr/nim-typestates), the state of the satellite is encoded directly in the Nim type system:

- **Strict Transitions**: You cannot call `onSpeechEnded()` on an `Idle` or a `Thinking` state. The compiler rejects it with a type mismatch error.
- **Barge-in Safety**: The `Stop` wake word is only valid during `Listening`, `Thinking`, `Replying`, or active `Alerting`. In `Idle`, `onStopWord()` does not exist on the type.
- **Strict Serialization**: Transitioning to `Listening` requires a completed chime event (`onChimeFinished()`). The microphone cannot capture audio during playback.
- **Offline Suppression**: When the satellite enters `ConnectionError`, wake word transitions are eliminated from the state type.
- **Privacy Enforcement**: When `Muted`, wake word detection and microphone capture cannot compile or execute.

---

## State Machine Architecture

```mermaid
stateDiagram-v2
    [*] --> Idle

    Idle --> Woken: onWakeWord(word, angle)
    Idle --> ConnectionError: onDisconnect()
    Idle --> Muted: onMute()
    Idle --> PlayingMedia: onMediaPlay()
    Idle --> Alerting: onAlertStart()
    Idle --> Announcing: onAnnouncementStart()
    Idle --> Updating: onOtaStart()

    state Woken {
        [*] --> PlayingChime
    }
    Woken --> Listening: onChimeFinished()
    Woken --> SilentDismiss: onChimeFailed()
    Woken --> ConnectionError: onDisconnect()

    state Listening {
        [*] --> StreamingMic
    }
    Listening --> Thinking: onSpeechEnded() [VAD speech done]
    Listening --> SilentDismiss: onSilenceTimeout() [stt-no-text-rec]
    Listening --> PipelineError: onPipelineError(code)
    Listening --> ConnectionError: onDisconnect()
    Listening --> Idle: onStopWord()

    state Thinking {
        [*] --> ProcessingIntent
    }
    Thinking --> Replying: onTtsStarted()
    Thinking --> PipelineError: onPipelineError(code)
    Thinking --> ConnectionError: onDisconnect()
    Thinking --> Idle: onStopWord()

    state Replying {
        [*] --> PlayingTTS
    }
    Replying --> Idle: onTtsFinished()
    Replying --> FollowUp: onFollowUpRequested()
    Replying --> Idle: onStopWord() [Barge-in]
    Replying --> PipelineError: onPipelineError(code)
    Replying --> ConnectionError: onDisconnect()

    state FollowUp {
        [*] --> ContinuousDialogue
    }
    FollowUp --> Listening: onFollowUpReadyToListen()
    FollowUp --> Idle: onFollowUpTimeout()
    FollowUp --> ConnectionError: onDisconnect()

    state PlayingMedia {
        [*] --> StreamingAudio
    }
    PlayingMedia --> Woken: onWakeWord() [Ducks volume]
    PlayingMedia --> Idle: onMediaStop()
    PlayingMedia --> Alerting: onAlertFromMedia()
    PlayingMedia --> Announcing: onAnnouncementFromMedia()
    PlayingMedia --> Updating: onOtaFromMedia()
    PlayingMedia --> ConnectionError: onDisconnect()

    state Alerting {
        [*] --> RingingTimerAlarm
    }
    Alerting --> Idle: onAlertDismiss() [Tap / Stop word]
    Alerting --> Woken: onWakeWordDuringAlert()
    Alerting --> ConnectionError: onDisconnect()

    state Muted {
        [*] --> PrivacyHardwareMute
    }
    Muted --> Idle: onUnmute()
    Muted --> ConnectionError: onDisconnect()
    Muted --> Updating: onOtaFromMuted()

    state Announcing {
        [*] --> ServerBroadcast
    }
    Announcing --> Idle: onAnnouncementEnd()
    Announcing --> ConnectionError: onDisconnect()

    state Updating {
        [*] --> FirmwareFlash
    }
    Updating --> Idle: onOtaComplete()

    state SilentDismiss {
        [*] --> SilentReset
    }
    SilentDismiss --> Idle: onDismiss()
    SilentDismiss --> PlayingMedia: onDismissToMedia()

    state PipelineError {
        [*] --> ErrorToneAndLED
    }
    PipelineError --> Idle: onResetPipelineError()
    PipelineError --> PlayingMedia: onResetPipelineErrorToMedia()

    state ConnectionError {
        [*] --> OfflineSuppression
    }
    ConnectionError --> Idle: onConnected() [HA reconnected]
    ConnectionError --> Muted: onConnectedMuted()
```

---

## Granular Error Handling

Conventional voice implementations dump all failures into a generic error handler that plays loud error tones. `nim-esphome-satellite` partitions errors into three distinct typestates:

| Typestate | Typical Triggers | Satellite Behavior |
|---|---|---|
| **`SilentDismiss`** | Silence timeout (`stt-no-text-recognized`), duplicate wake word. | **Completely silent instant reset**. No error buzzer, no blinking red LEDs. Unlocks the audio beam, restores media if ducked, and returns cleanly to `Idle`. |
| **`PipelineError`** | Intent parsing error, TTS streaming network error, STT failure. | Plays the standard error sound, pulses red LEDs, unlocks the microphone beam, restores media if ducked, and resets safely to `Idle`. |
| **`ConnectionError`**| Home Assistant API disconnect, WiFi dropped. | Indicates offline status via LEDs. **Wake word triggers are rejected/suppressed** until reconnect. |

---

## Extended Lifecycle States

| State | Hook / Trigger | Behavior & Compile-Time Guarantees |
|---|---|---|
| **`Muted`** | `call_nim_set_muted(true)` | Privacy lock. Wake word detection and mic capture are statically disallowed on the type. |
| **`FollowUp`** | `call_nim_follow_up()` | Continuous conversation without requiring wake words between dialogue turns. |
| **`PlayingMedia`** | `call_nim_media_play()` | Background music / radio streaming. Audio ducks on wake word and auto-restores when dialogue ends. |
| **`Alerting`** | `call_nim_alert_start()` | Active timer / alarm buzzer. Interrupted via touch tap, stop word, or new command. |
| **`Announcing`** | `call_nim_announcement_start()` | Unprompted server broadcasts (intercom, doorbell, security announcements). |
| **`Updating`** | `call_nim_ota_start()` | Firmware flash in progress. All audio tasks and DSP inference are halted to prevent brownouts. |

---

## Integration Guide for ESPHome

### Step 1: Include External Components

In your ESPHome device configuration YAML:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/axiomantic/nim-esphome
    components: [nim]

nim:
  source: /path/to/esphome-satellite/src/nim_esphome_satellite.nim
  requires:
    - https://github.com/elijahr/nim-typestates
```

### Step 2: Add the C Bridge Header

Include `nim_satellite_bridge.h` in your ESPHome `includes:` section:

```yaml
esphome:
  name: my-voice-satellite
  includes:
    - nim_satellite_bridge.h
```

> **Note**: All bridge functions use `__attribute__((weak))` and safe `call_nim_*` wrappers. If the Nim component is ever omitted or disabled, your firmware still compiles cleanly without linker errors.

### Step 3: Connect Voice Assistant & Extended Event Hooks

```yaml
# Wake Word Detection
micro_wake_word:
  on_wake_word_detected:
    - lambda: |-
        call_nim_wake_word(wake_word.c_str(), 0);

# Voice Assistant Pipeline
voice_assistant:
  on_start:
    - lambda: |-
        call_nim_chime_done(true);
  on_stt_vad_end:
    - lambda: |-
        call_nim_speech_ended();
  on_tts_start:
    - lambda: |-
        call_nim_tts_start();
  on_tts_end:
    - lambda: |-
        call_nim_tts_end();
  on_error:
    - lambda: |-
        call_nim_error(code.c_str());
  on_client_connected:
    - lambda: |-
        call_nim_connected();
  on_client_disconnected:
    - lambda: |-
        call_nim_disconnected();

# Hardware / Software Privacy Mute
switch:
  - platform: template
    id: mic_mute_switch
    name: "Mic Mute"
    on_turn_on:
      - lambda: |-
          call_nim_set_muted(true);
    on_turn_off:
      - lambda: |-
          call_nim_set_muted(false);

# Active Alarm / Timer Ringing
switch:
  - platform: template
    id: timer_ringing
    name: "Timer Ringing"
    on_turn_on:
      - lambda: |-
          call_nim_alert_start();
    on_turn_off:
      - lambda: |-
          call_nim_alert_stop();

# OTA Firmware Updates
ota:
  - platform: esphome
    on_begin:
      - lambda: |-
          call_nim_ota_start();
```

### Step 4: Drop-in Hardware Profiles

`esphome-satellite` provides ready-to-flash package profiles for supported hardware:

| Profile Package | Target Hardware | Default Audio Feedback | Use Case |
|---|---|---|---|
| [`packages/respeaker_xvf3800_twain.yaml`](packages/respeaker_xvf3800_twain.yaml) | Seeed ReSpeaker XVF3800 | **Spinner** (Active loop enabled) | Continuous audio spinner feedback during cloud STT/LLM inference. |
| [`packages/respeaker_xvf3800_silent.yaml`](packages/respeaker_xvf3800_silent.yaml) | Seeed ReSpeaker XVF3800 | **Silent** (No-op) | Discreet satellite operation with no intermediate processing audio. |
| [`packages/respeaker_xvf3800.yaml`](packages/respeaker_xvf3800.yaml) | Seeed ReSpeaker XVF3800 | Base Template | Base configuration component for custom inheritance. |

Import the package directly into your ESPHome configuration:

```yaml
packages:
  satellite:
    url: https://github.com/axiomantic/esphome-satellite
    ref: main
    files: [packages/respeaker_xvf3800_twain.yaml]
    refresh: 1d
```

---

## Audio Feedback, Processing Loops & Cancel Sounds

When a user finishes speaking, voice assistants often experience variable cloud latencies (1-5 seconds) while Speech-to-Text (STT) and Large Language Models (LLM) synthesize a response. Without feedback, users wonder if their command was received.

`esphome-satellite` implements a non-blocking, zero-allocation audio processing engine:

- **17 Pre-compiled Acoustic Themes**: Includes 17 matching sets of Wake Chimes, Processing Loops, and Cancel Sounds encoded as compact high-fidelity IMA-ADPCM in flash.
- **Seamless Zero-Gap Processing Loops**: The clockwork, spinner, pulse, and stream loops are mathematically tuned for continuous, seamless looping without rhythm stutter.
- **Dedicated Cancel Sounds**: Playing when a cancellation word (*"stop"*, *"cancel"*, *"nevermind"*) is spoken or voice interaction times out.
- **Custom Wake Word Flash-at-Install**: Upload any microWakeWord `.tflite` model directly in the browser installer. Pre-compiled firmware detects the partition header at boot, loads the model, and exposes it in Home Assistant.

---

## In-Browser Audio Transcoding & WebSerial Diagnostics

The [`esphome-satellite` Web Installer](https://axiomantic.github.io/esphome-satellite/) includes built-in browser-based audio tooling and serial diagnostics powered by the Web Audio API and WebSerial:

- **Client-Side Audio Transcoder**: Users can drag and drop custom audio files (`.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a`) directly in Chrome or Edge. The browser's native `OfflineAudioContext` decodes the audio, resamples it to 16,000 Hz mono 16-bit PCM, peak-normalizes it to `-1.0 dBFS`, and flashes it directly into dedicated flash partitions (`chime_data`, `sound_data`, or `cancel_data`).
- **Interactive Sound Showcase**: Listen to high-fidelity MP3 previews of all 17 pre-compiled acoustic themes directly in the browser before flashing.
- **WebSerial Terminal & Hardware Reset**: Connect to the device at 115,200 baud directly from the browser window. View live boot logs and send DTR/RTS hardware reset pulses to cycle the ESP32-S3 without physical unplugging.

---

## Synthetic Wake Word Corpus Generator & Trainer

The repository includes a self-contained, high-performance synthetic speech dataset generator and microWakeWord preparation script: [`scripts/generate_wakeword_corpus.py`](scripts/generate_wakeword_corpus.py).

High recall in edge neural wake word models requires acoustic variety across speech speed, pitch, accents, and phonetic permutations. `generate_wakeword_corpus.py` automates positive dataset creation with zero manual recording required.

### Synthesis Backends
1. **ElevenLabs API (`--backend elevenlabs`)**: Cloud neural synthesis using high-fidelity production voices. Employs curated voice registries spanning female, male, adolescent, and accented speakers.
2. **macOS `say` (`--backend macos_say`)**: Built-in zero-dependency local macOS speech synthesizer. Uses system voices (`Samantha`, `Victoria`, `Alex`, `Daniel`, `Oliver`, `Junior`, etc.) without requiring external network access or API tokens.

### Curated Voice Demographic Balance
To prevent acoustic overfitting and address gender/age detection disparities, the corpus generator draws from a balanced demographic distribution:
- **Female (40%)**: Voices with higher pitch and faster formant transitions (`Rachel`, `Sarah`, `Freya`, `Nicole`, `Charlotte`, `Samantha`, `Victoria`).
- **Male (40%)**: Deep and mid-range baritone voices (`Adam`, `Antoni`, `Josh`, `Arnold`, `George`, `Alex`, `Daniel`).
- **Adolescent / Youth (10%)**: Higher vocal tracts and faster cadence (`Mimi`, `Liam`, `Fin`, `Junior`).
- **Accents (10%)**: British, Irish, Australian, Transatlantic, and Swedish-English intonations (`Dorothy`, `Alice`, `Charlie`, `Matilda`, `Moira`).

### Exhaustive Phonetic Variations
The generator produces combinatorial phonetic permutations for common wake phrases to cover varied regional pronunciations and elisions:
- **Okay Nabu**:
  - Prefixes: `okay`, `ok`, `hey`, `ay`, `kay`, and bare phrase.
  - Surnames: `nabu`, `nahboo`, `na boo`, `nayboo`, `nah bu`, `naboo`.
- **Mr. Clemens**:
  - Honorifics: `mister`, `mr`, `mr.`, `mista`, `mist ur`, `miss ter`, `misster`, `miss tack`, `mist ack`.
  - Surnames: `clemens`, `clemen`, `clemence`, `claman`, `clem ins`, `lemons`, `klemens`, `clay mens`, `claymen`.

### Content-Addressed Caching
Generated audio clips are cached in `.cache/mww_corpus/<sha256>.wav` based on the hash of phrase, voice, engine, and acoustic parameters. Subsequent runs with identical parameters complete instantly without incurring duplicate API costs or re-synthesis delay.

### Interactive TUI Wizard & Headless CLI

Run the interactive terminal wizard:
```bash
python3 scripts/generate_wakeword_corpus.py --wizard
```
The wizard prompts for:
1. Model target (*Okay Nabu*, *Mr. Clemens*, or Custom phrase)
2. Synthesis backend (*ElevenLabs API* or *macOS say*)
3. Sample count (e.g. 50, 500, or 2,000)
4. Output directory

Run in headless CLI mode for scripted automation:
```bash
# Generate 100 samples of Mr. Clemens using macOS say
python3 scripts/generate_wakeword_corpus.py \
  --model mister_clemens \
  --backend macos_say \
  --count 100 \
  --output data/mister_clemens/positive

# Generate 500 samples using ElevenLabs API
export ELEVENLABS_API_KEY="your-api-key"
python3 scripts/generate_wakeword_corpus.py \
  --model okay_nabu \
  --backend elevenlabs \
  --count 500 \
  --output data/okay_nabu/positive

# Generate custom phrase
python3 scripts/generate_wakeword_corpus.py \
  --model custom \
  --phrase "computer activate" \
  --backend macos_say \
  --count 50 \
  --output data/custom/positive
```

### Exporting to microWakeWord Training Pipeline
Every synthesized audio file is automatically normalized, trimmed of leading/trailing silence, and transcoded to **16,000 Hz 16-bit mono PCM** matching microWakeWord input requirements:
1. Feed generated `.wav` files into the microWakeWord feature generator:
   ```bash
   python3 -m microwakeword.feature_generator \
     --dataset_dir data/mister_clemens \
     --output_dir trained_models/mister_clemens/features
   ```
2. Train the streaming neural network model:
   ```bash
   python3 -m microwakeword.train \
     --feature_dir trained_models/mister_clemens/features \
     --output_dir trained_models/mister_clemens/model
   ```
3. Convert to INT8 quantized `.tflite` model and flash directly to partition `0x510000` (`wake_model`) via the [Web Installer](https://axiomantic.github.io/esphome-satellite/).

### Roadmap: F5-TTS & Zero-Shot Household Voice Cloning
To maximize detection accuracy for specific family members while maintaining model robustness, the script design accommodates zero-shot voice cloning:

1. **F5-TTS Flow Matching Integration**:
   - F5-TTS employs non-autoregressive flow matching to generate high-fidelity speech conditioned on a short (3-10 second) reference audio clip.
   - Provides richer dynamic expressiveness, vocal cadence variation, and prosody shifts than traditional text-to-speech.
2. **Household Member Voice Cloning**:
   - Users record or supply a reference audio clip of household members (e.g. self, partner, children) along with a reference transcript.
   - The generator clones each member's acoustic timbre and fundamental frequency profile using either local F5-TTS or ElevenLabs Instant Voice Cloning (IVC).
3. **Additive Multi-Voice Composition**:
   - Household cloned voices operate as an additive layer on top of the default generic voice mix (40% female, 40% male, 10% kids, 10% accents).
   - This hybrid strategy ensures the neural network attains maximum sensitivity to the specific household's resonant frequencies while preserving generalization and preventing false triggers from background ambient speech.

---

## Home Assistant Surface Controls & Entities

`esphome-satellite` exposes native Home Assistant entities generated via `nim-esphome`'s declarative controls DSL, enabling full runtime configuration and automation from your dashboards:

| Entity ID | Domain | Type / Options | Description |
|---|---|---|---|
| `select.speech_slot_1_wake_word` | `select` | `Mr. Clemens`, `Okay Nabu`, Custom | Wake word model assigned to Assistant 1 (Slot 1). |
| `select.speech_slot_2_wake_word` | `select` | `Disabled`, `Mr. Clemens`, `Okay Nabu`, Custom | Wake word model assigned to Assistant 2 (Slot 2). |
| `select.speech_slot_1_sensitivity` | `select` | *Slightly*, *Moderately*, *Very*, *Extreme sensitivity* | Probability cutoff sensitivity for Slot 1 detection. |
| `select.speech_slot_2_sensitivity` | `select` | *Slightly*, *Moderately*, *Very*, *Extreme sensitivity* | Probability cutoff sensitivity for Slot 2 detection. |
| `number.speech_wake_window_size` | `number` | `2` – `5` frames (default `3`) | Detection window length; lower values catch fast female syllables. |
| `number.speech_mic_pre_gain_boost` | `number` | `0 dB` – `+12 dB` (step `1 dB`, default `3 dB`) | Digital pre-gain applied to raw microphone samples before DSP inference. |
| `text.speech_cancellation_words` | `text` | Comma-separated strings | Phrases that immediately abort active listening (*stop, nevermind, cancel*). |
| `button.speech_reset_conversation_history` | `button` | Action | Clears conversational memory context on Home Assistant. |
| `select.audio_slot_1_wake_chime` | `select` | 17 Acoustic Themes, `Silent`, `Custom` | Acknowledgement chime played for Slot 1 wake word. |
| `switch.audio_slot_1_wake_chime_enabled` | `switch` | `on` / `off` | Master toggle for Slot 1 wake chime playback. |
| `number.audio_slot_1_volume` | `number` | `0%` – `100%` (step `5%`) | Master playback and chime volume level for Slot 1. |
| `select.audio_slot_1_processing_sound` | `select` | 17 Acoustic Themes, `Silent`, `Custom` | Continuous audio loop played during Slot 1 cloud processing. |
| `select.audio_slot_1_cancel_sound` | `select` | `Match Wake Chime`, 17 Themes, `Silent` | Resolve cue played when Slot 1 interaction is cancelled. |
| `switch.audio_slot_1_cancel_sound_enabled` | `switch` | `on` / `off` | Master toggle for Slot 1 cancel sound playback. |
| `select.audio_slot_2_wake_chime` | `select` | 17 Acoustic Themes, `Silent`, `Custom` | Acknowledgement chime played for Slot 2 wake word. |
| `switch.audio_slot_2_wake_chime_enabled` | `switch` | `on` / `off` | Master toggle for Slot 2 wake chime playback. |
| `number.audio_slot_2_volume` | `number` | `0%` – `100%` (step `5%`) | Master playback and chime volume level for Slot 2. |
| `select.audio_slot_2_processing_sound` | `select` | 17 Acoustic Themes, `Silent`, `Custom` | Continuous audio loop played during Slot 2 cloud processing. |
| `select.audio_slot_2_cancel_sound` | `select` | `Match Wake Chime`, 17 Themes, `Silent` | Resolve cue played when Slot 2 interaction is cancelled. |
| `switch.audio_slot_2_cancel_sound_enabled` | `switch` | `on` / `off` | Master toggle for Slot 2 cancel sound playback. |
| `select.hardware_led_idle_pattern` | `select` | `Off`, `Breathe`, `Rainbow`, `Spinner` | Ambient idle animation mode for the 12-LED addressable ring. |
| `number.hardware_led_brightness` | `number` | `5%` – `100%` (step `5%`) | Brightness scaling for all LED animations. |
| `switch.privacy_mute` | `switch` | `on` / `off` | Hardware/firmware microphone privacy mute toggle. |
| `sensor.status_satellite_state` | `sensor` | 14 Typestates | Real-time state machine telemetry (*Idle*, *Woken*, *Listening*, *Thinking*, *Replying*). |
| `button.hardware_reset_audio_hardware` | `button` | Action | Hardware codec re-initialization and XMOS SoC reboot pulse. |

All control settings are saved to on-device NVS flash memory and persist across power cycles and firmware updates.

---

## Supported Hardware

- **Seeed Studio ReSpeaker XVF3800** (ESP32-S3 + XMOS XVF3800 DSP)
- **Home Assistant Voice PE** (ESP32-S3)
- **ESP32-S3-BOX / BOX-3**
- Any ESP32 / ESP32-S3 device running ESPHome Voice Assistant with `micro_wake_word`.

---

## Local Host Testing

You do not need an ESP32 connected to run the test suite. All state machine logic and compile-time invariants run locally on macOS or Linux:

```bash
# Run unit tests
./scripts/test.sh

# Or via Nim directly
nim c -r tests/test_fsm.nim
```

The test suite validates:
- **Core Happy Path**: `Idle -> Woken -> Listening -> Thinking -> Replying -> Idle`
- **Barge-in Interruptions**: `Stop` command during `Listening`, `Thinking`, `Replying`, and `Alerting`
- **Granular Errors**: `SilentDismiss`, `PipelineError`, `ConnectionError`
- **Extended Lifecycle**: `Muted`, `FollowUp`, `PlayingMedia`, `Alerting`, `Announcing`, `Updating`
- **Compile-Time Invariant Enforcement**: Verified using `not compiles(...)` (e.g. verifying that calling `onWakeWord` while `Muted` or `Updating` is rejected by the compiler).

---

## Project Layout

```
esphome-satellite/
├── src/
│   ├── nim_esphome_satellite.nim # 14-state verified FSM & exported C ABI
│   ├── satellite_fsm.nim         # Re-export entrypoint
│   └── nim_satellite_bridge.h    # C/C++ weak symbol bridge header
├── packages/
│   ├── respeaker_xvf3800.yaml    # Seeed ReSpeaker XVF3800 hardware configuration
│   └── satellite_nim_fsm.yaml    # ESPHome reusable package for drop-in integration
├── tests/
│   ├── test_audio_dsp.nim        # Speech compression, makeup gain & limiter tests
│   ├── test_cancellation.nim     # Mid-utterance cancellation matcher tests
│   ├── test_fsm.nim              # 14-state verified FSM typestate tests
│   ├── test_pcm_player.nim       # IMA-ADPCM zero-heap decoder tests
│   ├── test_version_sync.nim     # Version consistency invariant test suite
│   ├── test_wake_loader.nim      # Dynamic microWakeWord partition loader tests
│   └── test_xvf3800.nim          # XVF3800 GPO & LED ring animation tests
├── scripts/
│   ├── build_factory_binary.sh   # Automated factory flashing binary builder
│   ├── bump_version.sh           # Synchronized semver bumper
│   ├── generate_wakeword_corpus.py # Synthetic speech corpus generator & trainer
│   ├── generate_web.nim          # Web installer HTML generator
│   ├── process_audio.py          # Audio normalization & ADPCM sound bank pipeline
│   ├── test.sh                   # Invariant test execution runner
│   └── transcode_sounds.nim      # Nim sound bank transcoder
└── esphome_satellite.nimble      # Package specification & dependencies
```

## Changelog

All notable changes are documented in [CHANGELOG.md](CHANGELOG.md) in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

## Audio Licensing & Attribution

All 51 acoustic assets (17 Wake Chimes, 17 Processing Loops, and 17 Cancel Sounds) are royalty-free under permissive licenses (**Creative Commons CC0 1.0 Universal Public Domain Dedication** and **Creative Commons Attribution CC-BY 3.0**). Complete per-sound author credits, origins, and license terms are documented in [ATTRIBUTION.md](ATTRIBUTION.md).

---

## License

MIT © [Axiomantic](https://github.com/axiomantic) / [Elijah Rust](https://github.com/elijahr)
