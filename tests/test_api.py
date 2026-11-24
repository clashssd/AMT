"""End-to-end tests for all FastAPI endpoints in backend/main.py.

Uses TestClient with a fake httpx transport so no real network is needed.
The `tmp_backend` fixture (conftest) isolates all state.
"""
import json
import base64
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_backend, monkeypatch):
    """Fresh app + client with a fake httpx transport for the AI calls."""
    # Re-point module-level persistent paths at the tmp dirs. main.py reads env
    # at import time, but the fixture sets env after import, so re-assign here.
    main.memory = main.Memory(str(tmp_backend["mem_file"]))
    main.orchestrator = main.Orchestrator(str(tmp_backend["logs_dir"]), str(tmp_backend["settings_file"]))
    main.server_settings = main.Settings()
    main.SETTINGS_FILE = str(tmp_backend["settings_file"])
    main.LOG_DIR = str(tmp_backend["logs_dir"])
    main.CHATS_DIR = str(tmp_backend["chats_dir"])
    main.FILES_DIR = str(tmp_backend["files_dir"])
    main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp_backend["tmp"] / "keys.json"))
    main.SESSIONS_FILE = str(tmp_backend["tmp"] / "sessions.json")
    main.max_upload_limit = main.MAX_UPLOAD_BYTES
    # New managers
    main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp_backend["tmp"] / "keys.json"))

    app = main.app
    c = TestClient(app)
    yield c


# ---------- helpers to fake the upstream AI HTTP server ----------
def make_fake_ai(monkeypatch, responses):
    """Replace httpx.AsyncClient so .post/.get return canned responses.

    responses: dict with keys:
      "chat" -> list of httpx.Response-like or a callable
      "models" -> ...
    """
    class FakeResp:
        def __init__(self, status=200, payload=None, text=""):
            self.status_code = status
            self._payload = payload or {}
            self.text = text or json.dumps(self._payload)
            self.headers = {"retry-after": ""}
        def json(self):
            return self._payload

    class FakeClient:
        instances = []
        def __init__(self, **kw):
            self.kw = kw
            FakeClient.instances.append(self)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, headers=None, json=None, **kw):
            return _route("POST", url, headers, json)
        async def get(self, url, headers=None, **kw):
            return _route("GET", url, headers, None)

    def _route(method, url, headers, body):
        if url.rstrip("/").endswith("/models"):
            return FakeResp(200, responses.get("models", {"data": []}))
        if url.rstrip("/").endswith("/chat/completions"):
            # If the fake wants to record requests, do it here.
            if responses.get("on_request"):
                responses["on_request"]((method, url, headers, body))
            return responses.get("chat", FakeResp(200, {"choices": [{"message": {"content": "OK"}}], "usage": {"total_tokens": 5}}))
        return FakeResp(404, {}, "not found")

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    return FakeClient


# =============== SETTINGS ===============
def test_get_settings_no_key_leak(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    # apiKey must NOT appear in the response
    assert "apiKey" not in body
    assert "api_key" not in body
    assert "hasApiKey" in body
    assert body["hasApiKey"] is False


def test_get_settings_includes_new_fields(client):
    body = client.get("/api/settings").json()
    for key in ["baseUrl", "model", "systemPrompt", "temperature", "maxTokens", "contextWindow"]:
        assert key in body


def test_save_settings_persits_to_file(client, tmp_backend):
    r = client.post("/api/settings", json={"apiKey": "sk-123", "model": "gpt-4o", "maxTokens": 8000})
    assert r.json()["status"] == "saved"
    data = json.loads(tmp_backend["settings_file"].read_text())
    assert data["apiKey"] == "sk-123"
    assert data["maxTokens"] == 8000


def test_save_settings_keeps_old_key_when_empty(client, tmp_backend):
    # seed a key
    main.server_settings = main.Settings(apiKey="sk-existing")
    client.post("/api/settings", json={"apiKey": ""})
    # old key must be retained
    data = json.loads(tmp_backend["settings_file"].read_text())
    assert data["apiKey"] == "sk-existing"


def test_get_settings_reflects_saved(client, tmp_backend):
    client.post("/api/settings", json={"model": "qwen2.5"})
    assert client.get("/api/settings").json()["model"] == "qwen2.5"


# =============== CHAT ===============
def test_chat_without_key_returns_simulation(client, monkeypatch):
    main.server_settings = main.Settings(apiKey="")
    r = client.post("/api/chat", json={"message": "привет"})
    assert r.status_code == 200
    body = r.json()
    assert "Имитация" in body["response"]
    assert body["usage"] == {}


def test_chat_with_key_calls_ai_and_returns_usage(client, monkeypatch):
    captured = {}
    make_fake_ai(monkeypatch, {
        "chat": FakeResp_ok(),
        "on_request": lambda req: captured.setdefault("req", req),
    })
    # /api/chat uses the settings in the request body (frontend always sends them)
    r = client.post("/api/chat", json={
        "message": "привет", "history": [],
        "settings": {"apiKey": "sk-1", "baseUrl": "http://fake/v1", "model": "m"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["response"] == "Привет, я модель"
    assert body["usage"]["total_tokens"] == 42
    # verify the upstream request carried the Bearer key
    method, url, headers, jsonbody = captured["req"]
    assert headers["Authorization"] == "Bearer sk-1"
    assert jsonbody["model"] == "m"
    assert url.endswith("/chat/completions")


class FakeResp_ok:
    status_code = 200
    def json(self):
        return {"choices": [{"message": {"content": "Привет, я модель"}}], "usage": {"total_tokens": 42}}


def test_chat_api_error_500(client, monkeypatch):
    class ErrResp:
        status_code = 500
        text = "boom"
        headers = {"retry-after": ""}
        def json(self): return {}
    make_fake_ai(monkeypatch, {"chat": ErrResp()})
    r = client.post("/api/chat", json={
        "message": "hi",
        "settings": {"apiKey": "sk-1", "baseUrl": "http://fake/v1", "model": "m"},
    })
    assert r.status_code == 500


def test_chat_memory_injected_into_system_prompt(client, monkeypatch):
    main.memory.add_fact("user is a dev")
    captured = {}
    make_fake_ai(monkeypatch, {"chat": FakeResp_ok(), "on_request": lambda r: captured.setdefault("req", r)})
    client.post("/api/chat", json={
        "message": "hi",
        "settings": {"apiKey": "sk-1", "baseUrl": "http://fake/v1", "model": "m"},
    })
    m, u, h, jb = captured["req"]
    sent_msgs = jb["messages"]
    system_msgs = [mm for mm in sent_msgs if mm["role"] == "system"]
    assert any("user is a dev" in mm["content"] for mm in system_msgs)


# =============== TEST-CONNECTION ===============
def test_connection_no_key(client):
    r = client.post("/api/test-connection", json={"settings": {"apiKey": ""}})
    assert r.json()["ok"] is False
    assert "не задан" in r.json()["message"].lower() or "заполни" in r.json()["message"].lower()


def test_connection_ok(client, monkeypatch):
    make_fake_ai(monkeypatch, {"chat": FakeResp_ok()})
    r = client.post("/api/test-connection", json={"settings": {"apiKey": "sk", "baseUrl": "http://fake/v1"}})
    assert r.json()["ok"] is True


# =============== MODELS ===============
def test_models_no_key(client):
    main.server_settings = main.Settings(apiKey="")
    r = client.post("/api/models/test")
    assert r.json()["ok"] is False


def test_models_parsing_capabilities(client, monkeypatch):
    main.server_settings = main.Settings(apiKey="sk", baseUrl="http://fake/v1")
    models_payload = {"data": [
        {"id": "gpt-4o", "created": 1},
        {"id": "dall-e-3", "created": 1},
        {"id": "whisper-1", "created": 1},
        {"id": "text-embedding-ada-002", "created": 1},
    ]}
    make_fake_ai(monkeypatch, {"models": models_payload})
    r = client.post("/api/models/test")
    assert r.json()["ok"] is True
    by_id = {m["id"]: m for m in r.json()["models"]}
    assert "text_generation" in by_id["gpt-4o"]["capabilities"]
    assert "image_generation" in by_id["gpt-4o"]["capabilities"]
    assert "image_generation" in by_id["dall-e-3"]["capabilities"]
    assert "audio" in by_id["whisper-1"]["capabilities"]
    assert "embeddings" in by_id["text-embedding-ada-002"]["capabilities"]


# =============== MEMORY WIPE ===============
def test_memory_wipe(client, tmp_backend):
    main.memory.add_fact("x")
    assert len(main.memory.facts) == 1
    r = client.post("/api/memory/wipe")
    assert r.json()["status"] == "wiped"
    assert main.memory.facts == []
    assert json.loads(tmp_backend["mem_file"].read_text())["facts"] == []


# =============== ORCHESTRATOR ===============
def test_orch_config_get(client):
    r = client.get("/api/orchestrator/config")
    assert r.status_code == 200
    assert "config" in r.json() and "health" in r.json()


def test_orch_config_set(client, tmp_backend):
    r = client.post("/api/orchestrator/config", json={"auto_mode": False, "enabled": False})
    assert r.json()["status"] == "updated"
    assert r.json()["config"]["auto_mode"] is False
    # persisted
    data = json.loads(tmp_backend["settings_file"].read_text())
    assert data["orchestrator"]["auto_mode"] is False


def test_orch_health(client):
    r = client.get("/api/orchestrator/health")
    assert "total_requests" in r.json()


# =============== LOGS ===============
def test_logs_returns_lines(client, tmp_backend):
    # trigger a log line via a chat request (simulation logs REQUEST? only real path)
    # Instead, write directly to today's log and read back
    from datetime import datetime
    log_path = tmp_backend["logs_dir"] / f"chat_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_path.write_text("12:00:00  [TEST] hello=world\n")
    r = client.get("/api/logs")
    assert any("TEST" in line for line in r.json()["lines"])


def test_logs_empty_when_no_file(client, tmp_backend):
    # Point main's LOG_DIR at an empty dir by ensuring no log file exists today
    from datetime import datetime
    log_path = tmp_backend["logs_dir"] / f"chat_{datetime.now().strftime('%Y-%m-%d')}.log"
    if log_path.exists():
        log_path.unlink()
    r = client.get("/api/logs")
    assert r.json()["lines"] == []


# =============== CHAT SAVE ===============
def test_chats_save(client, tmp_backend):
    payload = {"chats": [{"id": "c1", "title": "t", "messages": []}]}
    r = client.post("/api/chats/save", json=payload)
    assert r.json()["status"] == "saved"
    assert r.json()["count"] == 1
    stored = json.loads((tmp_backend["chats_dir"] / "all_chats.json").read_text())
    assert stored == payload["chats"]
