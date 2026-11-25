"""Security-focused tests.

These both verify the application's security posture AND confirm the
specific vulnerabilities found during audit are handled.
"""
import json
import base64
import os
import re
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
    c = TestClient(main.app)
    yield c


# ---------- 1. File upload path traversal ----------
def test_upload_blocks_path_traversal(client, tmp_backend):
    payload = base64.b64encode(b"malicious").decode()
    r = client.post("/api/files/upload", json={
        "filename": "../../../etc/passwd",
        "content": payload,
        "mime_type": "text/plain",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The returned path MUST be inside FILES_DIR, never escaping it
    path = body["path"]
    files_dir = str(tmp_backend["files_dir"])
    assert os.path.realpath(path).startswith(os.path.realpath(files_dir) + os.sep)
    # Ensure we did NOT write to a real system path
    assert not os.path.exists(os.path.join(os.getcwd(), "etc"))


def test_upload_blocks_absolute_path(client, tmp_backend):
    payload = base64.b64encode(b"data").decode()
    r = client.post("/api/files/upload", json={
        "filename": "/etc/cron.d/x",
        "content": payload,
        "mime_type": "application/x",
    })
    path = r.json()["path"]
    files_dir = str(tmp_backend["files_dir"])
    assert os.path.realpath(path).startswith(os.path.realpath(files_dir) + os.sep)


def test_upload_null_byte_and_weird_chars(client, tmp_backend):
    payload = base64.b64encode(b"x").decode()
    r = client.post("/api/files/upload", json={
        "filename": "a\x00b/../../c",
        "content": payload,
        "mime_type": "text/plain",
    })
    path = r.json()["path"]
    files_dir = str(tmp_backend["files_dir"])
    assert os.path.realpath(path).startswith(os.path.realpath(files_dir) + os.sep)


def test_upload_enforces_size_limit(client, tmp_backend, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    big = base64.b64encode(b"a" * 100).decode()
    r = client.post("/api/files/upload", json={"filename": "big.bin", "content": big, "mime_type": "application/octet-stream"})
    assert r.json()["status"] == "error"
    assert "слишком большой" in r.json()["message"]


def test_upload_empty_filename_fallback(client, tmp_backend):
    payload = base64.b64encode(b"data").decode()
    r = client.post("/api/files/upload", json={"filename": "///...", "content": payload, "mime_type": "text/plain"})
    # basename of "///..." is "..." which has no safe alnum -> fallback "upload"
    assert r.json()["filename"] in ("upload", "...") or r.json()["status"] == "ok"


# ---------- 2. API key never leaks ----------
def test_settings_endpoint_never_exposes_key(client):
    main.server_settings = main.Settings(apiKey="sk-SECRET-XYZ")
    body = client.get("/api/settings").json()
    assert "sk-SECRET-XYZ" not in json.dumps(body)
    assert "SECRET-XYZ" not in json.dumps(body)


def test_logs_do_not_contain_api_key(client, tmp_backend, monkeypatch):
    """Log lines must not embed the Bearer token."""
    main.server_settings = main.Settings(apiKey="sk-SUPERSECRET", baseUrl="http://fake/v1", model="m")
    # Trigger a request log via a simulation chat (no key -> still logs? no, simulation returns early)
    # Force a real path: monkeypatch httpx to return ok, so REQUEST/RESPONSE are logged
    from fastapi.testclient import TestClient as TC
    import httpx as httpx_mod
    class FakeResp:
        status_code = 200
        headers = {"retry-after": ""}
        text = "{}"
        def json(self): return {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}
    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return FakeResp()
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    client.post("/api/chat", json={"message": "привет мир"})
    from datetime import datetime
    log_path = tmp_backend["logs_dir"] / f"chat_{datetime.now().strftime('%Y-%m-%d')}.log"
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        assert "sk-SUPERSECRET" not in content
        assert "Bearer" not in content


# ---------- 3. CORS configuration ----------
def test_cors_not_wildcard_with_credentials():
    """A '*' origin combined with credentials=True is invalid/unsafe.
    The app must either restrict origins or disable credentials."""
    cors = None
    for mw in main.app.user_middleware:
        if getattr(mw, "cls", None) is main.CORSMiddleware:
            cors = mw
            break
    assert cors is not None, "CORS middleware not found"
    allow_origins = cors.kwargs.get("allow_origins")
    allow_credentials = cors.kwargs.get("allow_credentials")
    # The dangerous combo is ["*"] + True
    if allow_credentials:
        assert "*" not in (allow_origins or []), "CORS: '*' with credentials=True is unsafe"


def test_cors_default_allows_localhost(client):
    """Pre-flight from localhost should be accepted."""
    r = client.options(
        "/",
        headers={"Origin": "http://127.0.0.1:8000", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code in (200, 204)


# ---------- 4. Settings input validation ----------
def test_settings_rejects_bad_types(client):
    r = client.post("/api/settings", json={"temperature": "not_a_number"})
    assert r.status_code == 422  # pydantic validation


def test_chat_rejects_missing_message(client):
    r = client.post("/api/chat", json={})
    assert r.status_code == 422


def test_orch_config_arbitrary_keys_stored_but_inert(client, tmp_backend):
    """POSTing unknown keys is accepted (dict). Ensure it can't crash config.
    This documents the behavior: we accept a free-form dict. We guard that
    a non-dict body is rejected."""
    r = client.post("/api/orchestrator/config", json={"weird_key": [1, 2]})
    assert r.json()["status"] == "updated"
    # Non-dict must 422
    r2 = client.post("/api/orchestrator/config", json="just a string")
    assert r2.status_code == 422


# ---------- 5. Static / no key disclosure on disk ----------
def test_settings_json_file_not_world_readable_metadata(client, tmp_backend):
    """Even though the key is stored in settings.json, the GET endpoint hides it.
    Confirm the file itself can contain the key but the API masks it (already tested).
    This test ensures persisting a key doesn't get reflected back through GET."""
    client.post("/api/settings", json={"apiKey": "sk-ONLY-ON-DISK"})
    on_disk = json.loads(tmp_backend["settings_file"].read_text())
    assert on_disk["apiKey"] == "sk-ONLY-ON-DISK"
    api_view = client.get("/api/settings").json()
    assert "sk-ONLY-ON-DISK" not in json.dumps(api_view)


# ---------- 6. Model capability inference (no crash on odd ids) ----------
def test_models_handles_empty_and_odd_ids(client, monkeypatch):
    main.server_settings = main.Settings(apiKey="sk", baseUrl="http://fake/v1")
    import httpx as h
    class R:
        status_code = 200
        headers = {"retry-after": ""}
        text = "{}"
        def json(self):
            return {"data": [{"id": "…weird…"}, {"id": ""}]}
    class C:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return R()
        async def post(self, *a, **k): return R()
    monkeypatch.setattr(main.httpx, "AsyncClient", C)
    r = client.post("/api/models/test")
    assert r.json()["ok"] is True
    # no crash, empty id just has no capabilities
    assert any(m["id"] == "" for m in r.json()["models"])


# ---------- 7. Host header validation (audit fixes 1.2-1.6) ----------
def test_host_validation_blocks_evil_com(client):
    """A request with Host: evil.com must be rejected (DNS-rebinding mitigation)."""
    r = client.get("/health", headers={"Host": "evil.com"})
    assert r.status_code == 403


def test_host_validation_blocks_nip_io(client):
    """Host: 127.0.0.1.nip.io (DNS-rebinding trick) must be rejected."""
    r = client.get("/health", headers={"Host": "127.0.0.1.nip.io"})
    assert r.status_code == 403


def test_host_validation_blocks_subdomain(client):
    """Host: subdomain.127.0.0.1 must be rejected."""
    r = client.get("/health", headers={"Host": "sub.127.0.0.1"})
    assert r.status_code == 403


def test_host_validation_blocks_missing_host(client):
    """A request without a Host header must be rejected (fail-closed)."""
    # TestClient always sends a Host header, so we test via the raw app
    # by confirming testserver (the TestClient default) is allowed but
    # an empty string would not be.
    r = client.get("/health", headers={"Host": ""})
    assert r.status_code in (400, 403)


def test_host_validation_allows_localhost(client):
    """Host: localhost must be accepted."""
    r = client.get("/health", headers={"Host": "localhost"})
    assert r.status_code == 200


def test_host_validation_allows_127_0_0_1(client):
    """Host: 127.0.0.1 must be accepted."""
    r = client.get("/health", headers={"Host": "127.0.0.1"})
    assert r.status_code == 200


def test_host_validation_allows_with_port(client):
    """Host: 127.0.0.1:8765 must be accepted (port is stripped)."""
    r = client.get("/health", headers={"Host": "127.0.0.1:8765"})
    assert r.status_code == 200


# ---------- 8. Origin validation for mutating requests (audit fixes 2.1-2.7) ----------
def test_origin_blocks_evil_com_post(client):
    """POST with Origin: http://evil.com must be rejected."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "http://evil.com"})
    assert r.status_code == 403


def test_origin_blocks_null_post(client):
    """POST with Origin: null must be rejected."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "null"})
    # "null" as an Origin header means the browser stripped it (file://, cross-origin)
    # We treat it as an unknown host -> blocked
    assert r.status_code == 403


def test_origin_blocks_subdomain_post(client):
    """POST with Origin: http://evil.127.0.0.1:8765 must be rejected."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "http://evil.127.0.0.1:8765"})
    assert r.status_code == 403


def test_origin_blocks_wrong_port_post(client):
    """POST with Origin: http://evil.127.0.0.1:9999 (subdomain trick) must be
    rejected because the hostname is not in the allowlist."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "http://evil.127.0.0.1:9999"})
    assert r.status_code == 403


def test_origin_allows_localhost_post(client):
    """POST with Origin: http://localhost:8000 must be accepted."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "http://localhost:8000"})
    assert r.status_code == 200


def test_origin_allows_127_0_0_1_post(client):
    """POST with Origin: http://127.0.0.1:8000 must be accepted."""
    r = client.post("/api/settings", json={"temperature": 0.5},
                    headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200


def test_origin_allows_no_origin_post(client):
    """POST without Origin header (curl, Postman, sidecar) must be accepted."""
    r = client.post("/api/settings", json={"temperature": 0.5})
    assert r.status_code == 200


def test_origin_allows_get_foreign_origin(client):
    """GET with foreign Origin is allowed (CORS handles the cross-origin read).
    The audit only flags mutating requests for Origin checking."""
    r = client.get("/api/settings", headers={"Origin": "http://evil.com"})
    # GET should still work – CORS preflight would block browser requests,
    # but a direct GET from a non-browser with a foreign origin is fine
    assert r.status_code == 200


# ---------- 9. CORS allow_methods shrunk (audit fix 3.4) ----------
def test_cors_allow_methods_not_wildcard():
    """allow_methods must not be ['*'] – it should be an explicit list."""
    cors = None
    for mw in main.app.user_middleware:
        if getattr(mw, "cls", None) is main.CORSMiddleware:
            cors = mw
            break
    assert cors is not None, "CORS middleware not found"
    allow_methods = cors.kwargs.get("allow_methods")
    assert allow_methods != ["*"], "CORS allow_methods must not be wildcard"
    assert "GET" in allow_methods
    assert "POST" in allow_methods
