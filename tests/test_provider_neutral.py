"""Provider-neutrality regression tests.

Pins the invariant that the app does NOT assume a specific provider
(OpenAI etc.) by default:
  * Settings defaults are empty (no baked-in base_url / model).
  * A user-provided non-OpenAI base_url flows through untouched.
  * model passes through as-is.
  * Empty base_url with a key -> graceful "need base url", not a crash.
"""
import pytest

import main
from main import Settings


# ---------- Settings defaults ----------

def test_settings_defaults_are_neutral():
    s = Settings()
    assert s.baseUrl == "", "Settings must not assume a provider base_url by default"
    assert s.apiKey == ""
    assert s.model == "", "Settings must not assume a provider model by default"


def test_settings_accepts_non_openai_baseurl():
    s = Settings(baseUrl="https://api.deepseek.com/v1", model="deepseek-chat")
    assert s.effective_base_url == "https://api.deepseek.com/v1"
    assert s.effective_model == "deepseek-chat"
    # Round-trip through the model (no mutation)
    s2 = Settings.model_validate(s.model_dump())
    assert s2.baseUrl == "https://api.deepseek.com/v1"
    assert s2.model == "deepseek-chat"


def test_settings_empty_is_treated_as_not_customized():
    # The old logic compared against the OpenAI default URL as a "sentinel".
    # Now "not customized" simply means empty. An empty base_url must NOT
    # be mistaken for a real configured URL.
    s = Settings(baseUrl="")
    assert not s.effective_base_url


# ---------- Call path: base_url resolution ----------

def test_call_ai_api_no_base_url_is_graceful(tmp_backend, monkeypatch):
    """A key without base_url must return the 'need base url' imitation,
    not raise or build a relative URL."""
    c = _make_client(tmp_backend, monkeypatch)
    req = {
        "message": "hi",
        "history": [],
        "settings": {
            "baseUrl": "",
            "apiKey": "sk-test-neutral",
            "model": "some-model",
        },
    }
    r = c.post("/api/chat", json=req)
    assert r.status_code == 200
    body = r.json()
    text = body.get("response", "")
    # Graceful imitation explaining the missing Base URL — NOT a 500/exception,
    # and NOT a silently-built relative URL.
    assert "Base URL" in text or "имитация" in text.lower()


def _make_client(tmp_backend, monkeypatch):
    from fastapi.testclient import TestClient
    main.server_settings = main.Settings()
    main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp_backend["tmp"] / "keys.json"))
    return TestClient(main.app)


def test_non_openai_baseurl_not_mutated(tmp_backend, monkeypatch):
    """When the user explicitly sets a non-OpenAI base_url, it must be used
    verbatim (no provider re-routing / no OpenAI sentinel interference)."""
    s = Settings(baseUrl="https://myprovider.example/v1", apiKey="k", model="m")
    assert s.effective_base_url == "https://myprovider.example/v1"
    # The "customized?" check must be true for ANY non-empty URL
    settings_url = (s.baseUrl or "").strip()
    settings_has_url = bool(settings_url)
    assert settings_has_url is True
