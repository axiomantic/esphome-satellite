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
