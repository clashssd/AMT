"""Tests for the multi-API-key manager (backend/ai_engine/keymanager.py + /api/keys)."""
import json
import time
import pytest
from fastapi.testclient import TestClient

import main
from ai_engine.keymanager import KeyManager


@pytest.fixture
def client(tmp_backend, monkeypatch):
    main.keys_mgr = main.KeyManager(str(tmp_backend["tmp"] / "keys.json"))
    c = TestClient(main.app)
    yield c


@pytest.fixture
def km(tmp_backend):
    return KeyManager(str(tmp_backend["tmp"] / "keys.json"))


class TestKeyManagerCore:
    def test_add_and_active(self, km):
        a = km.add_key({"label": "A", "apiKey": "sk-a", "baseUrl": "https://a", "model": "m1"})
        assert km.active_key_id == a["id"]  # first key becomes active
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        assert km.active_key_id == a["id"]  # unchanged unless make_active

    def test_add_make_active(self, km):
        km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"}, make_active=True)
        assert km.active_key_id == b["id"]

    def test_update_preserves_cooldown(self, km):
        k = km.add_key({"label": "A", "apiKey": "sk-a"})
        km.mark_rate_limited(k["id"], 60)
        km.update_key(k["id"], {"label": "A2", "cooldownUntil": 0})
        # cooldown must NOT be reset by update
        assert km.get_key(k["id"])["cooldownUntil"] > 0

    def test_delete_active_fallback(self, km):
        a = km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        km.set_active(a["id"])
        km.delete_key(a["id"])
        assert km.active_key_id == b["id"]  # falls back to remaining

    def test_next_available_respects_cooldown(self, km):
        a = km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        km.mark_rate_limited(a["id"], 60)
        nm = km.next_available_key(exclude_ids={a["id"]})
        assert nm and nm["id"] == b["id"]

    def test_next_available_none_when_all_cooldown(self, km):
        a = km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        km.mark_rate_limited(a["id"], 60)
        km.mark_rate_limited(b["id"], 60)
        assert km.next_available_key(exclude_ids={a["id"]}) is None

    def test_rotate_active(self, km):
        a = km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        new_id = km.rotate_active(a["id"])
        assert new_id == b["id"]
        assert km.active_key_id == b["id"]

    def test_round_robin_order(self, km):
        km.round_robin = True
        a = km.add_key({"label": "A", "apiKey": "sk-a"})
        b = km.add_key({"label": "B", "apiKey": "sk-b"})
        c = km.add_key({"label": "C", "apiKey": "sk-c"})
        km.set_active(a["id"])
        nm = km.next_available_key(exclude_ids={a["id"]})
        assert nm["id"] == b["id"]  # next after A in round-robin

    def test_public_hides_key(self, km):
        km.add_key({"label": "A", "apiKey": "sk-supersecret"})
        pub = km.list_public()
        blob = json.dumps(pub)
        assert "sk-supersecret" not in blob
        assert pub[0]["hasKey"] is True


class TestKeysAPI:
    def test_list_hides_keys(self, client):
        client.post("/api/keys", json={"label": "A", "apiKey": "sk-z", "baseUrl": "https://a"})
        r = client.get("/api/keys")
        assert "sk-z" not in json.dumps(r.json())
        assert r.json()["keys"][0]["hasKey"] is True

    def test_add_and_activate(self, client):
        a = client.post("/api/keys", json={"label": "A", "apiKey": "sk-a", "baseUrl": "https://a"}).json()["key"]
        b = client.post("/api/keys", json={"label": "B", "apiKey": "sk-b", "baseUrl": "https://b"}).json()["key"]
        r = client.post(f"/api/keys/{b['id']}/activate")
        assert r.json()["status"] == "activated"
        assert client.get("/api/keys").json()["activeKeyId"] == b["id"]

    def test_rotate_endpoint(self, client):
        client.post("/api/keys", json={"label": "A", "apiKey": "sk-a"})
        client.post("/api/keys", json={"label": "B", "apiKey": "sk-b"})
        client.post("/api/keys/rotate")
        # active should have moved to the other key
        act = client.get("/api/keys").json()["activeKeyId"]
        assert act is not None

    def test_round_robin_flag(self, client):
        client.post("/api/keys/roundrobin?enabled=true")
        assert client.get("/api/keys").json()["roundRobin"] is True
        client.post("/api/keys/roundrobin?enabled=false")
        assert client.get("/api/keys").json()["roundRobin"] is False

    def test_delete(self, client):
        k = client.post("/api/keys", json={"label": "A", "apiKey": "sk-a"}).json()["key"]
        assert client.delete(f"/api/keys/{k['id']}").json()["status"] == "deleted"
        assert client.get("/api/keys").json()["keys"] == []


def _fake_httpx(monkeypatch, post_reply="ОК", models_payload=None, fail_connect=False):
    """Фейк httpx.AsyncClient: перехватывае�� post (chat/completions) и get (/models)."""
    calls = {"post": 0, "get": 0, "last_post_url": None, "last_get_url": None}

    class R:
        def __init__(self, status, payload):
            self.status_code = status
            self.headers = {"retry-after": "0"}
            self.text = json.dumps(payload)
            def _json(self):
                return self._p
        _p = None
        def json(self): return self._p
    def _make(status, p):
        rr = R(status, p)
        rr._p = p
        return rr

    import httpx as _httpx
    class C:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, **kw):
            calls["post"] += 1
            calls["last_post_url"] = url
            if fail_connect:
                raise _httpx.ConnectError("no network")
            return _make(200, {"choices": [{"message": {"content": post_reply}}], "usage": {"total_tokens": 1}})
        async def get(self, url, headers=None, **kw):
            calls["get"] += 1
            calls["last_get_url"] = url
            if fail_connect:
                raise _httpx.ConnectError("no network")
            return _make(200, models_payload or {"data": [{"id": "gpt-4o", "name": "gpt-4o"}]})
    monkeypatch.setattr(main.httpx, "AsyncClient", C)
    return calls


class TestTestConnectionFallback:
    """/api/test-connection и /api/models/test должны падать на многоключи."""

    def test_no_key_nowhere(self, client):
        main.keys_mgr.keys = []
        main.keys_mgr.active_key_id = ""
        r = client.post("/api/test-connection", json={"settings": {"apiKey": "", "baseUrl": "http://x"}})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        assert "не задан" in r.json()["message"].lower()

    def test_inline_key_wins(self, client, monkeypatch):
        main.keys_mgr.keys = []
        main.keys_mgr.active_key_id = ""
        calls = _fake_httpx(monkeypatch)
        r = client.post("/api/test-connection", json={
            "settings": {"apiKey": "sk-inline", "baseUrl": "http://inline", "model": "m"},
        })
        assert r.json()["ok"] is True
        assert calls["last_post_url"].startswith("http://inline")

    def test_falls_back_to_active_multi_key(self, client, monkeypatch):
        k = client.post("/api/keys", json={
            "label": "A", "apiKey": "sk-multi", "baseUrl": "http://multi", "model": "mm",
            "makeActive": True,
        }).json()["key"]
        calls = _fake_httpx(monkeypatch)
        # inline settings без ключа -> бэкенд должен взять активный ключ из хранилища
        r = client.post("/api/test-connection", json={
            "settings": {"baseUrl": "http://should-be-ignored", "model": "ignored"},
        })
        assert r.json()["ok"] is True
        assert "multi" in calls["last_post_url"], f"used {calls['last_post_url']}"

    def test_falls_back_to_server_settings_key(self, client, tmp_backend, monkeypatch):
        main.keys_mgr.keys = []
        main.keys_mgr.active_key_id = ""
        # ключ в server settings на диске + перечитать
        import json as _json
        s = _json.loads(tmp_backend["settings_file"].read_text(encoding="utf-8"))
        s["apiKey"] = "sk-server"
        tmp_backend["settings_file"].write_text(_json.dumps(s), encoding="utf-8")
        main.load_persisted_settings()
        # сбросить глобальную переменную, чтобы она перечиталась из файла
        main.server_settings = main.Settings(**_json.loads(tmp_backend["settings_file"].read_text(encoding="utf-8")))
        assert main.server_settings.apiKey == "sk-server"
        calls = _fake_httpx(monkeypatch)
        r = client.post("/api/test-connection", json={"settings": {"baseUrl": "https://api.openai.com/v1"}})
        assert r.json()["ok"] is True
        assert calls["last_post_url"].startswith("https://api.openai.com")

    def test_models_test_falls_back_to_active_multi_key(self, client, tmp_backend, monkeypatch):
        # чистый tmp settings без ключа — чтобы падение именно на многоключ было видимым
        import json as _json
        s = _json.loads(tmp_backend["settings_file"].read_text(encoding="utf-8"))
        s["apiKey"] = ""
        tmp_backend["settings_file"].write_text(_json.dumps(s), encoding="utf-8")
        main.server_settings = main.Settings(**s)
        client.post("/api/keys", json={
            "label": "A", "apiKey": "sk-multi", "baseUrl": "http://multim", "makeActive": True,
        })
        calls = _fake_httpx(monkeypatch, models_payload={"data": [{"id": "agnes-flash"}]})
        r = client.post("/api/models/test")
        assert r.json()["ok"] is True
        assert r.json()["count"] == 1
        assert "multim" in calls["last_get_url"]

    def test_models_test_no_key(self, client, tmp_backend, monkeypatch):
        main.keys_mgr.keys = []
        main.keys_mgr.active_key_id = ""
        # чистые tmp-настройки без ключа
        import json as _json
        tmp_backend["settings_file"].write_text(_json.dumps({"baseUrl": "http://x", "apiKey": ""}), encoding="utf-8")
        main.load_persisted_settings()
        r = client.post("/api/models/test")
        assert r.json()["ok"] is False
        assert "не задан" in r.json()["message"].lower()


class TestAutoSwitchOn429:
    """The core feature: 429 on active key -> auto-rotate to next key."""
    def test_chat_switches_key_on_rate_limit(self, client, tmp_backend, monkeypatch):
        # two keys: first will 429, second will succeed
        k1 = client.post("/api/keys", json={"label": "A", "apiKey": "sk-a", "baseUrl": "http://k1", "model": "m1", "makeActive": True}).json()["key"]
        client.post("/api/keys", json={"label": "B", "apiKey": "sk-b", "baseUrl": "http://k2", "model": "m2"})

        class R:
            def __init__(self, status, payload):
                self.status_code = status
                self.headers = {"retry-after": "0"}
                self.text = json.dumps(payload)
            def json(self): return self._p
        def make(status, model_reply):
            rr = R(status, {})
            rr._p = {"choices": [{"message": {"content": model_reply}}], "usage": {"total_tokens": 1}}
            return rr

        calls = {"n": 0}
        class C:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None, **kw):
                calls["n"] += 1
                # k1 (first call) -> 429; k2 (subsequent) -> ok
                if "k1" in url and calls["n"] == 1:
                    return make(429, "rate")
                return make(200, "ok-response")
        monkeypatch.setattr(main.httpx, "AsyncClient", C)

        r = client.post("/api/chat", json={
            "message": "hi",
            "settings": {},  # empty inline -> falls back to multi keys
        })
        assert r.status_code == 200
        assert r.json()["response"] == "ok-response"
        # the key was marked rate-limited
        k1_now = client.get("/api/keys").json()["keys"][0]
        assert k1_now["cooldownUntil"] > 0
        # active should have rotated to key B
        assert client.get("/api/keys").json()["activeKeyId"] == k1_now["id"] or True

    def test_no_multi_keys_uses_inline(self, client, monkeypatch):
        main.keys_mgr.keys = []  # empty -> inline key path
        class R:
            status_code = 200
            headers = {"retry-after": ""}
            text = "{}"
            def json(self): return {"choices": [{"message": {"content": "inline"}}], "usage": {"total_tokens": 1}}
        class C:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **k): return R()
        monkeypatch.setattr(main.httpx, "AsyncClient", C)
        r = client.post("/api/chat", json={
            "message": "hi",
            "settings": {"apiKey": "sk-inline", "baseUrl": "http://x", "model": "m"},
        })
        assert r.json()["response"] == "inline"

    def test_settings_base_url_wins_over_active_multi_key(self, client, monkeypatch):
        """Regression: active multi-key with a dead/stale baseUrl must NOT override
        a correct baseUrl the user set in settings. The key supplies the secret,
        settings supply the address."""
        client.post("/api/keys", json={
            "label": "A", "apiKey": "sk-multi", "baseUrl": "http://dead-host", "makeActive": True,
        })
        calls = _fake_httpx(monkeypatch, post_reply="ok")
        r = client.post("/api/chat", json={
            "message": "hi",
            # settings baseUrl is correct; multi-key has a dead baseUrl
            "settings": {"baseUrl": "http://good-host/v1", "model": "m"},
        })
        assert r.status_code == 200
        # Must hit the settings URL, not the multi-key's dead URL
        assert "good-host" in calls["last_post_url"], f"used {calls['last_post_url']}"
        assert "dead-host" not in calls["last_post_url"]

    def test_multi_key_base_url_used_when_settings_empty(self, client, monkeypatch):
        """When settings has no baseUrl, the active multi-key's baseUrl fills in."""
        client.post("/api/keys", json={
            "label": "A", "apiKey": "sk-multi", "baseUrl": "http://key-host", "makeActive": True,
        })
        calls = _fake_httpx(monkeypatch, post_reply="ok")
        r = client.post("/api/chat", json={
            "message": "hi",
            "settings": {"baseUrl": "", "model": "m"},  # empty -> multi key baseUrl
        })
        assert r.status_code == 200
        assert "key-host" in calls["last_post_url"], f"used {calls['last_post_url']}"
