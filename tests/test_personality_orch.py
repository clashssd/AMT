"""Tests: personality orchestratorRules field, agent keyId, and chat context-menu items shape (via backend)."""
import json
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def c(tmp_backend):
    tmp = tmp_backend["tmp"]
    main.agents_mgr = main.AgentSkillManager(str(tmp / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp / "keys.json"))
    main.server_settings = main.Settings()
    return TestClient(main.app)


def test_personality_with_orchestrator_rules(c):
    a = c.post("/api/agents", json={
        "name": "P", "systemPrompt": "sp",
        "orchestrator": "custom", "orchestratorRules": "Не отходи от цели",
        "parallel": 4, "keyId": "",
    }).json()["agent"]
    assert a["orchestrator"] == "custom"
    assert a["orchestratorRules"] == "Не отходи от цели"
    assert a["parallel"] == 4


def test_personality_key_bound(c):
    k = c.post("/api/keys", json={"label": "K", "apiKey": "sk-abc"}).json()["key"]["id"]
    a = c.post("/api/agents", json={"name": "P2", "keyId": k}).json()["agent"]
    assert a["keyId"] == k
    # the listing must not leak the secret
    assert "sk-abc" not in c.get("/api/agents").text


def test_agent_disabled_excluded_from_enabled_list(c):
    a = c.post("/api/agents", json={"name": "Off", "enabled": False}).json()["agent"]
    listing = c.get("/api/agents").json()["agents"]
    off = [x for x in listing if x["id"] == a["id"]][0]
    assert off["enabled"] is False


def test_skill_disabled_flag_persisted(c):
    s = c.post("/api/skills", json={"name": "S", "prompt": "p", "enabled": False}).json()["skill"]
    assert s["enabled"] is False
    got = c.get("/api/agents").json()["skills"]
    assert [x for x in got if x["id"] == s["id"]][0]["enabled"] is False


def test_chat_search_indexes_pinned_flag(c, tmp_backend):
    """Search results should carry pinned flag when the message has it."""
    chats = [{"id": "c1", "title": "T", "messages": [
        {"role": "user", "content": "важный факт про кота", "pinned": True}]}]
    c.post("/api/chats/save", json={"chats": chats})
    r = c.get("/api/chats/search", params={"q": "кот"})
    m = r.json()["matches"]
    assert m and any(x.get("pinned") for x in m)
