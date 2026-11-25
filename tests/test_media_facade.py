import base64
from ai_engine import media  # from backend, via conftest sys.path


def test_prepare_payload_minimal():
    p = media._prepare_payload("make a cat", "model-x")
    assert p["prompt"] == "make a cat"
    assert p["model"] == "model-x"
    assert "image" not in p and "file" not in p


def test_prepare_payload_attached_bytes():
    raw = b"\x89PNG\r\n\x1a\n"
    p = media._prepare_payload("cat", "m", attached_file=raw)
    expected = base64.b64encode(raw).decode("ascii")
    # image bytes -> "image" field
    assert p["image"] == expected or p["file"] == expected


def test_prepare_payload_attached_path(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"imgdata")
    p = media._prepare_payload("cat", "m", attached_file=str(f))
    assert p["image"] == base64.b64encode(b"imgdata").decode("ascii") or \
           p["file"] == base64.b64encode(b"imgdata").decode("ascii")


def test_prepare_payload_attached_b64_string_used_as_is():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=b64val)
    # a plain base64 string that is NOT a file path -> used as-is
    assert p["image"] == b64val


def test_prepare_payload_attached_data_uri_stripped():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=f"data:image/png;base64,{b64val}")
    assert p["image"] == b64val


def test_get_path_branches():
    assert media._get_path(False, "p", False) == media.DEFAULT_PATH_TEXT_TO_MEDIA
    assert media._get_path(True, "p", False) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA
    assert media._get_path(True, "", False) == media.DEFAULT_PATH_IMAGE_TO_MEDIA
    assert media._get_path(False, "", True) == media.DEFAULT_PATH_VOICE


def test_get_path_user_paths_override():
    up = {"text_to_media": "my/custom/path"}
    assert media._get_path(False, "p", False, up) == "my/custom/path"
    # empty user_paths entry falls back to default
    assert media._get_path(False, "p", False, {"text_to_media": ""}) == media.DEFAULT_PATH_TEXT_TO_MEDIA


def test_generate_media_success_custom(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None, **kw):
        captured.update(api_key=api_key, base_url=base_url, model=model, path=path, prompt=prompt)
        # provider-style body (what _make_request returns via resp.json())
        return {"b64": "AAAA", "url": "u"}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("KEY", "https://api.example", "mod-1",
                               {"text_to_media": "my/path"}, "a cat")
    # FLAT contract: provider keys land at top level, no "result" nesting
    assert res["ok"] is True
    assert res["b64"] == "AAAA"
    assert "result" not in res
    assert captured["api_key"] == "KEY"
    assert captured["base_url"] == "https://api.example"
    assert captured["model"] == "mod-1"
    assert captured["path"] == "my/path"


def test_generate_media_fallback_to_defaults(monkeypatch):
    calls = []
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None, **kw):
        calls.append((api_key, base_url, model, path))
        if api_key == "BAD_KEY":
            raise RuntimeError("custom failed: 401")
        return {"b64": "BBBB"}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("BAD_KEY", "https://bad", "bad-model", {}, "prompt", attached_file=b"raw")
    assert res["ok"] is True
    assert res["b64"] == "BBBB"      # flat: from the successful default attempt
    assert "result" not in res
    assert len(calls) == 2
    # second call used strict defaults
    assert calls[1][0] == media.DEFAULT_API_KEY
    assert calls[1][1] == media.DEFAULT_BASE_URL
    assert calls[1][2] == media.DEFAULT_MODEL


def test_generate_media_double_failure(monkeypatch):
    def fake_make_request(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("K", "U", "M", {}, "p")
    assert res["ok"] is False
    assert res["code"] == "api_error"
    assert "Ошибка кастомного API" in res["error"]
    assert "Ошибка дефолтного API" in res["error"]


def test_generate_media_audio_threads_voice_id_and_settings(monkeypatch):
    """Голос через фасад обязан передавать voice_id и voice_settings в payload —
    иначе провайдер отклонит TTS-запрос (500). Регресс на main.py:4701, где фасад
    бросал voice_id/voice_settings при маршрутизации kind=audio через paths."""
    captured = {}

    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None,
                          voice_id=None, voice_settings=None, extra=None):
        captured["voice_id"] = voice_id
        captured["voice_settings"] = voice_settings
        return {"b64": "AAAA"}

    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media(
        "KEY", "https://api.example", "tts-model",
        {"voice": "my/voice/path"}, "привет",
        is_voice=True, voice_id="alice-voice",
        voice_settings={"speed": 1.2},
    )
    assert res["ok"] is True
    assert captured["voice_id"] == "alice-voice"
    assert captured["voice_settings"] == {"speed": 1.2}


def test_generate_media_whitespace_user_field_substituted(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None, **kw):
        captured["model"] = model
        return {"ok": True}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    # whitespace model -> DEFAULT_MODEL on attempt 1
    media.generate_media("KEY", "BASE", "   ", {}, "p")
    assert captured["model"] == media.DEFAULT_MODEL


def test_generate_media_verbatim_model_not_trimmed(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None, **kw):
        captured["model"] = model
        return {"ok": True}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    media.generate_media("KEY", "BASE", "  my-model  ", {}, "p")
    # verbatim: NOT trimmed
    assert captured["model"] == "  my-model  "


def test_generate_image_signature_unchanged():
    # generate_image must keep its exact param names
    import inspect
    sig = inspect.signature(media.generate_image)
    assert list(sig.parameters) == ["base_url", "api_key", "model", "prompt",
                                    "size", "proxy", "extra"]


# ---- Task 4: facade paths routing (empty + partial + endpoint) ----

def test_generate_media_all_empty_paths_uses_defaults():
    """An all-empty paths dict must resolve to DEFAULT_PATH_* for each branch."""
    up = {"text_to_media": "", "image_to_media": "", "text_image_to_media": "", "voice": ""}
    assert media._get_path(False, "p", False, up) == media.DEFAULT_PATH_TEXT_TO_MEDIA
    assert media._get_path(True, "p", False, up) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA
    assert media._get_path(True, "", False, up) == media.DEFAULT_PATH_IMAGE_TO_MEDIA
    assert media._get_path(False, "", True, up) == media.DEFAULT_PATH_VOICE


def test_generate_media_partial_paths_verbatim():
    """A set path is used verbatim; an unset path falls back to DEFAULT."""
    up = {"image_to_media": "v1/my/custom/image", "text_image_to_media": "", "text_to_media": "", "voice": ""}
    # image-only branch (has file, prompt empty) -> image_to_media (custom)
    assert media._get_path(True, "", False, up) == "v1/my/custom/image"
    # text+image branch -> text_image_to_media empty -> DEFAULT
    assert media._get_path(True, "prompt", False, up) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA


def test_api_media_generate_with_paths_endpoint():
    """POST /api/media/generate with a paths dict must not 500 (routes through facade)."""
    from fastapi.testclient import TestClient
    import main as app_mod
    app_mod.server_settings = app_mod.Settings()
    c = TestClient(app_mod.app)
    r = c.post("/api/media/generate", json={
        "kind": "image", "prompt": "a cat", "use_settings_key": True,
        "paths": {"text_to_media": "", "image_to_media": "", "text_image_to_media": "", "voice": ""},
    })
    # A dict response (ok true/false), NOT an HTTP 500
    assert r.status_code in (200, 400, 502), f"unexpected status {r.status_code}"
    assert "ok" in r.json(), f"missing 'ok' key in {r.json()}"
