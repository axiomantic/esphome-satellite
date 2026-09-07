import std/[os, strutils]
import nim_esphome/dsl/installer

proc getPackageVersion(): string =
  let nimbleContent = readFile("esphome_satellite.nimble")
  for line in nimbleContent.splitLines():
    let trimmed = line.strip()
    if trimmed.startsWith("version"):
      let parts = trimmed.split('=')
      if parts.len == 2:
        return parts[1].strip().strip(chars = {'"', ' '})
  raise newException(ValueError, "Could not find version in esphome_satellite.nimble")

let currentVersion = getPackageVersion()

let satelliteInstaller = esphomeInstaller("esphome-satellite"):
  installer.title = "esphome-satellite Web Installer"
  installer.description = "On-device state supervisor for ESPHome and Home Assistant voice satellites with hardware target switching, multi-wake-word selection, and customizable audio feedback."
  installer.version = currentVersion
  installer.homeAssistantDomain = "esphome"
  installer.chipFamily = "ESP32-S3"
  installer.factoryBinPath = "firmware-factory.bin"

  # Hardware Board Targets
  installer.addTarget(
    name = "Seeed ReSpeaker XVF3800",
    binPath = "firmware-factory.bin",
    chipFamily = "ESP32-S3",
    description = "Seeed ReSpeaker XVF3800 with 4-mic array and hardware acoustic echo cancellation"
  )

  # Custom Wake Word Flasher (.tflite -> wake_model partition at 0x510000)
  installer.addCustomWakeWordField(
    name = "custom_wake_word",
    label = "Custom Wake Word Model (.tflite)",
    partition = "wake_model",
    flashOffset = 0x510000'u32,
    maxSize = 524288,
    defaultPhrase = "",
    defaultCutoff = 0.40,
    required = false,
    description = "Optional: Upload a microWakeWord .tflite model to flash directly into the dedicated wake_model partition (0x510000). At boot, the satellite automatically detects the model header, registers your custom wake word, and exposes it in Home Assistant alongside Okay Nabu and Mr. Clemens without re-compiling firmware."
  )

  # Built-in Wake Chimes Showcase (17 Pre-compiled Themes)
  installer.addAudioShowcase(
    name = "wake_chimes",
    label = "Built-in Wake Chimes (17 Acoustic Themes)",
    options = @[
      "Bell Ping (Default)", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
      "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
      "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime"
    ],
    defaultVal = "Bell Ping (Default)",
    description = "Acoustic acknowledgement chime played immediately upon wake word detection before opening the microphone. Pre-compiled in firmware and switchable anytime in Home Assistant.",
    optionDetails = @[
      optionDetail("Bell Ping (Default)", "Single tone (880Hz)", "Clean, crisp resonant bell with exponential acoustic decay (CC0)"),
      optionDetail("Modern Chime", "Two-tone ascending chord", "Modern minimalist crisp ascending harmonic chime (Kenney CC0)"),
      optionDetail("Crystal Glass", "Crystal ping resonance", "Modern minimalist delicate crystal resonance ping (CC0)"),
      optionDetail("Warm Kalimba", "Dual-tine acoustic strike", "Organic acoustic thumb piano with wooden body resonance (CC0)"),
      optionDetail("Meditation Bell", "Tibetan singing bowl", "Organic acoustic singing bowl with deep harmonic decay (CC0)"),
      optionDetail("Marimba", "Harmonic triad (523Hz, 659Hz, 784Hz)", "Organic mellow wooden marimba strike for discreet ambient homes (CC0)"),
      optionDetail("Subtle Beep", "Discrete blip (600Hz, 80ms)", "Minimal unobtrusive tick tone for quiet environments (CC0)"),
      optionDetail("Bamboo Chime", "Natural bamboo wind chime", "Organic acoustic hollow bamboo tubes resonant strike (CC0)"),
      optionDetail("Tibetan Bowl", "Himalayan brass bowl (432Hz)", "Organic acoustic singing bowl with golden overtone bloom (CC0)"),
      optionDetail("Acoustic Harp", "Concert harp pluck", "Organic acoustic ascending two-string concert harp pluck (CC-BY dobroide)"),
      optionDetail("Woodblock", "Hardwood temple block", "Organic natural rosewood temple block strike (Kenney CC0)"),
      optionDetail("Ceramic Bell", "Glazed porcelain bell", "Organic crystalline earthenware bell with high-frequency glaze shimmer (CC0)"),
      optionDetail("Neon Shimmer", "Lush analog FM chord", "Modern digital warm FM synth chord with soft glowing decay (Kenney CC0)"),
      optionDetail("Prism Ping", "Glass-digital harmonic ping", "Modern digital pristine glass-synth chime with overtone sparkle (CC0)"),
      optionDetail("Cyber Bloom", "Ascending synth arpeggio", "Modern digital ascending D5-A5-D6 synth arpeggio (Kenney CC0)"),
      optionDetail("Quantum Beep", "Precision micro-tone", "Modern digital precision dual-transient interface acknowledge (Kenney CC0)"),
      optionDetail("Aero Chime", "Spatial synth swell", "Modern digital airy spatial two-tone electronic acknowledgement (CC0)")
    ],
    presetAudios = @[
      ("Bell Ping (Default)", "sounds/bell-ping.mp3", "sounds/bell-ping.wav"),
      ("Modern Chime", "sounds/modern-chime.mp3", "sounds/modern-chime.wav"),
      ("Crystal Glass", "sounds/crystal-glass.mp3", "sounds/crystal-glass.wav"),
      ("Warm Kalimba", "sounds/warm-kalimba.mp3", "sounds/warm-kalimba.wav"),
      ("Meditation Bell", "sounds/meditation-bell.mp3", "sounds/meditation-bell.wav"),
      ("Marimba", "sounds/marimba.mp3", "sounds/marimba.wav"),
      ("Subtle Beep", "sounds/subtle-beep.mp3", "sounds/subtle-beep.wav"),
      ("Bamboo Chime", "sounds/bamboo-chime.mp3", "sounds/bamboo-chime.wav"),
      ("Tibetan Bowl", "sounds/tibetan-bowl.mp3", "sounds/tibetan-bowl.wav"),
      ("Acoustic Harp", "sounds/acoustic-harp.mp3", "sounds/acoustic-harp.wav"),
      ("Woodblock", "sounds/woodblock.mp3", "sounds/woodblock.wav"),
      ("Ceramic Bell", "sounds/ceramic-bell.mp3", "sounds/ceramic-bell.wav"),
      ("Neon Shimmer", "sounds/neon-shimmer.mp3", "sounds/neon-shimmer.wav"),
      ("Prism Ping", "sounds/prism-ping.mp3", "sounds/prism-ping.wav"),
      ("Cyber Bloom", "sounds/cyber-bloom.mp3", "sounds/cyber-bloom.wav"),
      ("Quantum Beep", "sounds/quantum-beep.mp3", "sounds/quantum-beep.wav"),
      ("Aero Chime", "sounds/aero-chime.mp3", "sounds/aero-chime.wav")
    ]
  )

  # Built-in Processing Sounds Showcase (17 Pre-compiled Themes)
  installer.addAudioShowcase(
    name = "processing_sounds",
    label = "Built-in Processing Sounds (17 Acoustic Themes)",
    options = @[
      "Spinner (Default)", "Pulse", "Sonar", "Tick", "Typewriter", "Clockwork", "Water Droplets",
      "Raindrops", "Forest Stream", "Campfire Ember", "Shishi-Odoshi", "Soft Footsteps",
      "Radar Ping", "Data Crunch", "Telemetry Blip", "Quantum Flux", "Retro Terminal"
    ],
    defaultVal = "Spinner (Default)",
    description = "Continuous acoustic feedback looped while the assistant processes speech. Pre-compiled in firmware with seamless zero-gap playback and selectable in Home Assistant.",
    optionDetails = @[
      optionDetail("Spinner (Default)", "120ms cadence", "Fast rhythmic progress ticking for rapid feedback (Kenney CC0)"),
      optionDetail("Pulse", "250ms cadence", "Subtle undulating heartbeat pattern for ambient presence (CC0)"),
      optionDetail("Sonar", "800ms cadence", "Periodic nautical acoustic ping for deliberate tracking (CC0)"),
      optionDetail("Tick", "500ms cadence", "Mechanical clockwork pulse for steady pacing (Kenney CC0)"),
      optionDetail("Typewriter", "Mechanical rhythm", "Soft acoustic typewriter keystrokes and mechanical chatter during LLM processing (CC0)"),
      optionDetail("Clockwork", "Watchmaker escapement", "Precision escapement tick-tock with seamless loop timing (CC0)"),
      optionDetail("Water Droplets", "Bubbly acoustic resonance", "Organic acoustic water droplets dripping into a calm pool (CC0)"),
      optionDetail("Raindrops", "Rain on foliage cadence", "Organic acoustic raindrops tapping softly on broad forest leaves (CC0)"),
      optionDetail("Forest Stream", "Mountain brook flow", "Organic gentle bubbling mountain brook stream with water eddies (CC0)"),
      optionDetail("Campfire Ember", "Wood crackle & pops", "Organic cozy woodfire crackles and soft ember pops (CC0)"),
      optionDetail("Shishi-Odoshi", "Bamboo rocker on stone", "Organic Japanese bamboo water rocker trickle and stone clack (CC-BY sonicfury)"),
      optionDetail("Soft Footsteps", "Paced footsteps on wood", "Organic subtle leather steps on hardwood indicating active thought (CC0)"),
      optionDetail("Radar Ping", "Sci-fi radar pulse", "Modern digital periodic radar sweep with resonant acoustic decay (Kenney CC0)"),
      optionDetail("Data Crunch", "Telemetry packet chatter", "Modern digital micro-packet processing chatter rhythm (CC0)"),
      optionDetail("Telemetry Blip", "Satellite tracking pulse", "Modern digital dual-harmonic instrument tracking blips (Kenney CC0)"),
      optionDetail("Quantum Flux", "LFO analog undulation", "Modern digital smooth undulating electronic rhythm (CC0)"),
      optionDetail("Retro Terminal", "Relay & tape flutter", "Modern digital vintage computer relay clicks and magnetic tape chatter (CC0)")
    ],
    presetAudios = @[
      ("Spinner (Default)", "sounds/spinner.mp3", "sounds/spinner.wav"),
      ("Pulse", "sounds/pulse.mp3", "sounds/pulse.wav"),
      ("Sonar", "sounds/sonar.mp3", "sounds/sonar.wav"),
      ("Tick", "sounds/tick.mp3", "sounds/tick.wav"),
      ("Typewriter", "sounds/typewriter.mp3", "sounds/typewriter.wav"),
      ("Clockwork", "sounds/clockwork.mp3", "sounds/clockwork.wav"),
      ("Water Droplets", "sounds/water-droplets.mp3", "sounds/water-droplets.wav"),
      ("Raindrops", "sounds/raindrops.mp3", "sounds/raindrops.wav"),
      ("Forest Stream", "sounds/forest-stream.mp3", "sounds/forest-stream.wav"),
      ("Campfire Ember", "sounds/campfire-ember.mp3", "sounds/campfire-ember.wav"),
      ("Shishi-Odoshi", "sounds/shishi-odoshi.mp3", "sounds/shishi-odoshi.wav"),
      ("Soft Footsteps", "sounds/soft-footsteps.mp3", "sounds/soft-footsteps.wav"),
      ("Radar Ping", "sounds/radar-ping.mp3", "sounds/radar-ping.wav"),
      ("Data Crunch", "sounds/data-crunch.mp3", "sounds/data-crunch.wav"),
      ("Telemetry Blip", "sounds/telemetry-blip.mp3", "sounds/telemetry-blip.wav"),
      ("Quantum Flux", "sounds/quantum-flux.mp3", "sounds/quantum-flux.wav"),
      ("Retro Terminal", "sounds/retro-terminal.mp3", "sounds/retro-terminal.wav")
    ]
  )

  # Built-in Cancel Sounds Showcase (17 Pre-compiled Themes)
  installer.addAudioShowcase(
    name = "cancel_sounds",
    label = "Built-in Cancel Sounds (17 Acoustic Themes)",
    options = @[
      "Bell Ping (Default)", "Modern Chime", "Crystal Glass", "Warm Kalimba", "Meditation Bell",
      "Marimba", "Subtle Beep", "Bamboo Chime", "Tibetan Bowl", "Acoustic Harp", "Woodblock",
      "Ceramic Bell", "Neon Shimmer", "Prism Ping", "Cyber Bloom", "Quantum Beep", "Aero Chime"
    ],
    defaultVal = "Bell Ping (Default)",
    description = "Audible cancellation tone played when a cancellation phrase ('stop', 'cancel', 'nevermind') is heard or speech recognition is aborted. Pre-compiled in firmware and selectable in Home Assistant.",
    optionDetails = @[
      optionDetail("Bell Ping (Default)", "Descending bell tone", "Crisp descending bell cancellation tone (CC0)"),
      optionDetail("Modern Chime", "Two-tone descending chord", "Clean downward harmonic resolve (Kenney CC0)"),
      optionDetail("Crystal Glass", "Downward crystal ping", "Gentle descending crystal note (CC0)"),
      optionDetail("Warm Kalimba", "Dual-tine downward strike", "Warm downward wooden thumb piano resolve (CC0)"),
      optionDetail("Meditation Bell", "Descending brass resonance", "Gentle calming singing bowl dampening tone (CC0)"),
      optionDetail("Marimba", "Descending wooden triad", "Discreet descending marimba strike (CC0)"),
      optionDetail("Subtle Beep", "Descending blip (80ms)", "Minimal downward cancellation tick (CC0)"),
      optionDetail("Bamboo Chime", "Descending bamboo tap", "Natural wood tap cancellation (CC0)"),
      optionDetail("Tibetan Bowl", "Calm bowl release", "Warm resonant bowl release tone (CC0)"),
      optionDetail("Acoustic Harp", "Descending harp pluck", "Gentle downward acoustic harp glissando note (CC-BY dobroide)"),
      optionDetail("Woodblock", "Downward temple block", "Natural temple block cancellation click (Kenney CC0)"),
      optionDetail("Ceramic Bell", "Porcelain dampening", "High-frequency earthenware tone release (CC0)"),
      optionDetail("Neon Shimmer", "Descending FM synth", "Warm analog FM downward sweep (Kenney CC0)"),
      optionDetail("Prism Ping", "Descending glass sparkle", "Digital downward prism tone (CC0)"),
      optionDetail("Cyber Bloom", "Descending synth arpeggio", "Futuristic descending electronic resolve (Kenney CC0)"),
      optionDetail("Quantum Beep", "Dual-tone micro abort", "Fast low-profile cancellation beep (Kenney CC0)"),
      optionDetail("Aero Chime", "Descending spatial swell", "Spatial downward atmospheric electronic note (CC0)")
    ],
    presetAudios = @[
      ("Bell Ping (Default)", "sounds/cancel-bell-ping.mp3", "sounds/cancel-bell-ping.wav"),
      ("Modern Chime", "sounds/cancel-modern-chime.mp3", "sounds/cancel-modern-chime.wav"),
      ("Crystal Glass", "sounds/cancel-crystal-glass.mp3", "sounds/cancel-crystal-glass.wav"),
      ("Warm Kalimba", "sounds/cancel-warm-kalimba.mp3", "sounds/cancel-warm-kalimba.wav"),
      ("Meditation Bell", "sounds/cancel-meditation-bell.mp3", "sounds/cancel-meditation-bell.wav"),
      ("Marimba", "sounds/cancel-marimba.mp3", "sounds/cancel-marimba.wav"),
      ("Subtle Beep", "sounds/cancel-subtle-beep.mp3", "sounds/cancel-subtle-beep.wav"),
      ("Bamboo Chime", "sounds/cancel-bamboo-chime.mp3", "sounds/cancel-bamboo-chime.wav"),
      ("Tibetan Bowl", "sounds/cancel-tibetan-bowl.mp3", "sounds/cancel-tibetan-bowl.wav"),
      ("Acoustic Harp", "sounds/cancel-acoustic-harp.mp3", "sounds/cancel-acoustic-harp.wav"),
      ("Woodblock", "sounds/cancel-woodblock.mp3", "sounds/cancel-woodblock.wav"),
      ("Ceramic Bell", "sounds/cancel-ceramic-bell.mp3", "sounds/cancel-ceramic-bell.wav"),
      ("Neon Shimmer", "sounds/cancel-neon-shimmer.mp3", "sounds/cancel-neon-shimmer.wav"),
      ("Prism Ping", "sounds/cancel-prism-ping.mp3", "sounds/cancel-prism-ping.wav"),
      ("Cyber Bloom", "sounds/cancel-cyber-bloom.mp3", "sounds/cancel-cyber-bloom.wav"),
      ("Quantum Beep", "sounds/cancel-quantum-beep.mp3", "sounds/cancel-quantum-beep.wav"),
      ("Aero Chime", "sounds/cancel-aero-chime.mp3", "sounds/cancel-aero-chime.wav")
    ]
  )

writeFile("web/index.html", satelliteInstaller.generateHtml())
writeFile("web/manifest.json", satelliteInstaller.generateManifest())
echo "Successfully generated web/index.html and web/manifest.json (v" & currentVersion & ") via nim-esphome DSL!"
