## XVF3800 Hardware Control & LED Animation Engine in Nim
##
## Implements XMOS XVF3800 GPO register payloads and the 12-LED ring animation
## state machine for visual voice satellite feedback.

import std/math

const
  GPO_SERVICER_RESID* = 20'u8
  GPO_CMD_WRITE_VALUE* = 1'u8
  GPO_CMD_LED_RING* = 18'u8

  PIN_MIC_MUTE* = 30'u8    ## 1 = muted, 0 = unmuted
  PIN_AMP_ENABLE* = 31'u8  ## 0 = enabled (active low), 1 = disabled
  PIN_LED_POWER* = 33'u8   ## 1 = power on, 0 = power off

  XVF3800_I2C_ADDR* = 0x2C'u8
  AIC3104_I2C_ADDR* = 0x18'u8

proc makeGpoPayload*(pin: uint8, val: uint8): array[5, uint8] {.inline.} =
  [GPO_SERVICER_RESID, GPO_CMD_WRITE_VALUE, 2'u8, pin, val]

proc makeLedRingPayload*(colors: openArray[uint32]): seq[uint8] =
  result = newSeq[uint8](3 + 48)
  result[0] = GPO_SERVICER_RESID
  result[1] = GPO_CMD_LED_RING
  result[2] = 48'u8

  let count = min(colors.len, 12)
  for i in 0 ..< count:
    let c = colors[i]
    result[3 + i * 4 + 0] = uint8(c and 0xFF'u32)         # Blue
    result[3 + i * 4 + 1] = uint8((c shr 8) and 0xFF'u32)  # Green
    result[3 + i * 4 + 2] = uint8((c shr 16) and 0xFF'u32) # Red
    result[3 + i * 4 + 3] = 0x00'u8

proc computeAnimationColors*(
    stateName: string,
    patternPref: string,
    brightnessIn: float32,
    nowMs: uint32
): array[12, uint32] =
  let brightness = clamp(brightnessIn, 0.05'f32, 1.0'f32)
  let now = float32(nowMs)

  case stateName
  of "Muted":
    let red = uint32(uint8(255.0'f32 * brightness)) shl 16
    for i in 0 ..< 12:
      result[i] = red
  of "Woken", "Listening":
    let pulse = 0.6'f32 + 0.4'f32 * sin(now * 0.008'f32)
    let g = uint32(uint8(clamp(200.0'f32 * pulse * brightness, 0.0'f32, 255.0'f32))) shl 8
    let b = uint32(uint8(clamp(255.0'f32 * pulse * brightness, 0.0'f32, 255.0'f32)))
    let cyan = g or b
    for i in 0 ..< 12:
      result[i] = cyan
  of "Follow Up":
    # Conversational mode active listening: distinctive breathing emerald-teal wave
    let pulse = 0.55'f32 + 0.45'f32 * sin(now * 0.007'f32)
    let head = int((nowMs div 120'u32) mod 12'u32)
    for i in 0 ..< 12:
      let dist = (head - i + 12) mod 12
      let accent = if dist == 0: 1.35'f32 elif dist == 1 or dist == 11: 1.15'f32 else: 1.0'f32
      let g = uint32(uint8(clamp(220.0'f32 * pulse * accent * brightness, 0.0'f32, 255.0'f32))) shl 8
      let b = uint32(uint8(clamp(150.0'f32 * pulse * accent * brightness, 0.0'f32, 255.0'f32)))
      let r = uint32(uint8(clamp(15.0'f32 * pulse * accent * brightness, 0.0'f32, 255.0'f32))) shl 16
      result[i] = r or g or b
  of "Thinking":
    let head = int((nowMs div 70'u32) mod 12'u32)
    for i in 0 ..< 12:
      let dist = (head - i + 12) mod 12
      var factor = 0.0'f32
      if dist == 0: factor = 1.0'f32
      elif dist == 1: factor = 0.6'f32
      elif dist == 2: factor = 0.25'f32
      elif dist == 3: factor = 0.08'f32

      if factor > 0.0'f32:
        let r = uint32(uint8(100.0'f32 * factor * brightness)) shl 16
        let g = uint32(uint8(150.0'f32 * factor * brightness)) shl 8
        let b = uint32(uint8(255.0'f32 * factor * brightness))
        result[i] = r or g or b
  of "Replying":
    let breath = 0.5'f32 + 0.5'f32 * sin(now * 0.006'f32)
    let r = uint32(uint8(clamp(255.0'f32 * breath * brightness, 0.0'f32, 255.0'f32))) shl 16
    let g = uint32(uint8(clamp(180.0'f32 * breath * brightness, 0.0'f32, 255.0'f32))) shl 8
    let b = uint32(uint8(clamp(40.0'f32 * breath * brightness, 0.0'f32, 255.0'f32)))
    let amber = r or g or b
    for i in 0 ..< 12:
      result[i] = amber
  of "Cancelling":
    let orange = (uint32(uint8(255.0'f32 * brightness)) shl 16) or (uint32(uint8(120.0'f32 * brightness)) shl 8)
    for i in 0 ..< 12:
      result[i] = orange
  of "Pipeline Error", "Connection Error":
    let on = (nowMs div 250'u32) mod 2'u32 == 0'u32
    let red = if on: (uint32(uint8(255.0'f32 * brightness)) shl 16) else: 0'u32
    for i in 0 ..< 12:
      result[i] = red
  else:
    case patternPref
    of "Off", "Silent":
      discard
    of "Breathe":
      let bth = 0.15'f32 + 0.15'f32 * sin(now * 0.002'f32)
      let val = uint32(uint8(clamp(255.0'f32 * bth * brightness, 0.0'f32, 255.0'f32)))
      let softBlue = ((val div 2'u32) shl 16) or (val shl 8) or val
      for i in 0 ..< 12:
        result[i] = softBlue
    of "Rainbow":
      let hueOffset = float32((nowMs mod 4000'u32)) / 4000.0'f32
      for i in 0 ..< 12:
        var h = hueOffset + (float32(i) / 12.0'f32)
        h = h - floor(h)
        var rf, gf, bf: float32
        let hi = int(h * 6.0'f32)
        let f = h * 6.0'f32 - float32(hi)
        let q = 1.0'f32 - f
        let val = 0.35'f32 * brightness
        case hi mod 6
        of 0: rf = val; gf = val * f; bf = 0.0'f32
        of 1: rf = val * q; gf = val; bf = 0.0'f32
        of 2: rf = 0.0'f32; gf = val; bf = val * f
        of 3: rf = 0.0'f32; gf = val * q; bf = val
        of 4: rf = val * f; gf = 0.0'f32; bf = val
        else: rf = val; gf = 0.0'f32; bf = val * q
        let r = uint32(uint8(clamp(rf * 255.0'f32, 0.0'f32, 255.0'f32))) shl 16
        let g = uint32(uint8(clamp(gf * 255.0'f32, 0.0'f32, 255.0'f32))) shl 8
        let b = uint32(uint8(clamp(bf * 255.0'f32, 0.0'f32, 255.0'f32)))
        result[i] = r or g or b
    of "Spinner":
      let head = int((nowMs div 200'u32) mod 12'u32)
      let g = uint32(uint8(40.0'f32 * brightness)) shl 8
      let b = uint32(uint8(100.0'f32 * brightness))
      result[head] = g or b
    else:
      discard

# C ABI bridge exports
proc nim_xvf3800_make_gpo_payload*(pin: uint8, val: uint8, outBuf: ptr UncheckedArray[uint8]) {.exportc, cdecl.} =
  if outBuf != nil:
    let p = makeGpoPayload(pin, val)
    copyMem(addr outBuf[0], unsafeAddr p[0], 5)

proc nim_xvf3800_update_animation*(
    stateName: cstring,
    patternPref: cstring,
    brightness: cfloat,
    nowMs: uint32,
    outColors: ptr UncheckedArray[uint32]
) {.exportc, cdecl.} =
  if outColors != nil:
    let st = if stateName != nil: $stateName else: "Idle"
    let pat = if patternPref != nil: $patternPref else: "Off"
    let colors = computeAnimationColors(st, pat, float32(brightness), nowMs)
    copyMem(addr outColors[0], unsafeAddr colors[0], sizeof(uint32) * 12)

const XVF3800_REBOOT_PAYLOAD*: array[4, uint8] = [240'u8, 89'u8, 1'u8, 0'u8]

proc nim_xvf3800_get_reboot_payload*(outBuf: ptr UncheckedArray[uint8]): csize_t {.exportc, cdecl.} =
  if outBuf != nil:
    copyMem(addr outBuf[0], unsafeAddr XVF3800_REBOOT_PAYLOAD[0], 4)
  return 4
