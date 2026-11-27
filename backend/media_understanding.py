"""Media understanding: audio transcription + video keyframes for AI chat.

Pipeline:
  audio file  → STT (cloud Whisper → local Vosk fallback) → transcript text
  video file  → ffmpeg extract audio + keyframes → STT + vision → combined markdown

All output is plain-text markdown with base64-embedded images, ready for
injection into the AI user message. The existing call_ai_api() multipart
conversion (data:image/... → image_url parts) handles the vision part.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from typing import Optional

log = logging.getLogger(__name__)

# Size limits (bytes)
AUDIO_MAX = 50 * 1024 * 1024   # 50 MB
VIDEO_MAX = 200 * 1024 * 1024  # 200 MB

# Cached ffmpeg path
_ffmpeg_path: Optional[str] = None
_ffmpeg_checked = False
_ffmpeg_lock = threading.Lock()

# Known static-build URLs (small, no dependencies).
# Windows: gyan.dev essentials zip — the inner folder name has a version
# number that changes, so we walk the tree to find ffmpeg.exe (not a fixed
# relative path).
# Linux: johnvansickle amd64 static tarball.
_FFMPEG_DL_URLS = {
    "windows": {
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "archive": "zip",
    },
    "linux": {
        "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "archive": "tar.xz",
    },
}


def _ffmpeg_dir() -> str:
    base = os.environ.get("AMT_DATA_DIR") or os.path.join(
        os.path.dirname(__file__), "..", ".amt_data"
    )
    d = os.path.join(base, "ffmpeg")
    os.makedirs(d, exist_ok=True)
    return d


def _find_ffmpeg() -> Optional[str]:
    """Return path to ffmpeg binary, or None if not found."""
    global _ffmpeg_path, _ffmpeg_checked
    with _ffmpeg_lock:
        if _ffmpeg_checked:
            return _ffmpeg_path
        _ffmpeg_checked = True

        # 1. Already cached
        if _ffmpeg_path and os.path.isfile(_ffmpeg_path):
            return _ffmpeg_path

        # 2. shutil.which
        found = shutil.which("ffmpeg")
        if found:
            _ffmpeg_path = found
            log.info("ffmpeg found on PATH: %s", found)
            return found

        # 3. AMT_DATA_DIR/ffmpeg — look for ffmpeg directly, then walk the
        # tree (the auto-downloaded build extracts into a versioned folder).
        dl_dir = _ffmpeg_dir()
        candidate = os.path.join(dl_dir, "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
        if os.path.isfile(candidate):
            _ffmpeg_path = candidate
            log.info("ffmpeg found in data dir: %s", candidate)
            return candidate
        for root, _dirs, files in os.walk(dl_dir):
            if "ffmpeg.exe" in files:
                _ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                log.info("ffmpeg found in data dir tree: %s", _ffmpeg_path)
                return _ffmpeg_path
            if "ffmpeg" in files:
                _ffmpeg_path = os.path.join(root, "ffmpeg")
                log.info("ffmpeg found in data dir tree: %s", _ffmpeg_path)
                return _ffmpeg_path

        # 4. Common Windows locations
        if platform.system() == "Windows":
            for p in [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
            ]:
                if os.path.isfile(p):
                    _ffmpeg_path = p
                    log.info("ffmpeg found in common location: %s", p)
                    return p

        # 5. Try auto-download
        _ffmpeg_path = _download_ffmpeg()
        return _ffmpeg_path


def _download_ffmpeg() -> Optional[str]:
    """Download a static ffmpeg build on first use. Returns binary path or None.

    Best-effort: a failed download just disables media understanding, it
    doesn't break the app. We verify the binary actually exists and is
    executable after extraction, and record the archive hash so we don't
    re-download on the next call.
    """
    import urllib.request
    import zipfile
    import tarfile

    system = platform.system().lower()
    if system not in _FFMPEG_DL_URLS:
        log.warning("ffmpeg auto-download not supported on %s", system)
        return None

    info = _FFMPEG_DL_URLS[system]
    url = info["url"]
    archive_kind = info.get("archive", "zip")

    dl_dir = _ffmpeg_dir()
    archive_path = os.path.join(dl_dir, "download.archive")
    hash_path = os.path.join(dl_dir, "download.sha256")
    bin_name = "ffmpeg.exe" if system == "windows" else "ffmpeg"

    # Fast path: binary already present at a known location.
    candidate = os.path.join(dl_dir, bin_name)
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        log.info("ffmpeg already present: %s", candidate)
        _ffmpeg_path = candidate
        return candidate

    # Check if we already downloaded (hash of the archive matches).
    if os.path.isfile(archive_path) and os.path.isfile(hash_path):
        try:
            h = hashlib.sha256()
            with open(archive_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            stored = hash_path and open(hash_path).read().strip()
            if h.hexdigest() == stored:
                log.info("ffmpeg archive cached: %s", archive_path)
                # Fall through to extraction (binary may not have been placed).
            else:
                log.info("ffmpeg archive hash mismatch, re-downloading")
        except OSError:
            pass

    log.info("Downloading ffmpeg from %s …", url)
    try:
        tmp = archive_path + ".part"
        urllib.request.urlretrieve(url, tmp)
        # Record the hash of the fresh download so next call skips the re-fetch.
        h = hashlib.sha256()
        with open(tmp, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        with open(hash_path, "w") as fh:
            fh.write(h.hexdigest())
        os.replace(tmp, archive_path)

        # Extract to dl_dir (the inner folder name carries a version number
        # that changes, so we don't trust a fixed relative path — we walk
        # the tree to find the binary).
        target: Optional[str] = None
        if archive_kind == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dl_dir)
        else:  # tar.xz
            with tarfile.open(archive_path, "r:xz") as tf:
                tf.extractall(dl_dir)

        for root, _dirs, files in os.walk(dl_dir):
            if bin_name in files:
                target = os.path.join(root, bin_name)
                break

        if target is None:
            log.error("ffmpeg download finished but %s not found under %s", bin_name, dl_dir)
            return None

        # Also try to place ffprobe next to it (used by _find_ffprobe if added later).
        if os.path.getsize(target) == 0:
            log.error("ffmpeg binary is empty: %s", target)
            return None

        if system != "windows":
            os.chmod(target, 0o755)

        log.info("ffmpeg extracted to: %s", target)
        _ffmpeg_path = target
        return target

    except Exception as e:
        log.error("ffmpeg auto-download failed: %s", e)
        for p in [archive_path, archive_path + ".part"]:
            try:
                if os.path.isfile(p):
                    os.unlink(p)
            except OSError:
                pass
        return None


def _run_ffmpeg(args: list, timeout: int = 120) -> tuple[bool, str]:
    """Run ffmpeg with args. Returns (success, stderr_tail)."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False, "ffmpeg not found and auto-download failed"
    try:
        r = subprocess.run(
            [ffmpeg] + args,
            capture_output=True,
            timeout=timeout,
        )
        if r.returncode != 0:
            return False, r.stderr.decode("utf-8", errors="replace")[-300:]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"ffmpeg timed out after {timeout}s"
    except Exception as e:
        return False, str(e)[:200]


def extract_audio_from_video(video_path: str) -> Optional[bytes]:
    """Extract audio track from video as 16kHz mono MP3. Returns mp3 bytes or None."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-i", video_path,
             "-vn", "-acodec", "libmp3lame", "-ab", "128k", "-ar", "16000", "-ac", "1",
             "pipe:1"],
            capture_output=True, timeout=300,
        )
        if r.returncode == 0 and r.stdout and len(r.stdout) > 100:
            return r.stdout
        return None
    except Exception as e:
        log.warning("extract_audio_from_video failed: %s", e)
        return None


def _get_video_duration(video_path: str) -> Optional[float]:
    """Return video duration in seconds, or None if undetectable."""
    import re
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        r = subprocess.run(
            [ffmpeg, "-i", video_path, "-f", "null", "-"],
            capture_output=True, timeout=30,
        )
        stderr = r.stderr.decode("utf-8", errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", stderr)
        if m:
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mi * 60 + s + ms / 100.0
        return None
    except Exception:
        return None


def extract_keyframes(video_path: str, count: int = 4) -> list[bytes]:
    """Extract N evenly-spaced JPEG keyframes from a video. Returns list of JPEG bytes."""
    frames: list[bytes] = []
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return frames

    duration = _get_video_duration(video_path)
    tmp_dir = tempfile.mkdtemp(prefix="amt_kf_")
    try:
        if duration and duration > 0:
            # Evenly-spaced: 1/(count+1), 2/(count+1), ..., count/(count+1)
            for i in range(count):
                t = duration * (i + 1) / (count + 1)
                out_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
                r = subprocess.run(
                    [ffmpeg, "-y", "-ss", f"{t:.2f}", "-i", video_path,
                     "-vframes", "1", "-q:v", "2", out_path],
                    capture_output=True, timeout=30,
                )
                if r.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                    with open(out_path, "rb") as f:
                        frames.append(f.read())
        else:
            # Unknown duration — grab first frame
            out_path = os.path.join(tmp_dir, "frame_0.jpg")
            r = subprocess.run(
                [ffmpeg, "-y", "-i", video_path, "-vframes", "1", "-q:v", "2", out_path],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as f:
                    frames.append(f.read())
    except Exception as e:
        log.warning("extract_keyframes failed: %s", e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return frames[:count]


def transcribe_audio(audio_bytes: bytes, mime: str = "audio/mp3") -> str:
    """Transcribe audio bytes to text.

    Strategy: cloud STT (Whisper API) → local Vosk fallback.
    Returns transcript text, or an error marker string starting with '[STT ERROR:'.
    """
    import media_gen

    ss = _get_server_settings()
    if not ss:
        return "[STT ERROR: no server settings]"

    # 1. Try cloud STT
    base = ss.audioBaseUrl or ss.baseUrl or ""
    key = ss.audioKey or ss.apiKey or ""
    stt_model = (ss.sttModel or "").strip() or ss.audioModel or "whisper-1"

    if key:
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        res = media_gen.transcribe_audio(
            base_url=base, api_key=key, model=stt_model,
            audio_b64=b64, mime=mime,
        )
        if res.get("ok"):
            return res.get("text", "").strip() or "[Пустой транскрипт]"

    # 2. Fall back to local Vosk
    try:
        import stt_local
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        result = stt_local.transcribe_local(b64, mime)
        if result.get("ok"):
            return result.get("text", "").strip() or "[Пустой транскрипт]"
        return f"[STT ERROR: {result.get('error', 'unknown')}]"
    except Exception as e:
        return f"[STT ERROR: local Vosk unavailable — {str(e)[:150]}"


def _get_server_settings():
    """Lazily import server_settings from main to avoid circular imports."""
    try:
        import main
        return main.server_settings
    except Exception:
        return None


def understand_media(file_path: str, mime_type: str) -> str:
    """Main entry: understand an audio or video file, return markdown for AI.

    Audio → STT transcript.
    Video → keyframes (base64 images) + audio transcript.

    Returns markdown text ready for injection into user_message.
    """
    name = os.path.basename(file_path)

    if mime_type.startswith("audio/"):
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            if len(data) > AUDIO_MAX:
                return f"[Аудио: {name} — файл слишком большой (>50MB)]"
            transcript = transcribe_audio(data, mime_type)
            return _audio_md(name, transcript)
        except Exception as e:
            return f"[Аудио: {name} — ошибка: {str(e)[:150]}]"

    if mime_type.startswith("video/"):
        try:
            size = os.path.getsize(file_path)
            if size > VIDEO_MAX:
                return f"[Видео: {name} — файл слишком большой (>200MB)]"

            frames = extract_keyframes(file_path, count=4)
            audio = extract_audio_from_video(file_path)
            transcript = transcribe_audio(audio, "audio/mpeg") if audio else ""
            return _video_md(name, frames, transcript)
        except Exception as e:
            return f"[Видео: {name} — ошибка: {str(e)[:150]}]"

    # Unknown media type — return placeholder
    return f"[Медиа: {name}]"


def _audio_md(name: str, transcript: str) -> str:
    """Build the markdown block for an audio transcript.

    Exposed for unit testing. ``transcript`` already starts with ``[STT ERROR``
    on failure — we surface that verbatim.
    """
    if transcript.startswith("[STT ERROR"):
        return f"[Аудио: {name}]\n{transcript}"
    if not transcript.strip():
        return f"[Аудио: {name}]\ntranscript: (not available)"
    return f"[Транскрипт аудио: {name}]\n{transcript}"


def _video_md(name: str, keyframes: list[bytes], transcript: str) -> str:
    """Build the markdown block for video keyframes + transcript.

    Exposed for unit testing. ``keyframes`` is a list of JPEG bytes; each is
    embedded as a base64 data-URL the vision pipeline can ingest.
    """
    parts: list[str] = []

    if keyframes:
        parts.append(f"[Кадры из видео: {name}]")
        for i, jpeg in enumerate(keyframes, 1):
            b64 = base64.b64encode(jpeg).decode("ascii")
            parts.append(f"![frame_{i}](data:image/jpeg;base64,{b64})")
    else:
        parts.append(f"[Видео: {name} — кадры не удалось извлечь]")

    if transcript.strip():
        if transcript.startswith("[STT ERROR"):
            parts.append(f"[Звук в видео: {name}]\n{transcript}")
        else:
            parts.append(f"[Транскрипт звука из видео: {name}]\n{transcript}")
    elif not keyframes:
        # No frames and no transcript — nothing useful to show.
        parts.append(f"[Видео: {name} — ни кадры, ни звук не удалось извлечь]")

    return "\n\n".join(parts)
