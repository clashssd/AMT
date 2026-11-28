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
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import ai_engine.tool_registry as tool_registry  # noqa: E402


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
