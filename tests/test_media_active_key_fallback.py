# tests/test_media_active_key_fallback.py
"""Regression: media tool-calling must fall back to the ACTIVE CHAT KEY.

Root cause being pinned: when a user chats with a multi-key (keys.json) or a
session key_id, the LLM's active key works for chat but the media handlers
(_media_cfg) only read server_settings.imageKey/apiKey. If those are empty,
generate_image wrongly returns {"ok":false,"code":"no_key"} and the model then
explains in plain text why it can't do image-to-image.

Fix: main.py pushes the active chat key via set_active_chat_media(); _media_cfg
uses it as the LAST fallback when dedicated + global keys are empty.

These tests are ORDERING-SAFE: they monkeypatch _media_cfg's settings source
(the in-memory server_settings object AND the disk-reload path) so prior tests
cannot pollute the result.
"""
import json


def _clean_settings(monkeypatch, **overrides):
    """Build a fresh main.Settings with keys/bases/models blanked out and
    redirect the disk-reload so it can't reintroduce state from a previous
    test. Returns the Settings object to point _media_cfg at."""
    import main
    s = main.Settings(**{k: "" for k in (
        "baseUrl", "apiKey", "model",
        "imageKey", "imageBaseUrl", "imageModel",
        "videoKey", "videoBaseUrl", "videoModel",
        "audioKey", "audioBaseUrl", "audioModel")})
    for k, v in overrides.items():
        setattr(s, k, v)
    # Point the module-global server_settings at this clean object for the
    # duration of the test, and disable the on-disk reload that would clobber
    # our in-memory state.
    monkeypatch.setattr(main, "server_settings", s)
    monkeypatch.setattr(main, "load_persisted_settings", lambda: None)
    return s


def test_active_chat_key_is_media_fallback(tmp_backend, monkeypatch):
    import main
    from ai_engine.tool_registry import _media_cfg, set_active_chat_media

    _clean_settings(monkeypatch, baseUrl="https://api.openai.com/v1")

    # Nothing set yet -> empty key.
    set_active_chat_media("", "", "")
    cfg = _media_cfg("image")
    assert cfg["key"] == "", "no key expected when chat key not set"

    # Now the user is chatting with a working multi-key. main.py records it.
    set_active_chat_media("https://agnesapi.example/v1", "sk-live-multi-key", "agnes-3.0")
    cfg = _media_cfg("image")
    assert cfg["key"] == "sk-live-multi-key"
    # No dedicated image base -> chat base wins over the generic chat baseUrl.
    assert cfg["base"].startswith("https://agnesapi.example")
    # No global image model or global model -> chat model is the fallback.
    assert cfg["model"] == "agnes-3.0"


def test_dedicated_image_key_wins_over_chat_key(tmp_backend, monkeypatch):
    """A real imageKey in settings must NOT be shadowed by the active chat key."""
    import main
    from ai_engine.tool_registry import _media_cfg, set_active_chat_media

    _clean_settings(monkeypatch, imageKey="sk-dedicated-image",
                    imageBaseUrl="https://img.example/v1")
    set_active_chat_media("https://chat.example", "sk-chat", "chat-model")
    cfg = _media_cfg("image")
    assert cfg["key"] == "sk-dedicated-image", "dedicated imageKey must win"
    assert cfg["base"].startswith("https://img.example")


def test_chat_key_fallback_for_video_and_audio(tmp_backend, monkeypatch):
    """The fallback applies to all media kinds, not just image."""
    import main
    from ai_engine.tool_registry import _media_cfg, set_active_chat_media

    _clean_settings(monkeypatch)
    set_active_chat_media("https://provider.example/v1", "sk-all", "m")
    assert _media_cfg("video")["key"] == "sk-all"
    assert _media_cfg("audio")["key"] == "sk-all"


def test_chat_key_fallback_does_not_overwrite_explicit_base(tmp_backend, monkeypatch):
    """If a dedicated base exists for the kind, the chat key fills only the key."""
    import main
    from ai_engine.tool_registry import _media_cfg, set_active_chat_media

    _clean_settings(monkeypatch, videoBaseUrl="https://video.example")
    set_active_chat_media("https://chat.example", "sk-chat", "chat-model")
    cfg = _media_cfg("video")
    assert cfg["key"] == "sk-chat"
    # Video's own dedicated base must be preserved, not clobbered by the chat base.
    assert cfg["base"] == "https://video.example"
