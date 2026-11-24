"""Tests for agent/skill extension fields: group, enabled, parallel, keyId, orchestrator."""
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


def test_agent_with_group_and_flags(c):
    r = c.post("/api/agents", json={
        "name": "Lichnost", "systemPrompt": "sp", "group": "dev",
        "parallel": 3, "keyId": "", "orchestrator": "base", "enabled": True,
    })
    a = r.json()["agent"]
    assert a["group"] == "dev"
    assert a["parallel"] == 3
    assert a["enabled"] is True
    assert a["orchestrator"] == "base"


def test_agent_disable_via_update(c):
    a = c.post("/api/agents", json={"name": "A", "enabled": True}).json()["agent"]
    r = c.put(f"/api/agents/{a['id']}", json={"name": "A", "enabled": False})
    assert r.json()["agent"]["enabled"] is False


def test_agent_defaults_enabled_true(c):
    a = c.post("/api/agents", json={"name": "D"}).json()["agent"]
    assert a["enabled"] is True
    assert a["parallel"] == 1
    assert a.get("group", "") in ("", None)


def test_skill_with_group(c):
    s = c.post("/api/skills", json={"name": "S", "prompt": "p", "group": "work"}).json()["skill"]
    assert s["group"] == "work"


def test_skill_defaults(c):
    s = c.post("/api/skills", json={"name": "S2", "prompt": "p"}).json()["skill"]
    assert s["enabled"] is True


def test_personality_agent_combines_prompts(c):
    """A personality agent carries the combined prompt + skills."""
    sk = c.post("/api/skills", json={"name": "K", "prompt": "instr"}).json()["skill"]["id"]
    a = c.post("/api/agents", json={
        "name": "Persona", "systemPrompt": "base role\n\n[Агент X]\nsp",
        "skills": [sk], "parallel": 2,
    }).json()["agent"]
    # system prompt composition is stored as-is on the agent
    assert "base role" in a["systemPrompt"]
    assert sk in a["skills"]
    # build_system_prompt must include the skill prompt
    full = main.agents_mgr.build_system_prompt(a["id"])
    assert "instr" in full


def test_keys_do_not_leak_secrets_with_agent(c):
    """Agent keyId references a key; ensure the secret isn't echoed by /api/agents."""
    k = c.post("/api/keys", json={"label": "K", "apiKey": "sk-SECRET"}).json()["key"]["id"]
    c.post("/api/agents", json={"name": "P", "keyId": k})
    listing = c.get("/api/agents").text
    assert "sk-SECRET" not in listing
