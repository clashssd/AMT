"""Tests for the newer feature endpoints: batch import, sessions, chat search,
explicit key binding in chat, and agent/skill model param application."""
import json
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_backend, monkeypatch):
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
    yield TestClient(main.app)


# ============ BATCH IMPORT ============
def test_batch_import_agents_and_skills(client):
    payload = {
        "agents": [
            {"id": "arch", "name": "Архитектор", "systemPrompt": "Ты архитектор", "model": "gpt-4o"},
            {"name": "Без Id"},
        ],
        "skills": [
            {"id": "review", "name": "Код-ревью", "prompt": "Ревьюируй код"},
            {"name": "Без Id", "prompt": "x" * 10},
        ],
    }
    r = client.post("/api/import/batch", json=payload)
    assert r.json()["status"] == "ok"
    assert r.json()["imported_agents"] == 2
    assert r.json()["imported_skills"] == 2
    # verify persisted
    listing = client.get("/api/agents").json()
    ids = [a["id"] for a in listing["agents"]]
    assert "arch" in ids
    assert "review" in [s["id"] for s in listing["skills"]]


def test_batch_import_skips_existing_when_not_overwrite(client):
    client.post("/api/agents", json={"name": "Дубликат", "systemPrompt": "old"})
    r = client.post("/api/import/batch", json={
        "agents": [{"name": "Дубликат", "systemPrompt": "new"}]
    })
    # No id -> gets a new id, so it's a new agent. To test skip, use same id:
    listing = client.get("/api/agents").json()
    dup = next(a for a in listing["agents"] if a["name"] == "Дубликат" and a["id"].startswith("a_"))
    r2 = client.post("/api/import/batch", json={
        "agents": [{"id": dup["id"], "name": "Дубликат", "systemPrompt": "new"}]
    })
    assert r2.json()["skipped"] == 1
    # content unchanged (no overwrite)
    listing2 = client.get("/api/agents").json()
    dup2 = next(a for a in listing2["agents"] if a["id"] == dup["id"])
    assert dup2["systemPrompt"] == "old"


def test_batch_import_overwrite(client):
    client.post("/api/agents", json={"name": "Тест", "systemPrompt": "old"})
    listing = client.get("/api/agents").json()
    a = next(x for x in listing["agents"] if x["name"] == "Тест")
    client.post("/api/import/batch", json={
        "agents": [{"id": a["id"], "name": "Тест", "systemPrompt": "new"}], "overwrite": True
    })
    listing2 = client.get("/api/agents").json()
    a2 = next(x for x in listing2["agents"] if x["id"] == a["id"])
    assert a2["systemPrompt"] == "new"


def test_batch_import_ignores_empty(client):
    r = client.post("/api/import/batch", json={"agents": [{"name": ""}], "skills": []})
    assert r.json()["imported_agents"] == 0


# ============ SESSIONS ============
def test_create_and_list_sessions(client):
    r = client.post("/api/sessions", json={"name": "Моя сессия", "mode": "new_personality", "key_id": "k1", "agent_id": "arch"})
    assert r.json()["status"] == "created"
    sid = r.json()["session"]["id"]
    listing = client.get("/api/sessions").json()
    assert any(s["id"] == sid for s in listing["sessions"])
    s = next(x for x in listing["sessions"] if x["id"] == sid)
    assert s["keyId"] == "k1"
    assert s["agentId"] == "arch"
    assert s["mode"] == "new_personality"


def test_delete_session(client):
    r = client.post("/api/sessions", json={"name": "tmp"}).json()
    sid = r["session"]["id"]
    d = client.delete(f"/api/sessions/{sid}")
    assert d.json()["status"] == "deleted"
    listing = client.get("/api/sessions").json()
    assert not any(s["id"] == sid for s in listing["sessions"])


def test_delete_missing_session(client):
    assert client.delete("/api/sessions/nonexistent").json()["status"] == "not_found"


# ============ CHAT SEARCH ============
def test_search_finds_message(client, tmp_backend):
    # write a chats file with content
    chats_file = tmp_backend["chats_dir"] / "all_chats.json"
    chats = [{"id": "c1", "title": "Про Python", "messages": [
        {"role": "user", "content": "Как написать сортировку?"},
        {"role": "assistant", "content": "Используй quicksort на Python."},
    ]}]
    chats_file.write_text(json.dumps(chats))
    r = client.get("/api/chats/search", params={"q": "quicksort"})
    matches = r.json()["matches"]
    assert len(matches) >= 1
    assert any(m["chatId"] == "c1" and "quicksort" in m["snippet"] for m in matches)


def test_search_case_insensitive(client, tmp_backend):
    chats_file = tmp_backend["chats_dir"] / "all_chats.json"
    chats_file.write_text(json.dumps([{"id": "c2", "title": "Т", "messages": [{"role": "user", "content": "HELLO WORLD"}]}]))
    r = client.get("/api/chats/search", params={"q": "hello"})
    assert any(m["chatId"] == "c2" for m in r.json()["matches"])


def test_search_empty_query_returns_empty(client, tmp_backend):
    r = client.get("/api/chats/search", params={"q": ""})
    assert r.json()["matches"] == []


def test_search_no_file_returns_empty(client):
    r = client.get("/api/chats/search", params={"q": "anything"})
    assert r.json()["matches"] == []


def test_search_scope_to_chat(client, tmp_backend):
    chats_file = tmp_backend["chats_dir"] / "all_chats.json"
    chats_file.write_text(json.dumps([
        {"id": "c1", "messages": [{"role": "user", "content": "unique-needle"}]},
        {"id": "c2", "messages": [{"role": "user", "content": "unique-needle"}]},
    ]))
    r = client.get("/api/chats/search", params={"q": "unique-needle", "chat_id": "c1"})
    matches = r.json()["matches"]
    assert all(m["chatId"] == "c1" for m in matches)
    assert len(matches) == 1


# ============ EXPLICIT KEY BINDING IN CHAT ============
def test_chat_with_explicit_key_uses_that_key(client, monkeypatch):
    """A key_id in the request must be used, even if another key is active."""
    main.keys_mgr.add_key({"id": "kA", "label": "A", "baseUrl": "http://A/v1", "apiKey": "sk-A", "model": "mA"})
    main.keys_mgr.add_key({"id": "kB", "label": "B", "baseUrl": "http://B/v1", "apiKey": "sk-B", "model": "mB"})
    main.keys_mgr.set_active("kA")

    calls = []
    class FakeResp:
        status_code = 200
        headers = {"retry-after": ""}
        text = "{}"
        def json(self): return {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, **kw):
            calls.append((url, headers))
            return FakeResp()
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)

    # Force explicit key B while active is A
    client.post("/api/chat", json={
        "message": "hi", "key_id": "kB",
        "settings": {"apiKey": ""},  # empty inline, must fall through to key manager
    })
    url, headers = calls[0]  # first call = the main chat completion
    assert headers["Authorization"] == "Bearer sk-B"
    assert "http://B/v1" in url


def test_system_prompt_override_for_new_personality(client, monkeypatch):
    """systemPromptOverride replaces the base system prompt (new personality)."""
    main.keys_mgr.add_key({"id": "k1", "baseUrl": "http://x/v1", "apiKey": "sk", "model": "m"})
    captured = {}
    calls = []
    class FakeResp:
        status_code = 200
        headers = {"retry-after": ""}
        text = "{}"
        def json(self): return {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, **kw):
            calls.append(json)
            return FakeResp()
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)

    client.post("/api/chat", json={
        "message": "привет",
        # baseUrl set explicitly (provider-neutral test data — no implicit default).
        "settings": {"systemPrompt": "Я базовый ассистент", "apiKey": "sk",
                      "baseUrl": "http://fake.example/v1"},
        "systemPromptOverride": "Я — Пират-капитан, отвечаю с характером",
    })
    # The FIRST post is the main chat completion; later ones are fact extraction.
    msgs = calls[0]["messages"]
    sys_msgs = [m for m in msgs if m["role"] == "system"]
    assert any("Пират-капитан" in m["content"] for m in sys_msgs)
    assert not any(m["content"].startswith("Я базовый ассистент") for m in sys_msgs)


# ============ AGENT MODEL PARAM APPLICATION ============
def test_agent_params_override_model(client, monkeypatch):
    """An agent's model/temperature override the request settings."""
    main.keys_mgr.add_key({"id": "k1", "baseUrl": "http://x/v1", "apiKey": "sk", "model": "default-model"})
    main.agents_mgr.add_agent({"id": "ag1", "name": "Точный", "model": "gpt-4o", "temperature": 0.1})
    calls = []
    class FakeResp:
        status_code = 200
        headers = {"retry-after": ""}
        text = "{}"
        def json(self): return {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, **kw):
            calls.append(json)
            return FakeResp()
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)

    client.post("/api/chat", json={
        "message": "hi", "agent_id": "ag1",
        # baseUrl set explicitly (provider-neutral test data — no implicit default).
        "settings": {"apiKey": "sk", "baseUrl": "http://fake.example/v1",
                      "model": "should-be-overridden", "temperature": 0.9},
    })
    body = calls[0]
    assert body["model"] == "gpt-4o"        # agent model wins
    assert body["temperature"] == 0.1        # agent temp wins
