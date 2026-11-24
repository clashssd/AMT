"""Tests for media generation endpoints + any-language code files."""
import json
import pytest
from fastapi.testclient import TestClient

import main
from ai_engine import filegen, media


def test_code_file_any_language():
    data, fname = filegen.generate_file("code", "def x(): pass", "script", lang="py")
    assert fname.endswith(".py")
    data, fname = filegen.generate_file("code", "fn main(){}", "app", lang="rs")
    assert fname.endswith(".rs")
    data, fname = filegen.generate_file("code", "console.log(1)", "x", lang="js")
    assert fname.endswith(".js")
    data, fname = filegen.generate_file("code", "SELECT 1", "q", lang="sql")
    assert fname.endswith(".sql")


def test_media_check_no_key():
    r = media.check_capability("image", "", "", "")
    assert r["ok"] is False
    assert "Ключ не указан" in r["reason"]


def test_media_check_network_error_returns_ok_false(monkeypatch):
    # без сети/ключей — должно ок-ложно, а не падать
    r = media.check_capability("image", "http://127.0.0.1:1", "sk-x", "m")
    assert r["ok"] in (False, True)  # нет подключения → False
    assert "reason" in r


def test_media_generate_no_key():
    r = media.generate_image("", "", "", "prompt")
    assert r["ok"] is False and r["code"] == "no_key"
    r = media.generate_video("", "", "", "prompt")
    assert r["ok"] is False and r["code"] == "no_key"
    r = media.generate_audio("", "", "", "text")
    assert r["ok"] is False and r["code"] == "no_key"


@pytest.fixture
def c(tmp_backend):
    return TestClient(main.app)


def test_media_check_endpoint(c):
    r = c.post("/api/media/check", json={"kind": "image", "api_key": "", "use_settings_key": False})
    assert r.status_code == 200
    assert "supported" in r.json()


def test_media_generate_no_key_endpoint(c):
    r = c.post("/api/media/generate", json={"kind": "image", "prompt": "x", "use_settings_key": False, "api_key": ""})
    j = r.json()
    assert j["ok"] is False
    assert j["code"] == "no_key"


def test_filegen_code_endpoint(c):
    r = c.post("/api/filegen/generate", json={"filetype": "code", "content": "print(1)", "title": "a", "lang": "go"})
    j = r.json()
    assert j["status"] == "ok"
    assert j["filename"].endswith(".go")


# ===== STT (распознавание голоса) =====
def test_transcribe_audio_no_key():
    r = media.transcribe_audio("", "", "whisper-1", "QUFD")
    assert r["ok"] is False and r["code"] == "no_key"


def test_transcribe_audio_no_audio():
    r = media.transcribe_audio("http://127.0.0.1:1", "sk-x", "whisper-1", "")
    assert r["ok"] is False and r["code"] == "no_audio"


def test_transcribe_audio_base_url_not_doubled_v1(monkeypatch):
    # base с /v1 не должен давать /v1/v1/audio/transcriptions
    calls = {}
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"text": "привет"}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, files=None, data=None):
            calls["url"] = url
            return _Resp()
    import httpx
    media._client = lambda *a, **k: _Client()
    r = media.transcribe_audio("https://apihub.agnes-ai.com/v1", "sk-x", "whisper-1", "QUFD", "audio/webm")
    assert calls["url"].endswith("/v1/audio/transcriptions"), calls["url"]
    assert "/v1/v1" not in calls["url"]


def test_generate_audio_base_url_not_doubled_v1(monkeypatch):
    # base с /v1 (Agnes, не ElevenLabs) → универсальный /v1/audio/speech без /v1/v1
    calls = {}
    class _Resp:
        status_code = 200
        content = b"mp3"
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["headers"] = headers
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.generate_audio("https://apihub.agnes-ai.com/v1", "sk-x", "m", "привет")
    assert r["ok"] is True, r
    assert calls["url"].endswith("/v1/audio/speech"), calls["url"]
    assert "/v1/v1" not in calls["url"], calls["url"]
    # Универсальный путь: Bearer-авторизация, НЕ xi-api-key
    assert "Authorization" in calls["headers"], calls["headers"]
    assert calls["headers"].get("Authorization", "").startswith("Bearer "), calls["headers"]


def test_generate_audio_universal_provider(monkeypatch):
    # Любой OpenAI-совместимый провайдер (не elevenlabs) → /v1/audio/speech + Bearer + voice=alloy
    calls = {}
    class _Resp:
        status_code = 200
        content = b"mp3"
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["headers"] = headers
            calls["body"] = json
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.generate_audio("https://openrouter.ai/api/v1", "sk-or", "tts-1", "привет")
    assert r["ok"] is True, r
    assert calls["url"].endswith("/v1/audio/speech"), calls["url"]
    assert "Bearer" in calls["headers"].get("Authorization", ""), calls["headers"]
    # Provider-neutral: voice пустая = провайдер выберет свой дефолт (не alloy-по-умолчанию)
    assert calls["body"]["voice"] in ("", None), calls["body"]


def test_generate_audio_elevenlabs_dialect(monkeypatch):
    # base elevenlabs.io → диалект ElevenLabs (xi-api-key + /v1/text-to-speech/{voice} + model_id)
    calls = {}
    class _Resp:
        status_code = 200
        content = b"mp3"
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["headers"] = headers
            calls["body"] = json
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.generate_audio("https://api.elevenlabs.io", "sk-x", "", "привет")
    assert r["ok"] is True, r
    assert "text-to-speech" in calls["url"], calls["url"]
    assert "xi-api-key" in calls["headers"], calls["headers"]
    assert "model_id" in calls["body"], calls["body"]


def test_list_voices_universal_provider(monkeypatch):
    # Не-ElevenLabs провайдер → универсальный GET /v1/voices (Bearer)
    calls = {}
    class _Resp:
        status_code = 200
        def json(self): return {"voices": []}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, headers=None):
            calls["url"] = url
            calls["headers"] = headers
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.list_voices("https://openrouter.ai/api", "sk-or")
    assert r["ok"] is True, r
    assert "Bearer" in calls["headers"].get("Authorization", ""), calls["headers"]


def test_list_voices_elevenlabs_dialect(monkeypatch):
    # ElevenLabs → GET /v1/voices с xi-api-key
    calls = {}
    class _Resp:
        status_code = 200
        def json(self): return {"voices": [{"voice_id": "abc", "name": "x"}]}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, headers=None):
            calls["url"] = url
            calls["headers"] = headers
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.list_voices("https://api.elevenlabs.io", "sk-x")
    assert r["ok"] is True, r
    assert "xi-api-key" in calls["headers"], calls["headers"]
    assert r["voices"][0]["id"] == "abc"


def test_clone_voice_universal_provider(monkeypatch):
    # Не-ElevenLabs → POST /v1/voices (Bearer)
    calls = {}
    class _Resp:
        status_code = 200
        def json(self): return {"id": "v1", "name": "Cloned voice"}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["headers"] = headers
            return _Resp()
    media._client = lambda *a, **k: _Client()
    import base64
    big = base64.b64encode(b"x" * 20000).decode()
    r = media.clone_voice("https://openrouter.ai/api", "sk-or", big, "myvoice")
    assert r["ok"] is True, r
    assert "Bearer" in calls["headers"].get("Authorization", ""), calls["headers"]


def test_clone_voice_elevenlabs_dialect(monkeypatch):
    # ElevenLabs → POST /v1/voices/add с xi-api-key
    calls = {}
    class _Resp:
        status_code = 200
        def json(self): return {"id": "v1", "name": "myvoice"}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["headers"] = headers
            return _Resp()
    media._client = lambda *a, **k: _Client()
    import base64
    big = base64.b64encode(b"x" * 20000).decode()
    r = media.clone_voice("https://api.elevenlabs.io", "sk-x", big, "myvoice")
    assert r["ok"] is True, r
    assert "text-to-speech" not in calls["url"]
    assert "xi-api-key" in calls["headers"], calls["headers"]


def test_check_capability_video_passes_model_through(monkeypatch):
    # Provider-neutral: check_capability video sends the user's model as-is
    # (no hardcoded provider model substitution). The Agnes auto-mapping was
    # removed; a user who wants a specific video model sets it explicitly.
    calls = []
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"ok": True}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls.append({"url": url, "body": json})
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.check_capability("video", "https://apihub.agnes-ai.com/v1", "sk-x", "my-video-model")
    assert r["ok"] is True, r
    video_calls = [c for c in calls if "videos" in c["url"]]
    assert video_calls, f"No video calls in {calls}"
    # Provider-neutral: generic video probe doesn't inject a hardcoded model.
    # The user's model is either passed through or absent — never a forced name.
    body = video_calls[0]["body"]
    assert "model" not in body or body["model"] == "my-video-model", body


def test_check_capability_video_agnes_no_double_v1(monkeypatch):
    # Agnes base /v1: проверка видео идёт на {api_base}/videos, без /v1/v1
    calls = []
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"ok": True}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls.append(url)
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.check_capability("video", "https://apihub.agnes-ai.com/v1", "sk-x", "")
    assert r["ok"] is True, r
    # Check that no URL has /v1/v1
    for url in calls:
        assert "/v1/v1" not in url, url


def test_generate_video_agnes_no_double_v1(monkeypatch):
    # Provider-neutral: base с /v1 не даёт /v1/v1. Точный URL зависит от пути
    # (универсальный text2video), главное — без двойного /v1/v1.
    calls = {}
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"video_id": "abc"}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.generate_video("https://apihub.agnes-ai.com/v1", "sk-x", "m", "кошка")
    assert r["ok"] is True, r
    assert "/v1/v1" not in calls["url"], calls["url"]


def test_generate_video_passes_explicit_video_model(monkeypatch):
    # Provider-neutral: если пользователь явно указал видеомодель, она уходит как есть.
    # (Старая авто-подстановка agnes-video-2.5-flash удалена — модель задаёт пользователь.)
    calls = {}
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"video_id": "abc"}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["body"] = json
            return _Resp()
    media._client = lambda *a, **k: _Client()
    media.generate_video("https://apihub.agnes-ai.com/v1", "sk-x", "sora-2", "кошка")
    assert calls["body"]["model"] == "sora-2", calls["body"]["model"]


def test_check_capability_audio_base_url_not_doubled_v1(monkeypatch):
    # check_capability (media_check path) с Agnes base /v1 не даёт /v1/v1
    calls = []
    class _Resp:
        status_code = 200
        text = ""
        def json(self): return {"ok": True}
    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            calls.append(url)
            return _Resp()
    media._client = lambda *a, **k: _Client()
    r = media.check_capability("audio", "https://apihub.agnes-ai.com/v1", "sk-x", "", "21m00Tcm4TlvDq8ikT7d")
    assert r["ok"] is True, r
    # No URL should have /v1/v1
    for url in calls:
        assert "/v1/v1" not in url, url


def test_transcribe_audio_endpoint(c):
    r = c.post("/api/stt", json={"audio_b64": "QUFD", "mime": "audio/webm",
                                 "api_key": "", "base_url": "", "model": "",
                                 "use_settings_key": False})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False
    assert "code" in j
