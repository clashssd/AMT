"""Coding mode payload validation."""
import main


def test_coding_request_falls_back_to_data_dir_when_no_project_root(tmp_backend, monkeypatch):
    """Coding chat with empty project_root should NOT return 400.
    Instead the backend falls back to AMT_DATA_DIR so the chat stays usable."""
    monkeypatch.setattr(main, "keys_mgr", type(main.keys_mgr)(main.KEYS_FILE))
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(main.app)

    resp = client.post("/api/chat", json={"message": "привет", "chat_mode": "coding", "project_root": ""})
    body = resp.json()

    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {body}"
    assert "error" not in body, f"unexpected error payload: {body}"


def test_general_request_does_not_require_project_root(tmp_backend, monkeypatch):
    monkeypatch.setattr(main, "keys_mgr", type(main.keys_mgr)(main.KEYS_FILE))
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(main.app)

    resp = client.post("/api/chat", json={"message": "привет", "chat_mode": "general", "project_root": ""})

    assert resp.status_code == 200
    assert "error" not in resp.json()
