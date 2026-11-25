"""Tests for backend/stt_local.py — pure functions only (no real Vosk model needed)."""

import sys
import os
import json
import base64
import struct
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import stt_local


# ── normalize ───────────────────────────────────────────────────────────────

def test_normalize_lowercase_and_e():
    assert stt_local.normalize('ЁЖИК') == 'ежик'

def test_normalize_strips_punctuation():
    assert stt_local.normalize('привет, мир!') == 'привет мир'

def test_normalize_collapse_whitespace():
    assert stt_local.normalize('  привет   мир  ') == 'привет мир'


# ── wake_word_match ─────────────────────────────────────────────────────────

def test_wake_word_match_exact():
    # "а стра" contains alias "астра" — but we test exact alias in last 5 words
    # target_norm="астр", aliases=["астр"]
    # transcript "а стра" normalized → "а стра", last 5 words = "а стра"
    # alias "астр" is not a substring of "а стра" → fuzzy path
    # lev("стра", "астр", 2) = 2 → match
    assert stt_local.wake_word_match("а стра", "астр", ["астр"], 2) is True

def test_wake_word_match_alias_exact():
    # transcript "астр" with target "астр" → exact match
    assert stt_local.wake_word_match("астр", "астр", [], 2) is True

def test_wake_word_match_fuzzy():
    # "остра" vs target "астр" → lev("остра", "астр") = 2 (delete 'о', swap) → match
    assert stt_local.wake_word_match("остра", "астр", ["астр"], 2) is True

def test_wake_word_match_no_match():
    # "погода" has nothing close to "астр"
    assert stt_local.wake_word_match("погода", "астр", ["астр"], 2) is False

def test_wake_word_match_empty_transcript():
    assert stt_local.wake_word_match("", "астр", ["астр"], 2) is False


# ── lev ──────────────────────────────────────────────────────────────────────

def test_lev_capped():
    # "abc" vs "xyz" — all 3 differ, distance = 3, threshold = 2 → capped at 3
    assert stt_local.lev("abc", "xyz", 2) == 3

def test_lev_within_threshold():
    # "астр" vs "астро" — insert one char, distance = 1
    assert stt_local.lev("астр", "астро", 2) == 1

def test_lev_zero():
    assert stt_local.lev("abc", "abc", 2) == 0


# ── transcribe_local (mocked) ───────────────────────────────────────────────

def test_transcribe_local_returns_fallback_on_missing_model():
    with patch.object(stt_local, 'load_vosk_model', side_effect=FileNotFoundError("no model")):
        result = stt_local.transcribe_local("aW52YWxpZA==", "audio/wav", "/nonexistent/")
        assert result["ok"] is False
        assert result["error"] == "model_not_found"
        assert result.get("fallback") == "cloud"


def test_transcribe_local_returns_fallback_on_import_error():
    with patch.object(stt_local, 'load_vosk_model', side_effect=ImportError("vosk not installed")):
        result = stt_local.transcribe_local("aW52YWxpZA==", "audio/wav", None)
        assert result["ok"] is False
        assert result["error"] == "model_not_found"


# ── ensure_model_downloaded (mocked) ────────────────────────────────────────

def test_ensure_model_downloaded_model_ready():
    with patch('os.path.isdir', return_value=True):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(stt_local.ensure_model_downloaded())
        finally:
            loop.close()
        assert result["modelReady"] is True
        assert result["modelProgress"] == 1.0
        assert result["error"] is None


# ── _extract_pcm ────────────────────────────────────────────────────────────

def test_extract_pcm_wav():
    """Build a minimal WAV file and verify PCM extraction."""
    # WAV header: RIFF + WAVE + fmt chunk + data chunk
    pcm_data = struct.pack("<hh", 100, -200)  # two Int16 samples
    data_chunk_size = len(pcm_data)
    fmt_chunk = struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)  # fmt
    fmt_size = len(fmt_chunk)

    header = (
        b"RIFF" + struct.pack("<I", 36 + data_chunk_size) + b"WAVE"
        + b"fmt " + struct.pack("<I", fmt_size) + fmt_chunk
        + b"data" + struct.pack("<I", data_chunk_size)
    )
    wav = header + pcm_data
    extracted = stt_local._extract_pcm(wav, "audio/wav")
    assert extracted == pcm_data

def test_extract_pcm_non_wav_passthrough():
    raw = b"\x00\x01\x02\x03"
    assert stt_local._extract_pcm(raw, "audio/webm") == raw
