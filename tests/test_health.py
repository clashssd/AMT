"""Tests for the /health endpoint (used by the frontend backend-status indicator)."""
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_backend):
    # Re-point persistent paths at tmp dirs (fixture sets env after import).
    main.server_settings = main.Settings()
    main.agents_mgr = main.AgentSkillManager(str(tmp_backend["tmp"] / "agents.json"))
    main.keys_mgr = main.KeyManager(str(tmp_backend["tmp"] / "keys.json"))
    app = main.app
    yield TestClient(app)


def test_health_ok_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    # The health endpoint reports liveness + counts so the UI can badge
    # "backend up / N agents / M keys".
    assert body.get("ok") is True or body.get("status") == "ok"
    assert "agents" in body
    assert "keys" in body


def test_health_is_200_when_backend_fresh(tmp_backend):
    # Even with zero agents/keys the endpoint must still be 200 (it is the
    # "is the backend reachable" signal, not "do we have data").
    c = TestClient(main.app)
    r = c.get("/health")
    assert r.status_code == 200


def test_health_reflects_agents_count(tmp_backend, client):
    # Seed an agent via the API (id via query param, body via AgentIn), then
    # /health should count it.
    r = client.post("/api/agents", params={"agent_id": "t_agent"}, json={"name": "T Agent"})
    assert r.status_code == 200
    h = client.get("/health").json()
    assert h["agents"] >= 1
