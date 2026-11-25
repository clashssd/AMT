"""Local Vosk STT module for AMT Chat voice control.

Provides:
  - normalize(): transcript/wake-word string normalization
  - lev(): capped Levenshtein distance
  - wake_word_match(): fuzzy wake-word detection in transcript
  - load_vosk_model(): lazy-loaded Vosk Model (user path → auto-downloaded default)
  - transcribe_local(): batch STT via Vosk (audio_b64 → text)
  - ensure_model_downloaded(): auto-download Vosk model on first run
  - create_wake_word_recognizer(): factory for the WebSocket streaming handler
"""

import base64
import io
import json
import os
import re
import struct
import threading
import urllib.request
import zipfile
from typing import Optional

try:
    from vosk import KaldiRecognizer, Model
except ImportError:
    KaldiRecognizer = None
    Model = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VOSK_PATH = os.path.join(os.path.dirname(__file__), "models", "vosk-model-small-ru")
VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"

# Module-level caches
_model = None
_download_progress: dict = {}
_download_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pure functions (testable without Vosk)
# ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    """Lower, ё→е, strip non-alphanumeric (except spaces), collapse whitespace."""
    s = s.lower()
    s = s.replace("ё", "е")
    s = re.sub(r"[^a-zа-я\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def lev(a: str, b: str, threshold: int = 2) -> int:
    """Capped Levenshtein distance. Returns threshold+1 if actual > threshold."""
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = ca != cb
            val = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            curr.append(val)
            row_min = min(row_min, val)
        if row_min > threshold:
            return threshold + 1
        prev = curr
    return prev[-1] if prev[-1] <= threshold else threshold + 1


def wake_word_match(
    transcript_norm: str,
    target_norm: str,
    aliases: list,
    threshold: int = 2,
) -> bool:
    """Check if the last 5 words of a normalized transcript match the wake word.

    Fast path: exact alias substring in last 5 words.
    Fuzzy path: Levenshtein distance <= threshold on individual last-5 words.
    """
    words = transcript_norm.split()
    if not words:
        return False
    last_5 = " ".join(words[-5:])
    candidates = aliases + [target_norm]

    # Fast path: exact alias match in the last-5-word window
    for alias in candidates:
        if alias and alias in last_5:
            return True

    # Fuzzy: per-word Levenshtein on last 5 words
    for word in words[-5:]:
        for alias in candidates:
            if alias and lev(word, alias, threshold) <= threshold:
                return True
    return False


# ---------------------------------------------------------------------------
# Vosk model loading
# ---------------------------------------------------------------------------

def load_vosk_model(model_path: Optional[str] = None):
    """Load a Vosk Model, preferring user-specified path over auto-downloaded default.

    Raises FileNotFoundError if no valid model directory exists.
    Caches in module-level _model to avoid re-loading.
    """
    global _model
    if _model is not None:
        return _model

    if KaldiRecognizer is None:
        raise ImportError("vosk package is not installed")

    path = model_path or DEFAULT_VOSK_PATH
    if not os.path.isdir(path):
        path = DEFAULT_VOSK_PATH
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Vosk model not found at: {path}")

    _model = Model(path)
    return _model


def create_wake_word_recognizer(model_path: Optional[str] = None):
    """Create a KaldiRecognizer at 16 kHz for the wake-word WebSocket handler."""
    model = load_vosk_model(model_path)
    return KaldiRecognizer(model, 16000)


# ---------------------------------------------------------------------------
# Batch STT
# ---------------------------------------------------------------------------

def transcribe_local(audio_b64: str, mime: str, model_path: Optional[str] = None) -> dict:
    """Transcribe base64-encoded audio using local Vosk.

    Returns {"ok": True, "text": str} on success,
    or {"ok": False, "error": "model_not_found", "fallback": "cloud"} on missing model.
    """
    try:
        model = load_vosk_model(model_path)
    except (FileNotFoundError, ImportError):
        return {"ok": False, "error": "model_not_found", "fallback": "cloud"}

    if KaldiRecognizer is None:
        return {"ok": False, "error": "vosk_not_installed", "fallback": "cloud"}

    rec = KaldiRecognizer(model, 16000)
    raw = base64.b64decode(audio_b64)

    # If the payload is a WAV file, extract the PCM data; otherwise feed raw bytes
    pcm = _extract_pcm(raw, mime)
    rec.AcceptWaveform(pcm)
    text = json.loads(rec.FinalResult())["text"]
    return {"ok": True, "text": text}


def _extract_pcm(data: bytes, mime: str) -> bytes:
    """Extract raw 16 kHz mono Int16 PCM from WAV bytes."""
    # WAV header: 44 bytes standard; skip to 'data' chunk
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        # Find 'data' chunk
        pos = 12
        while pos < len(data) - 4:
            chunk_id = data[pos:pos + 4]
            chunk_size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            if chunk_id == b"data":
                return data[pos + 8:pos + 8 + chunk_size]
            pos += 8 + chunk_size
        # Fallback: skip standard 44-byte header
        return data[44:] if len(data) > 44 else data
    return data


# ---------------------------------------------------------------------------
# Model auto-download
# ---------------------------------------------------------------------------

def ensure_model_downloaded() -> dict:
    """Ensure the default Vosk model exists; download on first run.

    Returns {"modelReady": bool, "modelProgress": float, "error": str | None}.
    """
    if os.path.isdir(DEFAULT_VOSK_PATH):
        return {"modelReady": True, "modelProgress": 1.0, "error": None}

    global _download_progress
    _download_progress = {"progress": 0.0, "downloading": True}

    zip_path = DEFAULT_VOSK_PATH + ".zip"
    try:
        _download_progress["progress"] = 0.1
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path)
        _download_progress["progress"] = 0.9

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(os.path.dirname(DEFAULT_VOSK_PATH))
        os.remove(zip_path)
        _download_progress["progress"] = 1.0
        _download_progress["downloading"] = False
        return {"modelReady": True, "modelProgress": 1.0, "error": None}

    except Exception as e:
        _download_progress["downloading"] = False
        _download_progress["error"] = str(e)
        return {"modelReady": False, "modelProgress": _download_progress.get("progress", 0.0), "error": "download_failed"}

    finally:
        # Clean up partial zip on failure
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass


def get_download_progress() -> float:
    """Return the current download progress (0.0–1.0) for UI polling."""
    return _download_progress.get("progress", 0.0)
