## Satellite System Control & OTA Update Orchestration in Nim
##
## Implements:
## - Software system restart (invoking App.safe_reboot via nim-esphome API)
## - FreeRTOS microWakeWord task suspension and resumption to prevent flash cache panics
## - Firmware OTA download, validation, partition writing, and boot configuration

import nim_esphome

when defined(esp32) or defined(freertos):
  type
    TaskHandle_t = pointer
    esp_err_t = cint
    esp_ota_handle_t = uint32
    esp_partition_t {.importc: "const esp_partition_t*", header: "<esp_partition.h>".} = pointer
    esp_http_client_handle_t {.importc: "esp_http_client_handle_t", header: "<esp_http_client.h>".} = pointer

    esp_http_client_config_t {.importc: "esp_http_client_config_t", header: "<esp_http_client.h>", bycopy.} = object
      url: cstring
      timeout_ms: cint
      keep_alive_enable: bool
      buffer_size: cint
      buffer_size_tx: cint
      crt_bundle_attach: pointer
      skip_cert_common_name_check: bool
      max_redirection_count: cint

  const
    ESP_OK = 0.cint
    OTA_WITH_SEQUENTIAL_WRITES = 0xFFFFFFFF'u32

  proc xTaskGetHandle*(pcNameToQuery: cstring): TaskHandle_t {.importc: "xTaskGetHandle", header: "<freertos/FreeRTOS.h>", cdecl.}
  proc vTaskSuspend*(xTaskToSuspend: TaskHandle_t) {.importc: "vTaskSuspend", header: "<freertos/task.h>", cdecl.}
  proc vTaskResume*(xTaskToResume: TaskHandle_t) {.importc: "vTaskResume", header: "<freertos/task.h>", cdecl.}
  proc vTaskDelay*(xTicksToDelay: uint32) {.importc: "vTaskDelay", header: "<freertos/task.h>", cdecl.}

  proc esp_ota_get_next_update_partition*(start_from: pointer): pointer {.importc: "esp_ota_get_next_update_partition", header: "<esp_ota_ops.h>", cdecl.}
  proc esp_ota_begin*(partition: pointer, image_size: csize_t, out_handle: ptr esp_ota_handle_t): esp_err_t {.importc: "esp_ota_begin", header: "<esp_ota_ops.h>", cdecl.}
  proc esp_ota_write*(handle: esp_ota_handle_t, data: pointer, size: csize_t): esp_err_t {.importc: "esp_ota_write", header: "<esp_ota_ops.h>", cdecl.}
  proc esp_ota_end*(handle: esp_ota_handle_t): esp_err_t {.importc: "esp_ota_end", header: "<esp_ota_ops.h>", cdecl.}
  proc esp_ota_abort*(handle: esp_ota_handle_t): esp_err_t {.importc: "esp_ota_abort", header: "<esp_ota_ops.h>", cdecl.}
  proc esp_ota_set_boot_partition*(partition: pointer): esp_err_t {.importc: "esp_ota_set_boot_partition", header: "<esp_ota_ops.h>", cdecl.}

  proc esp_http_client_init*(config: ptr esp_http_client_config_t): esp_http_client_handle_t {.importc: "esp_http_client_init", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_open*(client: esp_http_client_handle_t, write_len: cint): esp_err_t {.importc: "esp_http_client_open", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_fetch_headers*(client: esp_http_client_handle_t): cint {.importc: "esp_http_client_fetch_headers", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_get_status_code*(client: esp_http_client_handle_t): cint {.importc: "esp_http_client_get_status_code", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_read*(client: esp_http_client_handle_t, buffer: pointer, len: cint): cint {.importc: "esp_http_client_read", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_is_complete_data_received*(client: esp_http_client_handle_t): bool {.importc: "esp_http_client_is_complete_data_received", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_close*(client: esp_http_client_handle_t): esp_err_t {.importc: "esp_http_client_close", header: "<esp_http_client.h>", cdecl.}
  proc esp_http_client_cleanup*(client: esp_http_client_handle_t): esp_err_t {.importc: "esp_http_client_cleanup", header: "<esp_http_client.h>", cdecl.}

  proc esp_crt_bundle_attach*(conf: pointer): esp_err_t {.importc: "esp_crt_bundle_attach", header: "<esp_crt_bundle.h>", cdecl.}

# Forward declarations of FSM callbacks if not already declared in compilation unit
when not declared(nim_satellite_ota_start):
  proc nim_satellite_ota_start*() {.importc: "nim_satellite_ota_start", cdecl.}
when not declared(nim_satellite_ota_end):
  proc nim_satellite_ota_end*(ok: bool) {.importc: "nim_satellite_ota_end", cdecl.}

proc nim_satellite_restart*() {.exportc, cdecl.} =
  ## Triggers a clean software restart of the satellite with a 1-second grace delay.
  info("SatelliteSystem", "Software restart requested. Rebooting in 1000ms...")
  delayMs(1000)
  reboot()

proc nim_satellite_suspend_inference*() {.exportc, cdecl.} =
  ## Suspends microWakeWord FreeRTOS task to prevent CPU 0 instruction cache invalidation
  ## while flash memory sectors are erased and written during OTA.
  info("SatelliteSystem", "Suspending microWakeWord inference before flash operations...")
  when defined(esp32) or defined(freertos):
    let task = xTaskGetHandle("mww")
    if task != nil:
      info("SatelliteSystem", "Suspending FreeRTOS 'mww' task during flash write...")
      vTaskSuspend(task)
  else:
    discard

proc nim_satellite_resume_inference*() {.exportc, cdecl.} =
  ## Resumes microWakeWord FreeRTOS task after flash operations complete.
  info("SatelliteSystem", "Resuming microWakeWord inference after flash operations...")
  when defined(esp32) or defined(freertos):
    let task = xTaskGetHandle("mww")
    if task != nil:
      info("SatelliteSystem", "Resuming FreeRTOS 'mww' task...")
      vTaskResume(task)
  else:
    discard

proc isValidOtaUrl*(url: string): bool =
  ## Validates that the OTA URL starts with http:// or https:// and is non-empty.
  if url.len < 10: return false
  if not (url.startsWith("http://") or url.startsWith("https://")): return false
  result = true

proc nim_satellite_flash_firmware_ota*(urlCStr: cstring): bool {.exportc, cdecl.} =
  ## Orchestrates remote firmware OTA download and partition writing in Nim.
  if urlCStr == nil:
    error("SatelliteOTA", "Firmware OTA URL is null!")
    return false

  let url = $urlCStr
  if not isValidOtaUrl(url):
    error("SatelliteOTA", "Firmware OTA URL is invalid: " & url)
    return false

  info("SatelliteOTA", "Starting remote firmware OTA from URL: " & url)

  # Notify FSM to enter Updating typestate (suppresses DSP audio & sets LEDs)
  nim_satellite_ota_start()

  # Suspend inference FreeRTOS task to prevent flash cache collision
  nim_satellite_suspend_inference()

  when defined(esp32) or defined(freertos):
    let updatePartition = esp_ota_get_next_update_partition(nil)
    if updatePartition == nil:
      error("SatelliteOTA", "Failed to find available OTA update partition!")
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    var httpConfig: esp_http_client_config_t
    httpConfig.url = urlCStr
    httpConfig.timeout_ms = 30000
    httpConfig.keep_alive_enable = true
    httpConfig.buffer_size = 4096
    httpConfig.buffer_size_tx = 1024
    httpConfig.crt_bundle_attach = cast[pointer](esp_crt_bundle_attach)
    httpConfig.skip_cert_common_name_check = true
    httpConfig.max_redirection_count = 5

    let client = esp_http_client_init(addr httpConfig)
    if client == nil:
      error("SatelliteOTA", "Failed to initialize HTTP client for OTA!")
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    var err = esp_http_client_open(client, 0)
    if err != ESP_OK:
      error("SatelliteOTA", "Failed to open HTTP connection for OTA: " & $err)
      discard esp_http_client_cleanup(client)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    discard esp_http_client_fetch_headers(client)
    let statusCode = esp_http_client_get_status_code(client)
    if statusCode != 200:
      error("SatelliteOTA", "HTTP server returned error status code: " & $statusCode)
      discard esp_http_client_close(client)
      discard esp_http_client_cleanup(client)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    var otaHandle: esp_ota_handle_t = 0
    err = esp_ota_begin(updatePartition, OTA_WITH_SEQUENTIAL_WRITES, addr otaHandle)
    if err != ESP_OK:
      error("SatelliteOTA", "esp_ota_begin failed: " & $err)
      discard esp_http_client_close(client)
      discard esp_http_client_cleanup(client)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    const bufSize = 4096
    var otaWriteData = newSeq[uint8](bufSize)
    var totalBytesWritten = 0
    var writeFailed = false

    while true:
      vTaskDelay(1) # Yield to FreeRTOS scheduler, feed TWDT, service WiFi stack
      let dataRead = esp_http_client_read(client, addr otaWriteData[0], cint(bufSize))
      if dataRead < 0:
        error("SatelliteOTA", "Error reading HTTP stream during OTA: " & $dataRead)
        writeFailed = true
        break
      elif dataRead > 0:
        err = esp_ota_write(otaHandle, addr otaWriteData[0], csize_t(dataRead))
        if err != ESP_OK:
          error("SatelliteOTA", "esp_ota_write failed: " & $err)
          writeFailed = true
          break
        totalBytesWritten += dataRead
      else:
        if esp_http_client_is_complete_data_received(client):
          break
        break

    discard esp_http_client_close(client)
    discard esp_http_client_cleanup(client)

    if writeFailed or totalBytesWritten < 1000:
      error("SatelliteOTA", "OTA failed or received incomplete binary (" & $totalBytesWritten & " bytes)")
      discard esp_ota_abort(otaHandle)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    info("SatelliteOTA", "Total binary written: " & $totalBytesWritten & " bytes. Finalizing OTA...")

    err = esp_ota_end(otaHandle)
    if err != ESP_OK:
      error("SatelliteOTA", "esp_ota_end failed: " & $err)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    err = esp_ota_set_boot_partition(updatePartition)
    if err != ESP_OK:
      error("SatelliteOTA", "esp_ota_set_boot_partition failed: " & $err)
      nim_satellite_resume_inference()
      nim_satellite_ota_end(false)
      return false

    info("SatelliteOTA", "Firmware OTA update successful! Rebooting in 1000ms...")
    nim_satellite_ota_end(true)
    delayMs(1000)
    reboot()
    return true
  else:
    # Host simulated path for testing
    info("SatelliteOTA", "Host simulated OTA flash successful for " & url)
    nim_satellite_ota_end(true)
    return true
