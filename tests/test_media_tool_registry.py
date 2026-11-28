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
