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
    BUILTIN_WAKE_WORDS,
    generate_clemens_variations,
    generate_bumblebee_variations,
    generate_gizmo_variations,
    generate_chief_variations,
    generate_captain_variations,
    generate_computer_variations,
    generate_wizard_variations,
    encode_multipart_formdata,
    load_household_voices,
    normalize_transcript,
    clean_path,
    sample_voices,
    HouseholdVoice,
    VoiceSpec,
    F5TTSBackend,
    ELEVENLABS_VOICES,
    VoiceCacheManager,
    compute_file_hash,
    get_pipeline_signature,
    get_sample_cache_key,
    is_corpus_complete,
    get_available_builtin_voices,
    parse_variations,
    edit_phrases_in_editor,
    remove_phrases_interactive,
    add_phrases_interactive,
    display_variations_table,
    review_phrases_fallback,
    generate_llm_prompt,
    copy_to_clipboard,
    show_llm_prompt_panel,
    PIPELINE_VERSION,
    AUDIO_PIPELINE_PARAMS,
)
from unittest.mock import patch, MagicMock

try:
    import questionary
    HAVE_QUESTIONARY = True
except ImportError:
    HAVE_QUESTIONARY = False


class TestWakewordCorpus(unittest.TestCase):

    def test_bumblebee_variations(self):
        variations = generate_bumblebee_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 29)
        self.assertIn("bumblebee", variations)
        self.assertIn("hey bumblebee", variations)
        self.assertIn("bummbell bee", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_gizmo_variations(self):
        variations = generate_gizmo_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 30)
        self.assertIn("hey gizmo", variations)
        self.assertIn("gizmo", variations)
        self.assertIn("hey gismoe", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_chief_variations(self):
        variations = generate_chief_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 31)
        self.assertIn("hey chief", variations)
        self.assertIn("chief", variations)
        self.assertIn("hey cheeve", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_captain_variations(self):
        variations = generate_captain_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 32)
        self.assertIn("oh captain", variations)
        self.assertIn("captain", variations)
        self.assertIn("oh cap den", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_computer_variations(self):
        variations = generate_computer_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 34)
        self.assertIn("ok computer", variations)
        self.assertIn("okay computer", variations)
        self.assertIn("ok computr", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_wizard_variations(self):
        variations = generate_wizard_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 35)
        self.assertIn("little wizard", variations)
        self.assertIn("hey little wizard", variations)
        self.assertIn("lit uhl wizz urd", variations)
        self.assertEqual(len(variations), len(set(variations)))

    def test_builtin_wake_words_registry(self):
        expected_keys = [
            "mister_clemens",
            "bumblebee",
            "hey_gizmo",
            "hey_chief",
            "oh_captain",
            "ok_computer",
            "little_wizard",
        ]
        self.assertEqual(list(BUILTIN_WAKE_WORDS.keys()), expected_keys)
        for key in expected_keys:
            entry = BUILTIN_WAKE_WORDS[key]
            self.assertIn("name", entry)
            self.assertIn("description", entry)
            self.assertTrue(callable(entry["generator"]))
            variations = entry["generator"]()
            self.assertIsInstance(variations, list)
            self.assertGreaterEqual(len(variations), 25)
            self.assertEqual(len(variations), len(set(variations)))

    def test_clemens_variations(self):
        variations = generate_clemens_variations()
        self.assertIsInstance(variations, list)
        self.assertEqual(len(variations), 35)
        self.assertIn("mister clemens", variations)
        self.assertIn("hey mister clemens", variations)
        self.assertIn("missed her clemens", variations)
        self.assertIn("ey mister clemens", variations)
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

    def test_compute_file_hash(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"SAMPLE AUDIO CONTENT FOR HASHING")
            temp_path = Path(f.name)
        try:
            h = compute_file_hash(temp_path)
            self.assertEqual(len(h), 64)
            # Verify deterministic hash
            import hashlib
            expected = hashlib.sha256(b"SAMPLE AUDIO CONTENT FOR HASHING").hexdigest()
            self.assertEqual(h, expected)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_pipeline_signature_determinism(self):
        sig1 = get_pipeline_signature("f5_tts")
        sig2 = get_pipeline_signature("f5_tts")
        sig_eleven = get_pipeline_signature("elevenlabs")
        self.assertEqual(sig1, sig2)
        self.assertNotEqual(sig1, sig_eleven)
        self.assertEqual(len(sig1), 16)

    def test_voice_cache_manager_reentrancy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_voices.json"
            vcm = VoiceCacheManager(cache_file)

            name = "Test Partner"
            audio_hash = "112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00"
            transcript = "This is a reference transcript"

            # Initially uncached
            cached = vcm.get_trained_voice("f5_tts", name, audio_hash, transcript)
            self.assertIsNone(cached)

            # Register trained voice model
            vcm.register_trained_voice("f5_tts", name, audio_hash, transcript, "voice_model_id_123")

            # Reload manager from disk to verify persistence
            vcm2 = VoiceCacheManager(cache_file)
            cached2 = vcm2.get_trained_voice("f5_tts", name, audio_hash, transcript)
            self.assertIsNotNone(cached2)
            self.assertEqual(cached2["voice_id"], "voice_model_id_123")
            self.assertEqual(cached2["audio_hash"], audio_hash)
            self.assertEqual(cached2["transcript"], transcript)

            # Different audio hash (modified training data) must miss cache
            modified_hash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
            miss_hash = vcm2.get_trained_voice("f5_tts", name, modified_hash, transcript)
            self.assertIsNone(miss_hash)

            # Different transcript must miss cache
            miss_trans = vcm2.get_trained_voice("f5_tts", name, audio_hash, "Changed transcript")
            self.assertIsNone(miss_trans)

    def test_get_sample_cache_key_encodes_audio_hash_and_transcript(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"AUDIO CONTENT 1")
            path1 = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"AUDIO CONTENT 2")
            path2 = Path(f.name)

        try:
            hv1 = HouseholdVoice(name="User", audio_path=path1, transcript="Hello world")
            vspec1 = VoiceSpec(voice_id="user", voice_name="User", household=hv1)

            hv2 = HouseholdVoice(name="User", audio_path=path2, transcript="Hello world")
            vspec2 = VoiceSpec(voice_id="user", voice_name="User", household=hv2)

            hv3 = HouseholdVoice(name="User", audio_path=path1, transcript="Different text")
            vspec3 = VoiceSpec(voice_id="user", voice_name="User", household=hv3)

            key1_a = get_sample_cache_key("f5_tts", vspec1, "mister clemens")
            key1_b = get_sample_cache_key("f5_tts", vspec1, "mister clemens")
            key2 = get_sample_cache_key("f5_tts", vspec2, "mister clemens")
            key3 = get_sample_cache_key("f5_tts", vspec3, "mister clemens")

            # Deterministic for identical parameters
            self.assertEqual(key1_a, key1_b)
            # Different training data hash must produce different cache key
            self.assertNotEqual(key1_a, key2)
            # Different transcript must produce different cache key
            self.assertNotEqual(key1_a, key3)
        finally:
            if path1.exists():
                path1.unlink()
            if path2.exists():
                path2.unlink()

    def test_is_corpus_complete_validation(self):
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            sample_file = out_dir / "sample_001.wav"
            sample_file.write_bytes(b"RIFF" + b"\x00" * 50)

            hv = HouseholdVoice(name="Partner", audio_path=Path("/fake.wav"), audio_hash="hash123")
            pipeline_sig = get_pipeline_signature("f5_tts")

            manifest_data = {
                "model": "mister_clemens",
                "backend": "f5_tts",
                "pipeline_version": PIPELINE_VERSION,
                "pipeline_signature": pipeline_sig,
                "total_samples": 1,
                "household_voice_hashes": {"Partner": "hash123"},
                "samples": [{"filename": "sample_001.wav"}]
            }
            (out_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

            # Must be complete
            self.assertTrue(is_corpus_complete(out_dir, 1, "mister_clemens", "f5_tts", [hv]))

            # If voice hash changed (training data modified), must not be considered complete
            hv_modified = HouseholdVoice(name="Partner", audio_path=Path("/fake.wav"), audio_hash="hash999")
            self.assertFalse(is_corpus_complete(out_dir, 1, "mister_clemens", "f5_tts", [hv_modified]))

            # If count expectation is higher, must not be complete
            self.assertFalse(is_corpus_complete(out_dir, 2, "mister_clemens", "f5_tts", [hv]))

    def test_get_available_builtin_voices(self):
        # ElevenLabs built-in voice registry
        el_voices = get_available_builtin_voices("elevenlabs")
        self.assertGreaterEqual(len(el_voices), 15)
        defaults = [v["name"] for v in el_voices if v.get("default")]
        self.assertIn("Rachel", defaults)
        self.assertIn("Adam", defaults)
        self.assertIn("Sarah", defaults)
        self.assertIn("George", defaults)
        self.assertIn("Mimi", defaults)
        self.assertIn("Matilda", defaults)

        # F5-TTS built-in reference voices (manifest-driven)
        f5_voices = get_available_builtin_voices("f5_tts")
        self.assertEqual(len(f5_voices), 12)
        f5_names = [v["name"] for v in f5_voices]
        self.assertIn("Adam", f5_names)
        self.assertIn("Claire", f5_names)
        self.assertIn("David", f5_names)
        self.assertIn("Davy", f5_names)
        self.assertIn("Emma", f5_names)
        self.assertIn("Gigi", f5_names)
        self.assertIn("Jake", f5_names)
        self.assertIn("Joy", f5_names)
        self.assertIn("Lulu Lolipop", f5_names)
        self.assertIn("Pirate", f5_names)
        self.assertIn("River", f5_names)
        self.assertIn("Shelly", f5_names)
        for v in f5_voices:
            self.assertTrue(v["default"])
            self.assertTrue(v["reference_audio"].is_file())
            self.assertTrue(v["reference_transcript"].startswith("Once upon a time"))
            self.assertGreater(len(v["desc"]), 0)
        f5_map = {v["name"]: v["category"] for v in f5_voices}
        self.assertEqual(f5_map["Claire"], "female")
        self.assertEqual(f5_map["Emma"], "female")
        self.assertEqual(f5_map["Gigi"], "female")
        self.assertEqual(f5_map["Joy"], "female")
        self.assertEqual(f5_map["Lulu Lolipop"], "female")
        self.assertEqual(f5_map["River"], "female")
        self.assertEqual(f5_map["Shelly"], "female")
        self.assertEqual(f5_map["Adam"], "male")
        self.assertEqual(f5_map["David"], "male")
        self.assertEqual(f5_map["Davy"], "male")
        self.assertEqual(f5_map["Jake"], "male")
        self.assertEqual(f5_map["Pirate"], "accents")

    def test_sample_voices_selected_builtin_voices(self):
        dist = {"female": 0.50, "male": 0.50}
        h_voices = [HouseholdVoice(name="Lijah", audio_path=Path("/tmp/l.wav"), voice_id="custom_l")]
        builtin_specs = [
            VoiceSpec(voice_id="v_rachel", voice_name="Rachel", category="female"),
            VoiceSpec(voice_id="v_adam", voice_name="Adam", category="male"),
        ]

        # 50% household, 50% built-in
        specs = sample_voices(dist, 10, voice_pool={}, household_voices=h_voices, household_ratio=0.50, selected_builtin_voices=builtin_specs)
        self.assertEqual(len(specs), 10)

        h_count = sum(1 for s in specs if s.category == "household")
        b_count = sum(1 for s in specs if s.category in ("female", "male"))
        self.assertEqual(h_count, 5)
        self.assertEqual(b_count, 5)

        # Generic voices must be exclusively Rachel and Adam
        generic_names = set(s.voice_name for s in specs if s.category != "household")
        self.assertEqual(generic_names, {"Rachel", "Adam"})

    def test_is_corpus_complete_with_builtin_voices(self):
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            (out_dir / "sample_001.wav").write_bytes(b"RIFF" + b"\x00" * 50)

            pipeline_sig = get_pipeline_signature("elevenlabs")
            manifest_data = {
                "model": "mister_clemens",
                "backend": "elevenlabs",
                "pipeline_version": PIPELINE_VERSION,
                "pipeline_signature": pipeline_sig,
                "total_samples": 1,
                "household_voice_hashes": {},
                "builtin_voices": ["Rachel", "Adam"],
                "samples": [{"filename": "sample_001.wav"}]
            }
            (out_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

            # Matches exactly
            self.assertTrue(is_corpus_complete(out_dir, 1, "mister_clemens", "elevenlabs", [], builtin_voices=["Rachel", "Adam"]))
            # Case/order insensitive match
            self.assertTrue(is_corpus_complete(out_dir, 1, "mister_clemens", "elevenlabs", [], builtin_voices=["adam", "rachel"]))
            # Mismatched voices must invalidate cache
            self.assertFalse(is_corpus_complete(out_dir, 1, "mister_clemens", "elevenlabs", [], builtin_voices=["Rachel", "George"]))

    def test_parse_variations(self):
        # Comma-separated
        self.assertEqual(parse_variations("hey computer, ok computer, hay computer"), ["hey computer", "ok computer", "hay computer"])
        # Multi-line
        self.assertEqual(parse_variations("hey computer\nok computer\n\nhay computer\n"), ["hey computer", "ok computer", "hay computer"])
        # Deduping and whitespace normalization
        self.assertEqual(parse_variations("hey  computer, hey computer\nHEY COMPUTER"), ["hey computer"])
        # Empty input
        self.assertEqual(parse_variations(""), [])

    def test_parse_variations_comments(self):
        text = (
            "# Header comment line\n"
            "mister clemens\n"
            "  # Indented comment line\n"
            "hey clemens, # inline is preserved or handled\n"
            "\n"
            "ok clemens\n"
        )
        parsed = parse_variations(text)
        self.assertIn("mister clemens", parsed)
        self.assertIn("hey clemens", parsed)
        self.assertIn("ok clemens", parsed)
        # Ensure pure comment lines are filtered out
        for p in parsed:
            self.assertFalse(p.startswith("#"))

    def test_edit_phrases_in_editor(self):
        orig_env = os.environ.get("EDITOR")
        try:
            # Point EDITOR to a sed command that transforms the phrase
            os.environ["EDITOR"] = "sed -i.bak s/mister/master/g"
            initial = ["mister clemens", "hey clemens"]
            edited = edit_phrases_in_editor(initial)
            self.assertEqual(edited, ["master clemens", "hey clemens"])

            # If editor empties the file, initial phrases must be retained
            os.environ["EDITOR"] = "cp /dev/null"
            retained = edit_phrases_in_editor(initial)
            self.assertEqual(retained, initial)
        finally:
            if orig_env is not None:
                os.environ["EDITOR"] = orig_env
            else:
                os.environ.pop("EDITOR", None)

    @unittest.skipUnless(HAVE_QUESTIONARY, "questionary not installed")
    def test_remove_phrases_interactive(self):
        initial = ["phrase one", "phrase two", "phrase three"]
        with patch("questionary.checkbox") as mock_checkbox:
            # Simulate selecting 'phrase two' to remove
            mock_checkbox.return_value.ask.return_value = ["phrase two"]
            remaining = remove_phrases_interactive(initial)
            self.assertEqual(remaining, ["phrase one", "phrase three"])

            # Simulate selecting ALL phrases (must be rejected to keep at least one)
            mock_checkbox.return_value.ask.return_value = ["phrase one", "phrase two", "phrase three"]
            retained = remove_phrases_interactive(initial)
            self.assertEqual(retained, initial)

            # Simulate cancelling (None)
            mock_checkbox.return_value.ask.return_value = None
            cancelled = remove_phrases_interactive(initial)
            self.assertEqual(cancelled, initial)

    @unittest.skipUnless(HAVE_QUESTIONARY, "questionary not installed")
    def test_add_phrases_interactive(self):
        initial = ["phrase one", "phrase two"]
        with patch("questionary.text") as mock_text:
            # Simulate adding a comma-separated list with one duplicate
            mock_text.return_value.ask.return_value = "phrase three, phrase one, phrase four"
            updated = add_phrases_interactive(initial)
            self.assertEqual(updated, ["phrase one", "phrase two", "phrase three", "phrase four"])

            # Simulate empty input
            mock_text.return_value.ask.return_value = "   "
            unchanged = add_phrases_interactive(initial)
            self.assertEqual(unchanged, initial)

    def test_display_variations_table(self):
        # Must execute cleanly across single, dual, and multi-column groupings
        for count in [1, 5, 20]:
            sample_phrases = [f"variant {i}" for i in range(count)]
            display_variations_table(sample_phrases, "test_model")

    def test_review_phrases_fallback_accept(self):
        initial = ["test variant"]
        with patch("builtins.input", return_value="1"):
            result = review_phrases_fallback(initial, "test_model")
            self.assertEqual(result, initial)

    def test_review_phrases_fallback_add(self):
        initial = ["first variant"]
        # Step 1: choose option 2 (add), Step 2: enter new variant, Step 3: choose option 1 (accept)
        inputs = iter(["2", "second variant, third variant", "1"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = review_phrases_fallback(initial, "test_model")
            self.assertEqual(result, ["first variant", "second variant", "third variant"])

    def test_generate_llm_prompt(self):
        prompt = generate_llm_prompt("hey computer")
        self.assertIn("hey computer", prompt)
        self.assertIn("microWakeWord", prompt)
        self.assertIn("phonetic variations", prompt)
        self.assertIn("comma-separated list", prompt)

    def test_copy_to_clipboard_and_show_panel(self):
        # Test copy_to_clipboard execution without exception
        _ = copy_to_clipboard("test phrase")
        # Test show_llm_prompt_panel renders prompt text
        prompt = show_llm_prompt_panel("hey computer")
        self.assertIn("hey computer", prompt)

    def test_review_phrases_fallback_llm_prompt(self):
        initial = ["base phrase"]
        # Option 3 (LLM prompt), then enter new variation, then Option 1 (accept)
        inputs = iter(["3", "new variant", "1"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = review_phrases_fallback(initial, "test_model")
            self.assertEqual(result, ["base phrase", "new variant"])


if __name__ == "__main__":
    unittest.main()
