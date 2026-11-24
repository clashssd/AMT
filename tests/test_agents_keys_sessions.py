"""Tests for agents/skills, multi-key manager, sessions, and chat search.

Uses the existing `client` + `tmp_backend` fixtures pattern (env isolation).
"""
import json
import os
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def c(tmp_backend, monkeypatch):
    tmp = tmp_backend["tmp"]
    main.agents_mgr = main.AgentSkillManager(str(tmp / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp / "keys.json"))
    main.memory = main.Memory(str(tmp / "memory.json"))
    main.server_settings = main.Settings()
    main.SESSIONS_FILE = str(tmp / "sessions.json")
    return TestClient(main.app)


# ---------- Agents / Skills ----------
def test_create_and_list_skill(c):
    r = c.post("/api/skills", json={"name": "Ревью", "prompt": "проверь код"})
    assert r.json()["status"] == "created"
    sid = r.json()["skill"]["id"]
    data = c.get("/api/agents").json()
    assert any(s["id"] == sid for s in data["skills"])


def test_create_agent_with_skills(c):
    sk = c.post("/api/skills", json={"name": "S", "prompt": "p"}).json()["skill"]["id"]
    r = c.post("/api/agents", json={"name": "Dev", "systemPrompt": "Ты dev", "skills": [sk]})
    aid = r.json()["agent"]["id"]
    agent = main.agents_mgr.get_agent(aid)
    assert sk in agent["skills"]


def test_build_system_prompt_composes_skills(c):
    sk = c.post("/api/skills", json={"name": "Код", "prompt": "ИНСТРУКЦИЯ-КОД"}).json()["skill"]["id"]
    c.post("/api/agents", json={"name": "A", "systemPrompt": "РОЛЬ-БАЗА", "skills": [sk]})
    aid = main.agents_mgr.list_agents()[0]["id"]
    prompt = main.agents_mgr.build_system_prompt(aid)
    assert "РОЛЬ-БАЗА" in prompt
    assert "ИНСТРУКЦИЯ-КОД" in prompt
    assert "[Скилл: Код]" in prompt


def test_agent_model_params(c):
    c.post("/api/agents", json={"name": "M", "model": "gpt-4o", "temperature": 0.2})
    aid = main.agents_mgr.list_agents()[0]["id"]
    params = main.agents_mgr.agent_model_params(aid)
    assert params["model"] == "gpt-4o"
    assert params["temperature"] == 0.2


def test_delete_skill_removes_from_agents(c):
    sk = c.post("/api/skills", json={"name": "S", "prompt": "p"}).json()["skill"]["id"]
    c.post("/api/agents", json={"name": "A", "skills": [sk]})
    aid = main.agents_mgr.list_agents()[0]["id"]
    c.delete(f"/api/skills/{sk}")
    agent = main.agents_mgr.get_agent(aid)
    assert sk not in agent["skills"]


def test_batch_import(c):
    data = json.dumps({
        "agents": [{"name": "ImportA", "systemPrompt": "sp"}],
        "skills": [{"name": "ImportS", "prompt": "pp"}],
    })
    r = c.post("/api/import/batch", json={"agents": json.loads(data)["agents"], "skills": json.loads(data)["skills"]})
    assert r.json()["imported_agents"] == 1
    assert r.json()["imported_skills"] == 1


def test_import_from_text_jsonl(c):
    text = '\n'.join([
        json.dumps({"name": "L1", "systemPrompt": "сп"}),
        json.dumps({"name": "S1", "prompt": "пр"}),
    ])
    r = c.post("/api/import/batch-from-text", json={"text": text})
    assert r.json()["imported_agents"] == 1
    assert r.json()["imported_skills"] == 1


def test_import_from_text_full_json(c):
    text = json.dumps({"agents": [{"name": "A1"}], "skills": [{"name": "S1", "prompt": "x"}]})
    r = c.post("/api/import/batch-from-text", json={"text": text})
    assert r.json()["imported_agents"] == 1
    assert r.json()["imported_skills"] == 1


# ---------- Multi-key ----------
def test_keys_crud_and_no_secret_leak(c):
    r = c.post("/api/keys", json={"label": "OpenAI", "baseUrl": "https://api.openai.com/v1",
                                   "apiKey": "sk-TOP-SECRET", "model": "gpt-4o-mini"})
    assert r.json()["status"] == "created"
    listed = c.get("/api/keys")
    # the raw secret must NOT be in the public listing
    assert "sk-TOP-SECRET" not in listed.text
    assert listed.json()["keys"][0]["hasKey"] is True


def test_key_activate_and_rotate(c):
    k1 = c.post("/api/keys", json={"label": "A", "apiKey": "sk-1", "makeActive": True}).json()["key"]["id"]
    k2 = c.post("/api/keys", json={"label": "B", "apiKey": "sk-2"}).json()["key"]["id"]
    c.post(f"/api/keys/{k2}/activate")
    assert c.get("/api/keys").json()["activeKeyId"] == k2
    # rotate -> back to k1 (k2 excluded)
    c.post("/api/keys/rotate")
    assert c.get("/api/keys").json()["activeKeyId"] == k1


def test_rate_limit_marks_cooldown(c, monkeypatch):
    k = c.post("/api/keys", json={"label": "X", "apiKey": "sk-x"}).json()["key"]["id"]
    main.keys_mgr.mark_rate_limited(k, retry_after=60)
    import time
    assert main.keys_mgr.get_key(k)["cooldownUntil"] > time.time()


def test_delete_active_key_resets(c):
    k1 = c.post("/api/keys", json={"label": "A", "apiKey": "sk-1", "makeActive": True}).json()["key"]["id"]
    c.post("/api/keys", json={"label": "B", "apiKey": "sk-2"})
    c.delete(f"/api/keys/{k1}")
    assert c.get("/api/keys").json()["activeKeyId"] != k1


# ---------- Sessions ----------
def test_session_create_modes(c):
    for mode in ["continue", "new_personality", "reuse_key"]:
        r = c.post("/api/sessions", json={"name": "S", "mode": mode})
        assert r.json()["status"] == "created"
        assert r.json()["session"]["mode"] == mode
    assert len(c.get("/api/sessions").json()["sessions"]) == 3


def test_session_delete(c):
    sid = c.post("/api/sessions", json={"name": "Del"}).json()["session"]["id"]
    assert c.delete(f"/api/sessions/{sid}").json()["status"] == "deleted"


# ---------- Chat search ----------
def test_search_over_saved_chats(c, tmp_backend):
    chats = [
        {"id": "c1", "title": "Python вопросы", "messages": [
            {"role": "user", "content": "как сделать list comprehension?"},
            {"role": "assistant", "content": "Вот пример: [x*2 for x in nums]"}]},
        {"id": "c2", "title": "Рецепты", "messages": [
            {"role": "user", "content": "как испечь пиццу"}]},
    ]
    c.post("/api/chats/save", json={"chats": chats})
    r = c.get("/api/chats/search", params={"q": "list comprehension"})
    assert r.json()["matches"], "should find a match"
    assert any(m["chatId"] == "c1" for m in r.json()["matches"])


def test_search_no_match(c, tmp_backend):
    c.post("/api/chats/save", json={"chats": [{"id": "c1", "title": "X", "messages": []}]})
    assert c.get("/api/chats/search", params={"q": "нет-такого"}).json()["matches"] == []
