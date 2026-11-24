"""Tests for theming/config/backgrounds endpoints + Agnes video poll shape."""
import os
import sys
import base64
import json
import pytest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))

from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_backend):
    import importlib, main
    importlib.reload(main)
    return TestClient(main.app)


# ===== Конфиги =====
def test_configs_save_list_delete(client):
    r = client.post("/api/configs", json={"name": "work", "config": {"theme": "ocean", "lang": "ru"}})
    assert r.status_code == 200 and r.json()["ok"]
    d = client.get("/api/configs").json()
    names = [c["name"] for c in d["configs"]]
    assert "work" in names
    # apply
    a = client.post("/api/configs/work/apply").json()
    assert a["ok"] and a["config"]["theme"] == "ocean"
    # delete
    client.delete("/api/configs/work")
    assert "work" not in [c["name"] for c in client.get("/api/configs").json()["configs"]]


def test_configs_name_sanitized_no_traversal(client):
    r = client.post("/api/configs", json={"name": "../evil", "config": {}})
    assert r.status_code == 200
    # no file created outside CONFIGS_DIR
    assert not os.path.exists(os.path.join(os.path.dirname(__import__('main').__file__), "evil.json"))


# ===== Фон =====
def test_background_upload_reject_non_media(client):
    b64 = base64.b64encode(b"hello").decode()
    r = client.post("/api/backgrounds", json={"name": "x.txt", "mime": "text/plain", "b64": b64})
    assert r.status_code == 200 and r.json()["ok"] is False


def test_background_upload_image_ok(client, tmp_backend):
    # tiny 1x1 png
    png = base64.b64encode(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfff010008134e0bca070000000049454e44ae426082")
    ).decode()
    r = client.post("/api/backgrounds", json={"name": "bg.png", "mime": "image/png", "b64": png})
    assert r.status_code == 200 and r.json()["ok"]
    url = r.json()["url"]
    # fetch it back
    got = client.get(url)
    assert got.status_code == 200 and len(got.content) > 0


# ===== Video task poll shape (provider-neutral: generic text2video poll, no crash) =====
def test_check_video_task_generic_poll(monkeypatch, tmp_backend):
    from ai_engine import media
    calls = {}
    class FakeResp:
        status_code = 200
        text = ""
        def json(self):
            # Generic poll shape the code actually parses:
            #   data (dict).task_status + data (dict).task_result[0].url
            return {"data": {"task_status": "succeed",
                              "task_result": [{"url": "https://example.com/v.mp4"}]}}
    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, headers=None):
            calls["url"] = url
            return FakeResp()
    monkeypatch.setattr(media, "_client", lambda *a, **k: FakeClient())
    out = media.check_video_task("https://videoprovider.example/v1", "KEY", "VID123")
    # Generic path returns status "succeed" + url; no crash, provider-neutral.
    assert out["status"] == "succeed", out
    assert out["url"].endswith("v.mp4"), out
    # URL is the generic text2video poll, base without /v1 doubling
    assert "/v1/v1" not in calls["url"], calls["url"]
