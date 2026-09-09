#!/usr/bin/env python3
"""
Unit test suite for scripts/generate_wakeword_corpus.py.
Validates phonetic variations, multipart encoding, household voice ingestion,
additive multi-voice sampling, and backend resilience.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_wakeword_corpus import (
    generate_nabu_variations,
    generate_clemens_variations,
    encode_multipart_formdata,
    load_household_voices,
    normalize_transcript,
    clean_path,
    sample_voices,
    HouseholdVoice,
    VoiceSpec,
    F5TTSBackend,
    ELEVENLABS_VOICES,
)


class TestWakewordCorpus(unittest.TestCase):

    def test_nabu_variations(self):
        variations = generate_nabu_variations()
        self.assertIsInstance(variations, list)
        self.assertGreaterEqual(len(variations), 10)
        self.assertIn("okay nabu", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_clemens_variations(self):
        variations = generate_clemens_variations()
        self.assertIsInstance(variations, list)
        self.assertGreaterEqual(len(variations), 30)
        self.assertIn("mister clemens", variations)
        self.assertIn("miss tack lemons", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_encode_multipart_formdata(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x24\x00\x00\x00WAVEfmt ")
            temp_path = Path(f.name)

        try:
            fields = {"name": "Test Voice", "description": "Profile sample"}
            files = [("files", temp_path)]
            body, content_type = encode_multipart_formdata(fields, files)

            self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
            boundary = content_type.split("boundary=")[1]
            body_str = body.decode("latin1")

            self.assertIn(boundary, body_str)
            self.assertIn('name="name"', body_str)
            self.assertIn("Test Voice", body_str)
            self.assertIn('name="files"', body_str)
            self.assertIn(temp_path.name, body_str)
            self.assertIn("audio/wav", body_str)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_load_household_voices_single(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x24\x00\x00\x00WAVE")
            temp_path = Path(f.name)

        try:
            voices = load_household_voices(
                single_sample=temp_path,
                single_name="Alice",
                single_transcript="Testing voice sample"
            )
            self.assertEqual(len(voices), 1)
            self.assertEqual(voices[0].name, "Alice")
            self.assertEqual(voices[0].audio_path, temp_path)
            self.assertEqual(voices[0].transcript, "Testing voice sample")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_clean_path(self):
        self.assertIsNone(clean_path(None))
        self.assertIsNone(clean_path(""))
        self.assertIsNone(clean_path("   "))
        self.assertEqual(clean_path("~/sample.wav"), Path.home() / "sample.wav")
        self.assertEqual(clean_path("'~/sample.wav'"), Path.home() / "sample.wav")
        self.assertEqual(clean_path('"~/sample.wav"'), Path.home() / "sample.wav")
        self.assertEqual(clean_path("/path/to/my\\ audio.wav"), Path("/path/to/my audio.wav"))

    def test_normalize_transcript(self):
        self.assertEqual(normalize_transcript(""), "")
        self.assertEqual(normalize_transcript("   hello   world   "), "hello world")
        self.assertEqual(normalize_transcript("Line 1\nLine 2\r\n\tLine 3"), "Line 1 Line 2 Line 3")

    def test_load_household_voices_multiple_samples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            wav1 = tmppath / "partner.wav"
            wav1.write_bytes(b"RIFF\x24\x00\x00\x00WAVE")
            txt1 = tmppath / "partner.txt"
            txt1.write_text("Partner speaking reference", encoding="utf-8")

            wav2 = tmppath / "self.wav"
            wav2.write_bytes(b"RIFF\x24\x00\x00\x00WAVE")
            txt2 = tmppath / "self.txt"
            txt2.write_text("Self speaking reference", encoding="utf-8")

            voices = load_household_voices(
                single_sample=[wav1, str(wav2)],
                single_name=["Partner", "Self"]
            )
            self.assertEqual(len(voices), 2)
            self.assertEqual(voices[0].name, "Partner")
            self.assertEqual(voices[0].transcript, "Partner speaking reference")
            self.assertEqual(voices[1].name, "Self")
            self.assertEqual(voices[1].transcript, "Self speaking reference")

    def test_load_household_voices_companion_txt_single(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            wav_file = tmppath / "charlie.wav"
            wav_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVE")
            txt_file = tmppath / "charlie.txt"
            txt_file.write_text("Spoken sentence in companion file\nwith extra newlines.\n", encoding="utf-8")

            voices = load_household_voices(single_sample=wav_file)
            self.assertEqual(len(voices), 1)
            self.assertEqual(voices[0].name, "Charlie")
            self.assertEqual(voices[0].transcript, "Spoken sentence in companion file with extra newlines.")

    def test_load_household_voices_transcript_file_arg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            wav_file = tmppath / "sample.wav"
            wav_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVE")
            txt_file = tmppath / "custom_trans.txt"
            txt_file.write_text("Custom transcript from external file\nacross multiple lines", encoding="utf-8")

            voices = load_household_voices(
                single_sample=wav_file,
                single_transcript_file=txt_file
            )
            self.assertEqual(len(voices), 1)
            self.assertEqual(voices[0].transcript, "Custom transcript from external file across multiple lines")

    def test_load_household_voices_transcript_filepath_in_string_arg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            wav_file = tmppath / "sample.wav"
            wav_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVE")
            txt_file = tmppath / "referenced_trans.txt"
            txt_file.write_text("Referenced path in string\nline 2", encoding="utf-8")

            voices = load_household_voices(
                single_sample=wav_file,
                single_transcript=str(txt_file)
            )
            self.assertEqual(len(voices), 1)
            self.assertEqual(voices[0].transcript, "Referenced path in string line 2")

    def test_load_household_voices_multiline_string_normalized(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF\x24\x00\x00\x00WAVE")
            temp_path = Path(f.name)

        try:
            voices = load_household_voices(
                single_sample=temp_path,
                single_transcript="Pasted paragraph 1.\n\nPasted paragraph 2 with   spaces."
            )
            self.assertEqual(len(voices), 1)
            self.assertEqual(voices[0].transcript, "Pasted paragraph 1. Pasted paragraph 2 with spaces.")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_load_household_voices_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Subdirectory member
            alice_dir = tmppath / "alice"
            alice_dir.mkdir()
            (alice_dir / "sample.wav").write_bytes(b"RIFF")
            (alice_dir / "transcript.txt").write_text("Hello world", encoding="utf-8")

            # Flat file member
            bob_wav = tmppath / "bob_smith.wav"
            bob_wav.write_bytes(b"RIFF")
            bob_txt = tmppath / "bob_smith.txt"
            bob_txt.write_text("Testing 1 2 3", encoding="utf-8")

            voices = load_household_voices(household_dir=tmppath)
            self.assertEqual(len(voices), 2)

            names = {v.name: v for v in voices}
            self.assertIn("Alice", names)
            self.assertEqual(names["Alice"].transcript, "Hello world")
            self.assertIn("Bob Smith", names)
            self.assertEqual(names["Bob Smith"].transcript, "Testing 1 2 3")

    def test_sample_voices_pure_generic(self):
        dist = {"female": 0.50, "male": 0.50}
        pool = {
            "female": [{"id": "f1", "name": "Female 1"}],
            "male": [{"id": "m1", "name": "Male 1"}],
        }
        specs = sample_voices(dist, 20, pool, household_voices=None, household_ratio=0.50)
        self.assertEqual(len(specs), 20)
        self.assertTrue(all(s.category in ("female", "male") for s in specs))

    def test_sample_voices_additive_household_composition(self):
        dist = {"female": 0.50, "male": 0.50}
        pool = {
            "female": [{"id": "f1", "name": "Female 1"}],
            "male": [{"id": "m1", "name": "Male 1"}],
        }
        h_voices = [
            HouseholdVoice(name="Partner", audio_path=Path("/tmp/p.wav"), voice_id="custom_p"),
            HouseholdVoice(name="Self", audio_path=Path("/tmp/s.wav"), voice_id="custom_s"),
        ]

        total = 100
        ratio = 0.40  # 40% household, 60% generic
        specs = sample_voices(dist, total, pool, household_voices=h_voices, household_ratio=ratio)
        self.assertEqual(len(specs), total)

        household_specs = [s for s in specs if s.category == "household"]
        generic_specs = [s for s in specs if s.category in ("female", "male")]

        self.assertEqual(len(household_specs), 40)
        self.assertEqual(len(generic_specs), 60)

        # Check distribution among household members
        partner_count = sum(1 for s in household_specs if s.voice_name == "Partner")
        self_count = sum(1 for s in household_specs if s.voice_name == "Self")
        self.assertEqual(partner_count, 20)
        self.assertEqual(self_count, 20)

    def test_sample_voices_full_household(self):
        h_voices = [HouseholdVoice(name="User", audio_path=Path("/tmp/u.wav"), voice_id="vid_1")]
        specs = sample_voices({}, 15, {}, household_voices=h_voices, household_ratio=1.0)
        self.assertEqual(len(specs), 15)
        self.assertTrue(all(s.category == "household" and s.voice_name == "User" for s in specs))

    def test_f5_tts_backend_missing_reference(self):
        backend = F5TTSBackend()
        missing_path = Path("/nonexistent/voice/sample.wav")
        out_path = Path("/tmp/f5_out.wav")
        res = backend.synthesize("test", missing_path, "ref text", out_path)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
