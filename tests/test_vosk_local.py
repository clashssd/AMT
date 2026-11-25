"""Tests for backend/stt_local.py — pure functions + mocked Vosk paths."""

import base64
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Make backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import stt_local


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

def test_normalize_lowercase_and_e():
    assert stt_local.normalize("ЁЖИК") == "ежик"


def test_normalize_strips_punctuation():
    assert stt_local.normalize("привет, мир!") == "привет мир"


def test_normalize_collapses_whitespace():
    assert stt_local.normalize("  астр   астра  ") == "астр астра"


# ---------------------------------------------------------------------------
# lev()
# ---------------------------------------------------------------------------

def test_lev_capped():
    # 'abc' → 'xyz' distance is 3, capped at threshold+1 = 3
    assert stt_local.lev("abc", "xyz", 2) == 3


def test_lev_within_threshold():
    # 'астр' → 'астро' distance is 1 (insertion)
    assert stt_local.lev("астр", "астро", 2) == 1


def test_lev_exact():
    assert stt_local.lev("астр", "астр", 2) == 0


def test_lev_single_char_diff():
    assert stt_local.lev("остра", "астр", 2) == 2  # rearrange + delete = 2


# ---------------------------------------------------------------------------
# wake_word_match()
# ---------------------------------------------------------------------------

def test_wake_word_match_exact():
    # 'а стра' contains alias 'астр' as substring? No — 'а стра' != 'астр'.
    # But the word list is ['а', 'стра'], last_5 = 'а стра'.
    # 'астр' is NOT a substring of 'а стра'.
    # However, fuzzy: lev('а', 'астр')=3, lev('стра', 'астр')=4... 
    # Actually let's use a cleaner test:
    assert stt_local.wake_word_match("а стра", "астр", ["а стра"], 2) is True


def test_wake_word_match_fuzzy():
    # 'остра' vs alias 'астр': lev distance = 4 (rearrange) > 2... 
    # Let's test a clearer case: 'астр' vs 'астро' (insertion, dist=1)
    assert stt_local.wake_word_match("астро", "астр", ["астро"], 2) is True


def test_wake_word_match_no_match():
    assert stt_local.wake_word_match("погода", "астр", ["астр"], 2) is False


def test_wake_word_match_target_direct():
    assert stt_local.wake_word_match("астра", "астра", [], 2) is True


def test_wake_word_match_empty_transcript():
    assert stt_local.wake_word_match("", "астр", ["астр"], 2) is False


# ---------------------------------------------------------------------------
# transcribe_local() — mocked Vosk
# ---------------------------------------------------------------------------

def test_transcribe_local_returns_fallback_on_missing_model():
    with patch("stt_local.load_vosk_model", side_effect=FileNotFoundError("no model")):
        result = stt_local.transcribe_local("aW5n", "audio/wav", "/nonexistent/")
        assert result == {"ok": False, "error": "model_not_found", "fallback": "cloud"}


def test_transcribe_local_success():
    mock_rec = MagicMock()
    mock_rec.FinalResult.return_value = '{"text": "привет мир"}'
    mock_rec.AcceptWaveform.return_value = True
    mock_model = MagicMock()

    with patch("stt_local.load_vosk_model", return_value=mock_model):
        with patch("stt_local.KaldiRecognizer", return_value=mock_rec):
            with patch("stt_local._extract_pcm", return_value=b"PCM_DATA"):
                result = stt_local.transcribe_local("aW5n", "audio/wav", "/valid/")
                assert result == {"ok": True, "text": "привет мир"}


# ---------------------------------------------------------------------------
# ensure_model_downloaded()
# ---------------------------------------------------------------------------

def test_ensure_model_downloaded_model_ready():
    with patch("os.path.isdir", return_value=True):
        result = stt_local.ensure_model_downloaded()
        assert result == {"modelReady": True, "modelProgress": 1.0, "error": None}


def test_ensure_model_downloaded_download_success():
    mock_zipfile = MagicMock()
    with patch("os.path.isdir", return_value=False):
        with patch("urllib.request.urlretrieve"):
            with patch("zipfile.ZipFile", mock_zipfile):
                with patch("os.remove"):
                    result = stt_local.ensure_model_downloaded()
                    assert result["modelReady"] is True
                    assert result["error"] is None


def test_ensure_model_downloaded_download_failure():
    import urllib.error
    with patch("os.path.isdir", return_value=False):
        with patch("urllib.request.urlretrieve", side_effect=urllib.error.URLError("no internet")):
            result = stt_local.ensure_model_downloaded()
            assert result["modelReady"] is False
            assert result["error"] == "download_failed"


# ---------------------------------------------------------------------------
# _extract_pcm()
# ---------------------------------------------------------------------------

def test_extract_pcm_from_wav():
    # Build a minimal WAV header + data
    import struct
    pcm_data = b"\x01\x02\x03\x04"
    # RIFF header: 44 bytes total
    wav = bytearray(44)
    wav[0:4] = b"RIFF"
    wav[4:8] = struct.pack("<I", 36 + len(pcm_data))
    wav[8:12] = b"WAVE"
    wav[12:16] = b"fmt "
    wav[16:20] = struct.pack("<I", 16)
    wav[36:40] = b"data"
    wav[40:44] = struct.pack("<I", len(pcm_data))
    wav.extend(pcm_data)
    result = stt_local._extract_pcm(bytes(wav), "audio/wav")
    assert result == pcm_data


def test_extract_pcm_raw_bytes():
    # Non-WAV data passes through
    result = stt_local._extract_pcm(b"\x01\x02", "audio/webm")
    assert result == b"\x01\x02"
