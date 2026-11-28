# tests/test_provider_store.py
"""Regression: provider-neutral media provider templates (backend/providers.json).

Pins three behaviors:
  1. ProviderStore encrypts the api_key at rest (Fernet), never persists plaintext.
  2. The media credential resolver (_media_cfg) picks up the ACTIVE provider when
     dedicated + global keys are empty — so any provider added via the UI drives
     image/video/audio generation.
  3. resolve_dialect in media.py honors the active provider's dialect flags so the
     provider-neutral layer works for arbitrary providers, not just host-hint auto-detect.

These tests are ORDERING-SAFE: they redirect AMT_PROVIDERS_FILE to a temp path and
blank the global/dedicated keys so prior tests can't pollute the result.
"""
import json
import os


def _point_providers_to(tmp_path, monkeypatch, doc=None):
    """Redirect main.PROVIDERS_FILE + media's provider-file lookup to a temp file,
    and re-instantiate main.providers_store so the module-level instance points
    at the temp path. Returns the temp file path."""
    import main
    from ai_engine import media
    providers_file = tmp_path / "providers.json"
    if doc is not None and not providers_file.exists():
        providers_file.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("AMT_PROVIDERS_FILE", str(providers_file))
    monkeypatch.setattr(main, "PROVIDERS_FILE", str(providers_file))
    # media.resolve_dialect reads the path from env each call, so just env is
    # enough; but re-instantiate the store on main so get_active() uses temp.
    from ai_engine.provider_store import ProviderStore
    main.providers_store = ProviderStore(str(providers_file))
    return providers_file


def _clean_settings(monkeypatch):
    import main
    s = main.Settings(**{k: "" for k in (
        "baseUrl", "apiKey", "model",
        "imageKey", "imageBaseUrl", "imageModel",
        "videoKey", "videoBaseUrl", "videoModel",
        "audioKey", "audioBaseUrl", "audioModel")})
    monkeypatch.setattr(main, "server_settings", s)
    monkeypatch.setattr(main, "load_persisted_settings", lambda: None)
    from ai_engine.tool_registry import set_active_chat_media
    set_active_chat_media("", "", "")
    return s


def test_provider_key_encrypted_at_rest(tmp_backend, monkeypatch):
    """Adding a provider stores a Fernet token, not the plaintext key."""
    import main
    _point_providers_to(tmp_backend["tmp"], monkeypatch)
    _clean_settings(monkeypatch)

    main.providers_store.add({
        "name": "Agnes",
        "base_url": "https://apihub.agnes-ai.com",
        "api_key": "sk-plain-secret",
        "capabilities": {"image": True, "video": True, "audio": False},
        "dialect": {"extra_body_ref": True, "v1_suffix": True, "return_base64": True},
    })
    raw = json.loads(tmp_backend["tmp"].joinpath("providers.json").read_text(encoding="utf-8"))
    prov = raw["providers"][0]
    assert "api_key" not in prov, "plaintext key must not be persisted"
    assert prov["api_key_enc"], "encrypted key must be stored"
    assert prov["api_key_enc"] != "sk-plain-secret"
    # And it round-trips through get_active().
    active = main.providers_store.get_active()
    assert active["api_key"] == "sk-plain-secret"
    # Public list never exposes the plaintext.
    pub = main.providers_store.list_public()
    assert pub[0]["hasKey"] is True
    assert pub[0].get("api_key", "") == ""


def test_active_provider_drives_media_credentials(tmp_backend, monkeypatch):
    """When dedicated + global keys are empty, the ACTIVE provider supplies the
    key/base/model so generate_image actually works with any provider."""
    import main
    _point_providers_to(tmp_backend["tmp"], monkeypatch)
    _clean_settings(monkeypatch)

    main.providers_store.add({
        "name": "Agnes",
        "base_url": "https://apihub.agnes-ai.com",
        "api_key": "sk-agnes-live",
        "model": "img-agnes",
        "capabilities": {"image": True, "video": True, "audio": False},
        "dialect": {"extra_body_ref": True},
    })
    pid = main.providers_store.list_public()[0]["id"]
    main.providers_store.set_active(pid)

    from ai_engine.tool_registry import _media_cfg
    cfg = _media_cfg("image")
    assert cfg["key"] == "sk-agnes-live"
    assert cfg["base"].startswith("https://apihub.agnes-ai.com")
    assert cfg["model"] == "img-agnes"


def test_active_provider_respects_capabilities(tmp_backend, monkeypatch):
    """A provider that only enables image must NOT satisfy an audio request."""
    import main
    _point_providers_to(tmp_backend["tmp"], monkeypatch)
    _clean_settings(monkeypatch)

    main.providers_store.add({
        "name": "ImageOnly",
        "base_url": "https://img.example",
        "api_key": "sk-imgonly",
        "capabilities": {"image": True, "video": False, "audio": False},
    })
    pid = main.providers_store.list_public()[0]["id"]
    main.providers_store.set_active(pid)

    from ai_engine.tool_registry import _media_cfg
    assert _media_cfg("image")["key"] == "sk-imgonly"
    # Audio not enabled -> provider must not be used for audio.
    assert _media_cfg("audio")["key"] != "sk-imgonly"


def test_resolve_dialect_from_active_provider(tmp_backend, monkeypatch):
    """resolve_dialect() picks up the active provider template's dialect flags so
    the media layer works for arbitrary providers (provider-neutral), not just
    the built-in host-hint auto-detect."""
    from ai_engine import media
    _point_providers_to(
        tmp_backend["tmp"], monkeypatch,
        doc={"providers": [{
            "id": "p_x", "name": "X", "base_url": "https://x.example",
            "capabilities": {"image": True, "video": True, "audio": False},
            "dialect": {"extra_body_ref": True, "v1_suffix": True,
                        "return_base64": True, "videos_mode_body": True,
                        "agnesapi_poll": True, "stt": False, "xi_api_key": False},
        }], "activeId": "p_x"})

    d = media.resolve_dialect("https://x.example")
    assert d["extra_body_ref"] is True
    assert d["v1_suffix"] is True
    assert d["videos_mode_body"] is True
    assert d["xi_api_key"] is False
    # A host with no active template + no built-in hint -> all default (False).
    unknown = media.resolve_dialect("https://some.random.host")
    assert unknown["extra_body_ref"] is False
    assert unknown["xi_api_key"] is False
