"""Tests for the 4 media endpoint-path settings fields (mediaPath*).

Covers:
- /api/settings GET returns the 4 keys.
- /api/settings POST preserves server-side values when the request omits/empties them.
- /api/settings POST sets a new value when provided.
"""
import main as app_mod
from fastapi.testclient import TestClient


def _fresh_client():
    app_mod.server_settings = app_mod.Settings()
    return TestClient(app_mod.app)


def test_settings_get_has_path_fields():
    c = _fresh_client()
    r = c.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    for k in ("mediaPathText", "mediaPathImage", "mediaPathTextImage", "mediaPathVoice",
              "mediaPathVideo"):
        assert k in body, f"GET /api/settings missing key {k}"
        assert body[k] == "", f"expected empty default for {k}, got {body[k]!r}"


def test_settings_post_preserves_paths_when_empty():
    c = _fresh_client()
    app_mod.server_settings.mediaPathText = "seed/text/path"
    r = c.post("/api/settings", json={"mediaPathText": ""})
    assert r.status_code == 200
    assert app_mod.server_settings.mediaPathText == "seed/text/path"


def test_settings_post_sets_paths():
    c = _fresh_client()
    r = c.post("/api/settings", json={"mediaPathVoice": "v1/audio/custom"})
    assert r.status_code == 200
    assert app_mod.server_settings.mediaPathVoice == "v1/audio/custom"


def test_settings_post_sets_video_path():
    c = _fresh_client()
    r = c.post("/api/settings", json={"mediaPathVideo": "v1/videos/custom"})
    assert r.status_code == 200
    assert app_mod.server_settings.mediaPathVideo == "v1/videos/custom"


def test_settings_defaults_provider_neutral():
    """All media path fields default to empty (no baked-in provider path)."""
    s = app_mod.Settings()
    assert s.mediaPathText == ""
    assert s.mediaPathImage == ""
    assert s.mediaPathTextImage == ""
    assert s.mediaPathVoice == ""
    assert s.mediaPathVideo == ""
