"""Regression: media tool-calling handlers must call media.generate_* with a
STRING base_url (resolved from settings), never with a config dict positional.

The original bug: `_handle_generate_image(prompt,size,model,ref_image_b64)` built
a `cfg` dict and called `media.generate_image(cfg)` — the dict bound positionally
to `base_url`, then `provider_profile` did `base_url.rstrip('/')` →
`'dict' object has no attribute 'rstrip'`.

Fix: handlers resolve {base,key,model,proxy} from main.server_settings via
`_media_cfg(kind)` and call media with keyword args. This test pins that the
`base_url` received by the underlying media function is a `str`.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import ai_engine.tool_registry as tool_registry  # noqa: E402
import main as _main  # noqa: E402  (for _clean_ref_base64)


def _fake_settings(**overrides):
    defaults = dict(
        baseUrl="https://apihub.agnes-ai.com/v1",
        apiKey="sk-test",
        model="agnes-3.0-flash",
        imageBaseUrl="", imageKey="", imageModel="",
        videoBaseUrl="", videoKey="", videoModel="",
        audioBaseUrl="", audioKey="", audioModel="", sttModel="",
        proxyUrl="", httpsProxy="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_media_cfg_image_falls_back_to_global():
    """imageBaseUrl/imageKey empty → use global baseUrl/apiKey/model."""
    ss = _fake_settings()
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=ss)}):
        cfg = tool_registry._media_cfg("image")
    assert cfg["base"] == "https://apihub.agnes-ai.com/v1"
    assert cfg["key"] == "sk-test"
    assert cfg["model"] == "agnes-3.0-flash"


def test_media_cfg_image_uses_image_specific():
    ss = _fake_settings(imageBaseUrl="https://img.example/v1", imageKey="img-key", imageModel="img-model")
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=ss)}):
        cfg = tool_registry._media_cfg("image")
    assert cfg["base"] == "https://img.example/v1"
    assert cfg["key"] == "img-key"
    assert cfg["model"] == "img-model"


def test_media_cfg_audio_stt_priority():
    ss = _fake_settings(audioModel="audio-model", sttModel="stt-model")
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=ss)}):
        cfg = tool_registry._media_cfg("audio")
    assert cfg["model"] == "stt-model"  # sttModel wins


def test_generate_image_passes_string_base_url(monkeypatch):
    """The core regression: media.generate_image must receive a STRING base_url,
    never a dict. We capture the positional args the handler forwards."""
    captured = {}

    def fake_generate_image(base_url="", api_key="", model="", prompt="", size="1024x1024", proxy="", extra=None):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["prompt"] = prompt
        return {"ok": True, "path": "/files/x.png", "b64": "aGVsbG8="}

    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=_fake_settings())}):
        media_mod = mock.MagicMock()
        media_mod.generate_image.side_effect = fake_generate_image
        media_mod.generate_image_ref = mock.MagicMock()
        with mock.patch.object(tool_registry, "media", media_mod, create=True):
            # tool_registry imports media lazily inside the handler via
            # `from ai_engine import media`; patch the ai_engine module attr instead.
            import ai_engine.media as real_media
            monkeypatch.setattr(real_media, "generate_image", fake_generate_image)
            monkeypatch.setattr(real_media, "generate_image_ref", mock.MagicMock())
            out = asyncio.run(tool_registry._handle_generate_image(prompt="a cat", size="1:1"))

    # Handler returns JSON-dumped result (or an error JSON). The base_url passed
    # to media must be a real string, not a dict.
    import json
    payload = json.loads(out)
    assert isinstance(captured["base_url"], str), f"base_url must be str, got {type(captured['base_url'])}"
    assert captured["base_url"] == "https://apihub.agnes-ai.com/v1"
    assert captured["prompt"] == "a cat"
    # result forwarded (not an error) since fake returned ok
    assert "ok" in payload or "path" in payload


def test_generate_image_ref_passes_string_base_url_and_ref(monkeypatch):
    captured = {}

    def fake_ref(base_url="", api_key="", model="", prompt="", size="1024x1024", ref_image_b64="", proxy="", extra=None):
        captured["base_url"] = base_url
        captured["ref"] = ref_image_b64
        return {"ok": True, "path": "/files/y.png", "b64": "aGk="}

    import ai_engine.media as real_media
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=_fake_settings())}):
        monkeypatch.setattr(real_media, "generate_image_ref", fake_ref)
        out = asyncio.run(tool_registry._handle_generate_image(
            prompt="pink hat", size="1:1", ref_image_b64="REFDATA"))
    import json
    json.loads(out)
    assert isinstance(captured["base_url"], str)
    assert captured["ref"] == "REFDATA"


def test_media_cfg_reloads_when_key_empty(monkeypatch):
    """Anti-no_key: when the in-memory key is empty, _media_cfg re-reads persisted
    settings from disk so a key saved mid-session works without a restart."""
    import ai_engine.media as real_media
    # Persist a file that HAS the image key.
    live = Path(__file__).parent.parent / "backend" / "settings.json"
    original = live.read_text(encoding="utf-8") if live.exists() else None
    try:
        live.write_text(
            json.dumps({"baseUrl": "https://h/v1", "apiKey": "sk-global",
                        "model": "m", "imageKey": "sk-persisted-img",
                        "imageBaseUrl": "https://h/v1/images/generations",
                        "imageModel": "img-2"}),
            encoding="utf-8")
        # In-memory server_settings has an EMPTY imageKey (and empty global apiKey
        # so the first pass resolves key="" and triggers the reload branch).
        monkeypatch.setenv("AMT_SETTINGS_FILE", str(live))
        main_mod = mock.MagicMock()
        main_mod.server_settings = SimpleNamespace(
            baseUrl="", apiKey="", model="", proxyUrl="", httpsProxy="",
            imageKey="", imageBaseUrl="", imageModel="",
            videoKey="", videoBaseUrl="", videoModel="",
            audioKey="", audioBaseUrl="", audioModel="", sttModel="",
        )
        # load_persisted_settings re-reads the file into a fresh object with the key.
        def _fake_load():
            main_mod.server_settings = SimpleNamespace(
                baseUrl="", apiKey="sk-global-reloaded", model="m",
                proxyUrl="", httpsProxy="",
                imageKey="sk-persisted-img", imageBaseUrl="https://h/v1/images/generations",
                imageModel="img-2",
                videoKey="", videoBaseUrl="", videoModel="",
                audioKey="", audioBaseUrl="", audioModel="", sttModel="",
            )
        main_mod.load_persisted_settings = _fake_load
        calls = {"reloaded": False}
        _orig_fake = _fake_load
        def _fake_load_tracking(*a, **k):
            calls["reloaded"] = True
            return _orig_fake(*a, **k)
        main_mod.load_persisted_settings = _fake_load_tracking
        with mock.patch.dict("sys.modules", {"main": main_mod}):
            cfg = tool_registry._media_cfg("image")
        # Reload pulled the persisted key in even though in-memory was empty.
        assert cfg["key"] == "sk-persisted-img"
        assert calls["reloaded"] is True, "expected load_persisted_settings to be invoked on empty key"
    finally:
        if original is not None:
            live.write_text(original, encoding="utf-8")
        else:
            live.unlink(missing_ok=True)
        monkeypatch.delenv("AMT_SETTINGS_FILE", raising=False)


# --- _clean_ref_base64 (tool-calling image-to-image) ---
# Regression: the model passes ref_image_b64 as a markdown-wrapped/truncated
# data URI, or leaves it empty; the provider then 400s "must be a public
# http(s) URL or valid image base64". _clean_ref_base64 must return CLEAN
# base64 (no ![](...) wrapper, no data: prefix) or fall back to the attached
# image embedded in user_message / attachments.

import base64 as _b64_test  # noqa: E402


def _valid_png_b64():
    """Minimal 1x1 transparent PNG, base64. Used to build data-URIs that a
    real provider would accept."""
    import struct
    import zlib
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
        return c
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    raw = b"\x00\x00\x00\x00\x00"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return _b64_test.b64encode(sig + ihdr + idat + iend).decode("ascii")


def test_clean_ref_normalizes_markdown_wrapper():
    b64 = _valid_png_b64()
    wrapped = f"![ref](data:image/png;base64,{b64})"
    assert _main._clean_ref_base64(wrapped, "", None) == b64


def test_clean_ref_normalizes_bare_data_uri():
    b64 = _valid_png_b64()
    assert _main._clean_ref_base64(f"data:image/png;base64,{b64}", "", None) == b64


def test_clean_ref_passes_clean_b64_through():
    b64 = _valid_png_b64()
    assert _main._clean_ref_base64(b64, "", None) == b64


def test_clean_ref_rejects_truncated_b64():
    # Mangled base64 (non-alphabet chars / cut stream) must NOT be returned.
    b64 = _valid_png_b64()
    # Append junk chars that break the base64 alphabet → invalid.
    mangled = b64 + "!!!"
    # value-branch must reject it; with no embed/disk fallback, returns "".
    assert _main._clean_ref_base64(mangled, "", None) == ""


def test_clean_ref_falls_back_to_user_message_embed():
    """Empty/invalid value, but user_message has an embedded attachment data-URL."""
    b64 = _valid_png_b64()
    user_message = f"измени шарф на зелёный\n![фото](data:image/png;base64,{b64})"
    assert _main._clean_ref_base64("", user_message, None) == b64


def test_clean_ref_falls_back_to_attachment_on_disk(monkeypatch, tmp_path):
    """value empty + no embed in user_message → read first image/* attachment."""
    b64 = _valid_png_b64()
    raw = _b64_test.b64decode(b64)
    p = tmp_path / "ref.png"
    p.write_bytes(raw)
    att = [{"path": str(p), "filename": "ref.png", "mime_type": "image/png"}]
    out = _main._clean_ref_base64("", "", att)
    assert out == b64


def test_clean_ref_returns_empty_when_nothing_valid():
    assert _main._clean_ref_base64("not-base64!!!", "no images here", None) == ""
    assert _main._clean_ref_base64("", "no images here", None) == ""


# --- _normalize_args: weak-model resilience (missing/null/type-mismatched args) ---

def test_normalize_applies_schema_default_for_missing_optional():
    tool = tool_registry.tool_registry.get("generate_image")
    out = tool_registry.ToolRegistry._normalize_args(tool, {})
    assert out["size"] == "1:1"          # default injected
    assert "prompt" not in out           # required, no default → not invented
    assert out.get("model", "") == ""    # default ""


def test_normalize_drops_unknown_keys_and_null():
    tool = tool_registry.tool_registry.get("generate_image")
    out = tool_registry.ToolRegistry._normalize_args(tool, {"prompt": "x", "bogus": 1, "model": None})
    assert "bogus" not in out            # unknown param must NOT reach handler
    assert out["prompt"] == "x"
    # model=None → dropped (no schema default for model) → handler default kicks in
    assert out.get("model", "") in ("", None)


def test_normalize_coerces_integer_string():
    tool = tool_registry.tool_registry.get("generate_video")
    out = tool_registry.ToolRegistry._normalize_args(tool, {"prompt": "v", "duration": "7"})
    assert out["duration"] == 7         # "7" → 7 per schema type=integer


def test_normalize_coerces_string_number():
    tool = tool_registry.tool_registry.get("generate_image")
    out = tool_registry.ToolRegistry._normalize_args(tool, {"size": 1024})
    assert out["size"] == "1024"        # int → str per schema type=string


# --- no-prompt guard: handler returns clean JSON, not a TypeError ---

def test_generate_image_no_prompt_returns_clean_error():
    import ai_engine.media as real_media
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        return {"ok": True}
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=_fake_settings())}):
        with mock.patch.object(real_media, "generate_image", _boom):
            out = asyncio.run(tool_registry._handle_generate_image(prompt="", size="1:1"))
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["code"] == "no_prompt"
    assert called["n"] == 0            # must NOT reach media when prompt empty


def test_generate_video_no_prompt_returns_clean_error():
    import ai_engine.media as real_media
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        return {"ok": True}
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=_fake_settings())}):
        with mock.patch.object(real_media, "generate_video", _boom):
            out = asyncio.run(tool_registry._handle_generate_video(prompt=""))
    payload = json.loads(out)
    assert payload["code"] == "no_prompt"
    assert called["n"] == 0


def test_generate_audio_no_text_returns_clean_error():
    import ai_engine.media as real_media
    called = {"n": 0}
    def _boom(*a, **k):
        called["n"] += 1
        return {"ok": True}
    with mock.patch.dict("sys.modules", {"main": SimpleNamespace(server_settings=_fake_settings())}):
        with mock.patch.object(real_media, "generate_audio", _boom):
            out = asyncio.run(tool_registry._handle_generate_audio(text=""))
    payload = json.loads(out)
    assert payload["code"] == "no_text"
    assert called["n"] == 0


def test_generate_image_ref_non_agnes_uses_edits(monkeypatch):
    """Provider-neutral image-to-image: a NON-agnes provider with a ref must go
    through the standard OpenAI /images/edits multipart (not the agnes extra_body
    dialect). We stub the httpx client so no real network call happens."""
    from ai_engine import media as _m

    captured = {"calls": []}

    class _Resp:
        def __init__(self, sc=200, b64="QUtFTVQ="):
            self.status_code = sc
            self._b64 = b64
        def json(self):
            return {"data": [{"b64_json": self._b64, "url": ""}]}
        @property
        def text(self):
            return ""

    class _Client:
        def __init__(self, *a, **k):
            pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None, content=None):
            captured["calls"].append({"url": url, "multipart": content is not None, "json": json})
            return _Resp(200, "QUtFTVQ=")

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    # A generic OpenAI-compatible host (NOT in _BASE_PROVIDER_HINTS)
    out = _m.generate_image_ref(
        base_url="https://img.example.com/v1",
        api_key="k", model="m", prompt="a cat", size="512x512",
        ref_image_b64="QUtFTVQ=", proxy="")
    assert out.get("ok") is True
    urls = [c["url"] for c in captured["calls"]]
    assert any("/images/edits" in u for u in urls), f"expected /images/edits, got {urls}"
    # No extra_body (agnes dialect) must be sent to a non-agnes provider
    assert not any((c.get("json") and "extra_body" in str(c["json"])) for c in captured["calls"])


def test_generate_image_ref_agnes_falls_back_to_extra_body(monkeypatch):
    """Agnes provider: if /images/edits fails, fall back to extra_body dialect."""
    from ai_engine import media as _m

    calls = []

    class _Resp:
        def __init__(self, sc, body=None, b64=""):
            self.status_code = sc
            self._body = body or {}
            self._b64 = b64
        def json(self):
            return self._body
        @property
        def text(self):
            return "boom" if self.status_code >= 400 else ""

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None, content=None):
            calls.append(url)
            if "/images/edits" in url:
                return _Resp(400, {"error": "edits not supported"})  # edits fails
            return _Resp(200, {"data": [{"b64_json": "QUtFTVQ=", "url": ""}]}, "QUtFTVQ=")

    # force agnes dialect: the real hint matches hosts containing "agnes"
    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    monkeypatch.setattr(_m, "_BASE_PROVIDER_HINTS", {"agnes": "img-agnes.example.com"})
    out = _m.generate_image_ref(
        base_url="https://img-agnes.example.com/v1",
        api_key="k", model="m", prompt="a cat", size="512x512",
        ref_image_b64="QUtFTVQ=", proxy="")
    # edits failed -> extra_body fallback succeeded
    assert out.get("ok") is True
    assert any("/images/edits" in u for u in calls)
    assert any("/images/generations" in u for u in calls)



def test_generate_image_ref_falls_back_to_text2img_when_provider_cannot_edit(monkeypatch):
    """Provider-neutral: when image-to-image is impossible (no /images/edits AND
    no agnes extra_body dialect — i.e. a plain OpenAI-compatible host whose edits
    endpoint 400s), generate_image_ref must fall back to text-to-image and attach
    a clear note, instead of returning the ref error. This is the honest fix for
    a local-photo edit request on a provider that cannot do image-to-image."""
    from ai_engine import media as _m

    calls = []

    class _Resp:
        def __init__(self, sc, b64=""):
            self.status_code = sc
            self._b64 = b64
        def json(self):
            return {"data": [{"b64_json": self._b64, "url": ""}]}
        @property
        def text(self):
            return "boom" if self.status_code >= 400 else ""

    class _Client:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, headers=None, json=None, content=None):
            calls.append(url)
            if "/images/edits" in url:
                # This provider does NOT support /images/edits -> 503.
                return _Resp(503)
            # text-to-image /images/generations succeeds.
            return _Resp(200, "QUtFTVQ=")

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    # Plain OpenAI-compatible host (NOT in provider hints) with a ref.
    out = _m.generate_image_ref(
        base_url="https://plain.example.com/v1",
        api_key="k", model="m", prompt="a cat with an orange scarf",
        size="512x512", ref_image_b64="QUtFTVQ=", proxy="")
    assert out.get("ok") is True
    assert any("/images/edits" in u for u in calls), "must attempt the ref path first"
    assert any("/images/generations" in u for u in calls), "must fall back to text-to-image"
    assert "note" in out and "not supported" in out["note"]


def test_generate_image_ref_agnes_extra_body_uses_raw_base64_not_data_uri(monkeypatch):
    """Regression: agnes extra_body.image must carry RAW base64, NOT a data:-
    prefixed data-URI. The agnes hub validates the ref as «public http(s) URL or
    valid image base64» — a data: prefix is rejected with 400
    "extra_body.image is not a valid image base64".
    """
    from ai_engine import media as _m

    captured = []

    class _Resp:
        def __init__(self, sc, body=None, b64=""):
            self.status_code = sc
            self._body = body or {}
            self._b64 = b64
        def json(self):
            return self._body
        @property
        def text(self):
            return "boom" if self.status_code >= 400 else ""

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None, content=None):
            if json is not None:
                captured.append(json)
            if "/images/edits" in url:
                return _Resp(400, {"error": "edits not supported"})  # force the agnes extra_body fallback
            return _Resp(200, {"data": [{"b64_json": "QUtFTVQ=", "url": ""}]}, "QUtFTVQ=")

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    monkeypatch.setattr(_m, "_BASE_PROVIDER_HINTS", {"agnes": "img-agnes.example.com"})
    out = _m.generate_image_ref(
        base_url="https://img-agnes.example.com/v1",
        api_key="k", model="m", prompt="a cat", size="512x512",
        ref_image_b64="QUtFTVQ=", proxy="")
    assert out.get("ok") is True
    # Find the extra_body (agnes) call and assert its image field is raw b64.
    extra = [c for c in captured if c and "extra_body" in c]
    assert extra, "expected the agnes extra_body fallback to fire"
    img = extra[0]["extra_body"]["image"]
    # image is a list per the dialect; first element must be the raw b64, not a data-URI.
    assert isinstance(img, list) and img
    assert not any(str(x).startswith("data:") for x in img), \
        "extra_body.image must NOT carry a data:-prefixed data-URI"
    assert "QUtFTVQ=" in [str(x) for x in img]


def test_generate_video_standard_first_dialect_fallback(monkeypatch):
    """Provider-neutral video: the standard OpenAI-compatible /v1/videos/text2video
    is tried FIRST for all providers; the config-hinted provider dialect is only a
    fallback. For a non-agnes provider that succeeds on standard, no dialect call
    is made."""
    from ai_engine import media as _m

    calls = []

    class _Resp:
        def __init__(self, sc):
            self.status_code = sc
        def json(self):
            return {"task_id": "t1"}
        @property
        def text(self):
            return ""

    class _Client:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, headers=None, json=None, content=None):
            calls.append(url)
            return _Resp(200)

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    out = _m.generate_video(
        base_url="https://plain.example.com/v1",
        api_key="k", model="video-model", prompt="a sunset",
        duration="5", aspect_ratio="16:9", proxy="")
    assert out.get("ok") is True
    # Standard endpoint tried first (and only).
    assert any("/v1/videos/text2video" in u for u in calls)
    assert not any(u.rstrip("/").endswith("/videos") and "text2video" not in u for u in calls), \
        f"non-agnes provider must not hit the dialect /videos: {calls}"


def test_generate_video_example_uses_manual_multipart_no_urllib3(monkeypatch):
    """generate_video_example must assemble multipart by hand (no urllib3 import),
    so it does not crash at runtime in an env where urllib3 is not installed."""
    import ai_engine.media as _mod
    import importlib
    from ai_engine import media as _m

    # urllib3 must NOT be referenced as a real import in media.py anymore.
    src = open(_mod.__file__, encoding="utf-8").read()
    assert "from urllib3.filepost import encode_multipart_formdata" not in src
    assert "import urllib3" not in src

    calls = []

    class _Resp:
        status_code = 200
        def json(self):
            return {"data": {"task_id": "t1"}}
        @property
        def text(self):
            return ""

    class _Client:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, headers=None, json=None, content=None):
            calls.append({"url": url, "content": content,
                          "ct": (headers or {}).get("Content-Type", "")})
            return _Resp()

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    out = _m.generate_video_example(
        base_url="https://plain.example.com/v1",
        api_key="k", model="video-model", prompt="extend this clip",
        example_b64="QUtFTVQ=", duration="5", aspect_ratio="16:9", proxy="")
    assert out.get("ok") is True
    assert len(calls) == 1
    assert isinstance(calls[0]["content"], (bytes, bytearray))
    assert "multipart/form-data; boundary=" in calls[0]["ct"]


def test_generate_video_403_quota_error_returns_friendly_code(monkeypatch):
    """When a video generation 403s with 'quota' in the body, the error code
    should be 'quota_exhausted' (not just 'unsupported'). This makes the UI
    able to show a friendlier message about billing/balance."""
    from ai_engine import media as _m

    class _Resp:
        def __init__(self, sc, body=None, text=""):
            self.status_code = sc
            self._body = body or {}
            self._text = text
        def json(self):
            return self._body
        @property
        def text(self):
            return self._text

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None, content=None):
            if "/v1/videos/text2video" in url:
                # Standard path fails with 400, forcing the dialect fallback
                return _Resp(400, {"error": "not found"}, "404")
            if "/videos" in url:
                # Agnes dialect path returns 403 quota
                return _Resp(403, {}, "Insufficient user quota")
            return _Resp(200)

    monkeypatch.setattr(_m, "_client", lambda proxy="", timeout=60.0: _Client())
    monkeypatch.setattr(_m, "_BASE_PROVIDER_HINTS", {"agnes": "img-agnes.example.com"})
    out = _m.generate_video(
        base_url="https://img-agnes.example.com/v1",
        api_key="k", model="agnes-video-2.5", prompt="a sunset",
        duration="5", aspect_ratio="16:9", proxy="")
    assert out.get("ok") is False
    assert out.get("code") == "quota_exhausted", f"expected quota_exhausted, got {out.get('code')}"
    assert "Insufficient" in out.get("error", "") or "баланс" in out.get("error", "").lower()
