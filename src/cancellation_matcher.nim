## Cancellation Phrase Matcher in Nim
##
## Detects voice assistant cancellation intents ("stop", "nevermind", "abort", "cancel", etc.)
## with robust normalization (case folding, punctuation stripping, word boundary detection).
##
## Self-contained without external dependencies to guarantee clean embedded C ABI linking.

const DefaultCancellationWords*: seq[string] = @[
  "stop",
  "nevermind",
  "never mind",
  "abort",
  "cancel",
  "dismiss",
  "quit",
  "quiet",
  "silence",
  "shut up"
]

proc startsWith*(s, prefix: string): bool =
  if prefix.len > s.len: return false
  for i in 0 ..< prefix.len:
    if s[i] != prefix[i]: return false
  return true

proc endsWith*(s, suffix: string): bool =
  if suffix.len > s.len: return false
  let offset = s.len - suffix.len
  for i in 0 ..< suffix.len:
    if s[offset + i] != suffix[i]: return false
  return true

proc containsSub*(s, sub: string): bool =
  if sub.len > s.len: return false
  if sub.len == 0: return true
  for i in 0 .. (s.len - sub.len):
    var match = true
    for j in 0 ..< sub.len:
      if s[i + j] != sub[j]:
        match = false
        break
    if match: return true
  return false

proc normalizeText*(s: string): string =
  result = ""
  var lastWasSpace = true
  for c in s:
    var ch = c
    if ch in {'A'..'Z'}:
      ch = chr(ord(ch) + 32)
    if ch in {'a'..'z', '0'..'9'}:
      result.add(ch)
      lastWasSpace = false
    elif ch == '-' or ch == ' ' or ch == '\t' or ch == '\r' or ch == '\n':
      if not lastWasSpace:
        result.add(' ')
        lastWasSpace = true
  while result.len > 0 and result[^1] == ' ':
    result.setLen(result.len - 1)

proc parseCancellationConfig*(cfg: string): seq[string] =
  if cfg.len == 0:
    return DefaultCancellationWords
  result = @[]
  var cur = ""
  for c in cfg:
    if c == ',':
      let norm = normalizeText(cur)
      if norm.len > 0:
        result.add(norm)
      cur = ""
    else:
      cur.add(c)
  if cur.len > 0:
    let norm = normalizeText(cur)
    if norm.len > 0:
      result.add(norm)
  if result.len == 0:
    result = DefaultCancellationWords

proc isCancellationPhrase*(text: string, configWords: string = ""): bool =
  let cleanText = normalizeText(text)
  if cleanText.len == 0:
    return false

  let targets = parseCancellationConfig(configWords)
  for target in targets:
    if cleanText == target:
      return true
    if startsWith(cleanText, target & " "):
      return true
    if endsWith(cleanText, " " & target):
      return true
    if containsSub(cleanText, " " & target & " "):
      return true

  return false

proc nim_satellite_is_cancellation*(text: cstring, config: cstring = nil): bool {.exportc, cdecl.} =
  if text == nil:
    return false
  let t = $text
  let c = if config != nil: $config else: ""
  return isCancellationPhrase(t, c)

const DefaultResetPhrases*: seq[string] = @[
  "forget our conversation",
  "forget my conversation",
  "forget this conversation",
  "clear history",
  "clear the history",
  "clear conversation",
  "clear conversation history",
  "reset conversation",
  "reset the conversation",
  "new conversation",
  "start a new conversation",
  "start new conversation",
  "forget everything"
]

proc isConversationResetPhrase*(text: string): bool =
  let cleanText = normalizeText(text)
  if cleanText.len == 0:
    return false

  for target in DefaultResetPhrases:
    if cleanText == target:
      return true
    if startsWith(cleanText, target & " "):
      return true
    if endsWith(cleanText, " " & target):
      return true
    if containsSub(cleanText, " " & target & " "):
      return true

  return false

proc nim_satellite_is_reset_phrase*(text: cstring): bool {.exportc, cdecl.} =
  if text == nil:
    return false
  return isConversationResetPhrase($text)

type
  SatelliteVolumeActionKind* = enum
    svakNone = 0,
    svakDown = 1,
    svakUp = 2,
    svakSet = 3,
    svakMute = 4,
    svakUnmute = 5

proc parsePercentage*(cleanText: string): int =
  result = -1
  var curNum = 0
  var foundDigits = false
  for i in 0 ..< cleanText.len:
    let c = cleanText[i]
    if c in {'0'..'9'}:
      curNum = curNum * 10 + (ord(c) - ord('0'))
      foundDigits = true
    elif foundDigits:
      if curNum >= 0 and curNum <= 100:
        return curNum
      curNum = 0
      foundDigits = false
  if foundDigits and curNum >= 0 and curNum <= 100:
    return curNum

  const wordPairs = [
    ("zero", 0), ("ten", 10), ("twenty", 20), ("twenty five", 25),
    ("thirty", 30), ("thirty five", 35), ("forty", 40), ("forty five", 45),
    ("fifty", 50), ("fifty five", 55), ("sixty", 60), ("sixty five", 65),
    ("seventy", 70), ("seventy five", 75), ("eighty", 80), ("eighty five", 85),
    ("ninety", 90), ("ninety five", 95), ("one hundred", 100), ("hundred", 100),
    ("maximum", 100), ("max", 100), ("minimum", 0), ("min", 0)
  ]
  for pair in wordPairs:
    let word = pair[0]
    let val = pair[1]
    if cleanText == word or startsWith(cleanText, word & " ") or endsWith(cleanText, " " & word) or containsSub(cleanText, " " & word & " "):
      return val

proc matchSatelliteVolumeAction*(text: string): tuple[action: SatelliteVolumeActionKind, targetPercent: int] =
  let cleanText = normalizeText(text)
  if cleanText.len == 0:
    return (svakNone, -1)

  # Check for direct speech volume commands
  if containsSub(cleanText, "speak softer") or
     containsSub(cleanText, "talk softer") or
     containsSub(cleanText, "speak quieter") or
     containsSub(cleanText, "talk quieter") or
     containsSub(cleanText, "be quieter") or
     containsSub(cleanText, "you are too loud") or
     containsSub(cleanText, "youre too loud") or
     cleanText == "too loud" or startsWith(cleanText, "too loud ") or endsWith(cleanText, " too loud") or containsSub(cleanText, " too loud "):
    return (svakDown, -1)

  if containsSub(cleanText, "speak louder") or
     containsSub(cleanText, "talk louder") or
     containsSub(cleanText, "speak up") or
     containsSub(cleanText, "talk up") or
     containsSub(cleanText, "you are too quiet") or
     containsSub(cleanText, "youre too quiet") or
     cleanText == "too quiet" or startsWith(cleanText, "too quiet ") or endsWith(cleanText, " too quiet") or containsSub(cleanText, " too quiet ") or
     containsSub(cleanText, "cant hear you"):
    return (svakUp, -1)

  let hasSelfRef = containsSub(cleanText, "your volume") or
                   containsSub(cleanText, "your voice") or
                   containsSub(cleanText, "your sound") or
                   containsSub(cleanText, "your speaker") or
                   containsSub(cleanText, "your speakers") or
                   containsSub(cleanText, "yourself") or
                   containsSub(cleanText, "this satellite") or
                   containsSub(cleanText, "this board") or
                   containsSub(cleanText, "this speaker")

  if not hasSelfRef:
    return (svakNone, -1)

  if containsSub(cleanText, "unmute") or containsSub(cleanText, "un-mute"):
    return (svakUnmute, -1)
  if containsSub(cleanText, "mute"):
    return (svakMute, -1)

  let pct = parsePercentage(cleanText)
  if pct >= 0 and (containsSub(cleanText, "set") or containsSub(cleanText, "to") or containsSub(cleanText, "at") or containsSub(cleanText, "put")):
    return (svakSet, pct)

  if containsSub(cleanText, "down") or
     containsSub(cleanText, "lower") or
     containsSub(cleanText, "decrease") or
     containsSub(cleanText, "quieter") or
     containsSub(cleanText, "drop") or
     containsSub(cleanText, "soften"):
    return (svakDown, -1)

  if containsSub(cleanText, "up") or
     containsSub(cleanText, "raise") or
     containsSub(cleanText, "increase") or
     containsSub(cleanText, "louder") or
     containsSub(cleanText, "boost") or
     containsSub(cleanText, "higher"):
    return (svakUp, -1)

  return (svakNone, -1)

proc nim_satellite_match_volume_action*(text: cstring, outTargetVol: ptr cint): cint {.exportc, cdecl.} =
  if text == nil:
    return 0
  let res = matchSatelliteVolumeAction($text)
  if outTargetVol != nil:
    outTargetVol[] = cint(res.targetPercent)
  return cint(ord(res.action))

proc containsWord*(s, target: string): bool =
  if s == target: return true
  if startsWith(s, target & " "): return true
  if endsWith(s, " " & target): return true
  if containsSub(s, " " & target & " "): return true
  return false

const WakeWordStopWords*: seq[string] = @[
  "hey", "hi", "hello", "ok", "okay", "the", "a", "an", "for", "with", "and"
]

proc verifyWakeWordPhrase*(transcript: string, wakeWord: string): bool =
  let cleanText = normalizeText(transcript)
  let cleanWw = normalizeText(wakeWord)
  if cleanText.len == 0 or cleanWw.len == 0:
    return false

  # 1. Full phrase or multi-word match
  if containsSub(cleanText, cleanWw):
    return true

  # 2. Phonetic expansions for Clemens / Twain
  if containsSub(cleanWw, "clemens") or containsSub(cleanWw, "twain"):
    const clemensVariants: array[7, string] = [
      "clemens", "clement", "clements", "cleman", "clemon", "twain", "mark twain"
    ]
    for v in clemensVariants:
      if containsWord(cleanText, v):
        return true

  # 3. Contraction / phonetic variants for initials (e.g. KT / Kay Tee)
  if containsSub(cleanWw, "kay tee") or containsSub(cleanWw, "kt"):
    const ktVariants: array[4, string] = ["kt", "k t", "kay tee", "kaytee"]
    for v in ktVariants:
      if containsWord(cleanText, v):
        return true

  # 4. Token-level matching with word boundaries
  var curWord = ""
  for c in cleanWw:
    if c == ' ':
      if curWord.len >= 3 and curWord notin WakeWordStopWords:
        if containsWord(cleanText, curWord):
          return true
      curWord = ""
    else:
      curWord.add(c)
  if curWord.len >= 3 and curWord notin WakeWordStopWords:
    if containsWord(cleanText, curWord):
      return true

  return false

proc nim_satellite_verify_wake_word*(text: cstring, wakeWord: cstring): bool {.exportc, cdecl.} =
  if text == nil or wakeWord == nil:
    return false
  return verifyWakeWordPhrase($text, $wakeWord)

