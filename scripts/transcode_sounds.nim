## Transcodes, compresses, and normalizes all satellite audio assets using the audio processing pipeline.
import std/[os, osproc]

let rootDir = currentSourcePath().parentDir().parentDir()
let pyScript = rootDir / "scripts" / "process_audio.py"

echo "Executing audio pipeline via scripts/process_audio.py..."
let res = execCmd("python3 " & quoteShell(pyScript))
if res != 0:
  quit("Audio processing failed with exit code " & $res, res)

echo "Audio processing complete."
