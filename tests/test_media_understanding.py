"""Tests for media_understanding (audio STT + video keyframes pipeline).

These tests cover the pure-logic parts (markdown builder, size limits,
fallback formatting) without needing ffmpeg or a real STT endpoint.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

# Make backend modules importable.
BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

mu = importlib.import_module("media_understanding")

# Cyrillic literals (Unicode-escaped to survive any console-encoding round-trip).
PRIVET_MIR = "\u043f\u0440\u0438\u0432\u0435\u0442 \u043c\u0438\u0442"
TRANSCRIPT_LABEL = "\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442 \u0430\u0443\u0434\u0438\u043e"
SLISHKOM_BOLSHOI = "\u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0431\u043e\u043b\u044c\u0448\u0435\u0439"


def test_audio_md_empty_transcript():
    out = mu._audio_md("a.mp3", "")
    assert "a.mp3" in out
    assert "not available" in out


def test_audio_md_with_transcript():
    out = mu._audio_md("a.mp3", PRIVET_MIR)
    assert PRIVET_MIR in out
    assert TRANSCRIPT_LABEL in out


def test_audio_md_stt_error_verbatim():
    out = mu._audio_md("a.mp3", "[STT ERROR: no provider]")
    assert "STT ERROR" in out
    assert "a.mp3" in out


def test_video_md_only_keyframes():
    out = mu._video_md("v.mp4", [b"jpeg1"], "")
    assert "v.mp4" in out
    assert "frame_1" in out


def test_video_md_only_transcript():
    out = mu._video_md("v.mp4", [], "hello")
    assert "hello" in out


def test_video_md_both():
    out = mu._video_md("v.mp4", [b"f1", b"f2"], PRIVET_MIR)
    assert PRIVET_MIR in out
    assert "frame_1" in out
    assert "frame_2" in out


def test_video_md_nothing_extracted():
    out = mu._video_md("v.mp4", [], "")
    assert out  # non-empty placeholder


def test_video_md_stt_error_in_transcript():
    out = mu._video_md("v.mp4", [b"f1"], "[STT ERROR: no provider]")
    assert "STT ERROR" in out


def test_understand_media_size_limits_audio():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        f.write(b"\x00" * (mu.AUDIO_MAX + 1))
        path = f.name
    try:
        out = mu.understand_media(path, "audio/mpeg")
        assert "(>50MB)" in out
    finally:
        os.unlink(path)


def test_understand_media_size_limits_video():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
        f.write(b"\x00" * (mu.VIDEO_MAX + 1))
        path = f.name
    try:
        out = mu.understand_media(path, "video/mp4")
        assert "(>200MB)" in out
    finally:
        os.unlink(path)


def test_understand_media_unknown_mime_returns_placeholder():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(b"x")
        path = f.name
    try:
        out = mu.understand_media(path, "application/octet-stream")
        assert out  # placeholder, non-empty
    finally:
        os.unlink(path)


def test_find_ffmpeg_returns_none_when_not_installed(monkeypatch):
    import media_understanding as m
    m._ffmpeg_checked = False
    m._ffmpeg_path = None
    monkeypatch.setattr(m, "_ffmpeg_dir", lambda: "/nonexistent/amt_data/ffmpeg")
    monkeypatch.setattr(m, "_download_ffmpeg", lambda: None)
    monkeypatch.setattr(m.shutil, "which", lambda name: None)
    assert m._find_ffmpeg() is None
