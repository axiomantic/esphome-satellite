import std/unittest

import ../src/xvf3800_hardware

suite "XVF3800 Hardware & Animation Suite (TDD)":
  test "GPO payload generation":
    let p1 = makeGpoPayload(30'u8, 1'u8) # Mute on
    check p1[0] == 20'u8 # GPO_SERVICER_RESID
    check p1[1] == 1'u8  # GPO_CMD_WRITE_VALUE
    check p1[2] == 2'u8  # Length
    check p1[3] == 30'u8 # Pin
    check p1[4] == 1'u8  # Value

    let p2 = makeGpoPayload(31'u8, 0'u8) # Amp enable (active low)
    check p2[3] == 31'u8
    check p2[4] == 0'u8

  test "LED ring payload formatting":
    var colors: array[12, uint32]
    colors[0] = 0x00FF8800'u32 # Orange (R=FF, G=88, B=00)
    let payload = makeLedRingPayload(colors)
    check payload.len == 3 + 48
    check payload[0] == 20'u8 # resid
    check payload[1] == 18'u8 # cmd led ring
    check payload[2] == 48'u8 # byte length
    # Check color 0: B, G, R, 0
    check payload[3] == 0x00'u8 # Blue
    check payload[4] == 0x88'u8 # Green
    check payload[5] == 0xFF'u8 # Red
    check payload[6] == 0x00'u8 # Pad

  test "LED animation states - Muted produces solid red":
    let colors = computeAnimationColors("Muted", "Off", 1.0'f32, 1000'u32)
    for c in colors:
      check (c and 0x00FF0000'u32) == 0x00FF0000'u32 # Red channel 255
      check (c and 0x0000FFFF'u32) == 0'u32          # Green and Blue 0

  test "LED animation states - Listening produces pulsing cyan/blue":
    let colors = computeAnimationColors("Listening", "Off", 1.0'f32, 1000'u32)
    for c in colors:
      check (c and 0x00FF0000'u32) == 0'u32          # Red channel 0
      check (c and 0x000000FF'u32) > 0'u32          # Blue channel active
      check (c and 0x0000FF00'u32) > 0'u32          # Green channel active

  test "LED animation states - Follow Up produces conversational listening emerald-teal wave":
    let colors = computeAnimationColors("Follow Up", "Off", 1.0'f32, 1000'u32)
    for c in colors:
      let r = (c shr 16) and 0xFF'u32
      let g = (c shr 8) and 0xFF'u32
      let b = c and 0xFF'u32
      check g > 0'u32 # Green active
      check b > 0'u32 # Blue active
      check g > r     # Green dominant over red (emerald-teal tone)

  test "LED animation states - Thinking produces 12-LED rotating spinner with decay":
    let colors = computeAnimationColors("Thinking", "Off", 1.0'f32, 0'u32)
    # Head at 0 has highest brightness
    let head = colors[0]
    check head > 0'u32
    # At least some trailing LEDs are dimmer or unlit
    check colors[6] == 0'u32

  test "XMOS reboot command payload format":
    check XVF3800_REBOOT_PAYLOAD == [240'u8, 89'u8, 1'u8, 0'u8]
    var buf: array[4, uint8]
    let written = nim_xvf3800_get_reboot_payload(cast[ptr UncheckedArray[uint8]](addr buf[0]))
    check written == 4
    check buf == [240'u8, 89'u8, 1'u8, 0'u8]

  test "AIC3104 initialization registers include DAC power and headphone/lineout routing":
    let regs = makeAic3104InitRegisters()
    check regs.len >= 14
    var foundPage0 = false
    var foundDacPower = false
    var foundHpRoute = false
    var foundHpLevel = false
    var foundLopRoute = false
    var foundLopLevel = false

    for r in regs:
      if r.reg == 0x00'u8 and r.val == 0x00'u8: foundPage0 = true
      if r.reg == 0x25'u8 and r.val == 0xC0'u8: foundDacPower = true
      if r.reg == 0x2F'u8 and r.val == 0x80'u8: foundHpRoute = true
      if r.reg == 0x33'u8 and r.val == 0x0D'u8: foundHpLevel = true
      if r.reg == 0x52'u8 and r.val == 0x80'u8: foundLopRoute = true
      if r.reg == 0x56'u8 and r.val == 0x0B'u8: foundLopLevel = true

    check foundPage0
    check foundDacPower
    check foundHpRoute
    check foundHpLevel
    check foundLopRoute
    check foundLopLevel

  test "AIC3104 volume calculation handles mute, normal, and boost curves":
    let muted = computeAic3104Volume(0.8'f32, true)
    check muted.dacVal == 0x80'u8
    check (muted.hpLevel and 0x08'u8) > 0'u8 or muted.hpLevel == 0x08'u8 # Muted bit set

    let zero = computeAic3104Volume(0.0'f32, false)
    check zero.dacVal == 0x80'u8

    let normal = computeAic3104Volume(0.8'f32, false)
    check normal.dacVal == 0x00'u8  # 0dB digital attenuation
    check normal.hpLevel == 0x0D'u8 # 0dB analog gain, unmuted, powered up
    check normal.lopLevel == 0x0B'u8 # 0dB analog gain, unmuted, powered up

    let maxBoost = computeAic3104Volume(1.0'f32, false)
    check maxBoost.dacVal == 0x00'u8
    check (maxBoost.hpLevel shr 4) == 9'u8 # +9dB analog boost
    check (maxBoost.hpLevel and 0x0F'u8) == 0x0D'u8 # unmuted, powered up
    check (maxBoost.lopLevel shr 4) == 9'u8 # +9dB analog boost

  test "XMOS AIC3104 level commands payload formatting":
    let p1 = makeXmosAic3104LevelPayload(XMOS_CMD_AIC3104_HP_LEVEL, 9'u8)
    check p1 == [48'u8, 11'u8, 1'u8, 9'u8]

    let p2 = makeXmosAic3104LevelPayload(XMOS_CMD_AIC3104_LINEOUT_LEVEL, 9'u8)
    check p2 == [48'u8, 12'u8, 1'u8, 9'u8]

  test "AIC3104 dedicated headphone gain calculation":
    check computeAic3104HpGain(0.0'f32) == 0'u8
    check computeAic3104HpGain(0.5'f32) == 5'u8
    check computeAic3104HpGain(1.0'f32) == 9'u8
    check computeAic3104HpGain(1.5'f32) == 9'u8

  test "AIC3104 dedicated headphone level register calculation with zero mute":
    # 0.0 volume must mute and power down driver (0x08)
    let (hpZero, lopZero) = computeAic3104HpLevel(0.0'f32)
    check hpZero == 0x08'u8
    check lopZero == 0x08'u8

    # 0.5 volume must set gain to 5 with unmuted/power-up flags (0x5D / 0x5B)
    let (hpMid, lopMid) = computeAic3104HpLevel(0.5'f32)
    check hpMid == ((5'u8 shl 4) or 0x0D'u8)
    check lopMid == ((5'u8 shl 4) or 0x0B'u8)

    # 1.0 volume must set gain to 9 (0x9D / 0x9B)
    let (hpMax, lopMax) = computeAic3104HpLevel(1.0'f32)
    check hpMax == ((9'u8 shl 4) or 0x0D'u8)
    check lopMax == ((9'u8 shl 4) or 0x0B'u8)

