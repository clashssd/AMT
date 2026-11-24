"""Tests for the Agents & Skills system (backend/ai_engine/agents.py + /api/agents, /api/skills)."""
import json
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_backend, monkeypatch):
    main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
    c = TestClient(main.app)
    yield c


@pytest.fixture
def mgr(tmp_backend):
    from ai_engine.agents import AgentSkillManager
    return AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))


class TestAgentSkillManager:
    def test_add_agent(self, mgr):
        a = mgr.add_agent({"name": "Стрикс", "systemPrompt": "Ты dev", "skills": []})
        assert a["id"].startswith("a_")
        assert len(mgr.list_agents()) == 1

    def test_agent_get(self, mgr):
        a = mgr.add_agent({"name": "A", "systemPrompt": "sp"})
        got = mgr.get_agent(a["id"])
        assert got["name"] == "A"

    def test_update_agent(self, mgr):
        a = mgr.add_agent({"name": "A", "systemPrompt": "sp"})
        mgr.update_agent(a["id"], {"model": "gpt-4"})
        assert mgr.get_agent(a["id"])["model"] == "gpt-4"

    def test_delete_agent(self, mgr):
        a = mgr.add_agent({"name": "A", "systemPrompt": "sp"})
        assert mgr.delete_agent(a["id"]) is True
        assert mgr.delete_agent(a["id"]) is False  # already gone
        assert mgr.list_agents() == []

    def test_add_skill(self, mgr):
        s = mgr.add_skill({"name": "review", "prompt": "check code"})
        assert s["id"].startswith("s_")
        assert s["enabled"] is True
        assert len(mgr.list_skills()) == 1

    def test_delete_skill_drops_from_agents(self, mgr):
        a = mgr.add_agent({"name": "A", "systemPrompt": "sp", "skills": []})
        s = mgr.add_skill({"name": "x", "prompt": "y"})
        a["skills"] = [s["id"]]
        mgr.delete_skill(s["id"])
        # skill gone
        assert mgr.list_skills() == []
        # agent no longer references it
        assert s["id"] not in mgr.get_agent(a["id"])["skills"]

    def test_build_system_prompt_combines(self, mgr):
        s1 = mgr.add_skill({"name": "S1", "prompt": "prompt-1", "enabled": True})
        s2 = mgr.add_skill({"name": "S2", "prompt": "prompt-2", "enabled": False})
        a = mgr.add_agent({"name": "A", "systemPrompt": "BASE", "skills": [s1["id"], s2["id"]]})
        sp = mgr.build_system_prompt(a["id"])
        assert "BASE" in sp
        assert "prompt-1" in sp
        assert "prompt-2" not in sp  # disabled skill skipped
        # extra skill
        s3 = mgr.add_skill({"name": "S3", "prompt": "prompt-3", "enabled": True})
        sp2 = mgr.build_system_prompt(a["id"], [s3["id"]])
        assert "prompt-3" in sp2

    def test_no_agent_no_skill_empty(self, mgr):
        assert mgr.build_system_prompt(None) == ""

    def test_agent_model_params(self, mgr):
        a = mgr.add_agent({"name": "A", "model": "gpt-4o", "temperature": 0.2, "systemPrompt": "sp"})
        p = mgr.agent_model_params(a["id"])
        assert p["model"] == "gpt-4o"
        assert p["temperature"] == 0.2
        assert "maxTokens" not in p

    def test_no_agent_params_empty(self, mgr):
        assert mgr.agent_model_params(None) == {}


class TestAgentsAPI:
    def test_create_and_list(self, client):
        r = client.post("/api/agents", json={"name": "Dev", "systemPrompt": "sp"})
        assert r.json()["status"] == "created"
        lid = client.get("/api/agents").json()
        assert len(lid["agents"]) == 1
        assert lid["agents"][0]["name"] == "Dev"

    def test_update(self, client):
        a = client.post("/api/agents", json={"name": "A", "systemPrompt": "sp"}).json()["agent"]
        r = client.put(f"/api/agents/{a['id']}", json={"name": "A2"})
        assert r.json()["agent"]["name"] == "A2"

    def test_update_missing_404(self, client):
        assert client.put("/api/agents/nonexistent", json={"name": "X"}).status_code == 404

    def test_delete(self, client):
        a = client.post("/api/agents", json={"name": "A", "systemPrompt": "sp"}).json()["agent"]
        assert client.delete(f"/api/agents/{a['id']}").json()["status"] == "deleted"
        assert client.get("/api/agents").json()["agents"] == []

    def test_create_skill(self, client):
        r = client.post("/api/skills", json={"name": "S", "prompt": "p"})
        assert r.json()["status"] == "created"
        assert len(client.get("/api/agents").json()["skills"]) == 1

    def test_skill_toggle_and_delete(self, client):
        s = client.post("/api/skills", json={"name": "S", "prompt": "p"}).json()["skill"]
        # toggle off
        client.put(f"/api/skills/{s['id']}", json={"name": "S", "prompt": "p", "enabled": False})
        client.delete(f"/api/skills/{s['id']}")
        assert client.get("/api/agents").json()["skills"] == []


class TestChatWithAgent:
    """Verify agent prompt actually reaches the AI request."""
    def test_agent_prompt_injected(self, client, tmp_backend, monkeypatch):
        # create agent + skill
        s = client.post("/api/skills", json={"name": "SK", "prompt": "INSTRUCT-X"}).json()["skill"]
        a = client.post("/api/agents", json={"name": "DEV", "systemPrompt": "ROLE-Y", "skills": [s["id"]], "model": "gpt-4o"}).json()["agent"]
        # fake the AI — capture only the FIRST call (the main chat completion),
        # since fact-extraction makes a second call to the same endpoint.
        calls = []
        class R:
            status_code = 200
            headers = {"retry-after": ""}
            text = "{}"
            def json(self): return {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}
        class C:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None, **kw):
                calls.append(json)
                return R()
        monkeypatch.setattr(main.httpx, "AsyncClient", C)
        main.keys_mgr.keys = []  # no multi keys -> uses inline key
        r = client.post("/api/chat", json={
            "message": "hi",
            "settings": {"apiKey": "sk", "baseUrl": "http://fake/v1", "model": "m"},
            "agent_id": a["id"],
        })
        assert r.status_code == 200
        body = calls[0]
        sysmsg = [m for m in body["messages"] if m["role"] == "system"]
        assert sysmsg, "expected a system message"
        assert "ROLE-Y" in sysmsg[0]["content"]
        assert "INSTRUCT-X" in sysmsg[0]["content"]
        # agent model overrides request model
        assert body["model"] == "gpt-4o"
