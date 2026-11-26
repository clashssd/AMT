"""Coding mode payload validation."""
import main


def test_coding_request_requires_project_root(tmp_backend, monkeypatch):
    monkeypatch.setattr(main, "keys_mgr", type(main.keys_mgr)(main.KEYS_FILE))
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(main.app)

    resp = client.post("/api/chat", json={"message": "привет", "chat_mode": "coding", "project_root": ""})
    body = resp.json()

    assert resp.status_code == 400
    assert "project" in body.get("detail", "").lower() or "проект" in body.get("detail", "").lower()


def test_general_request_does_not_require_project_root(tmp_backend, monkeypatch):
    monkeypatch.setattr(main, "keys_mgr", type(main.keys_mgr)(main.KEYS_FILE))
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(main.app)

    resp = client.post("/api/chat", json={"message": "привет", "chat_mode": "general", "project_root": ""})

    assert resp.status_code == 200
    assert "error" not in resp.json()
