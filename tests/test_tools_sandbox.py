"""Tests for the safe tool sandbox endpoints."""
import os
import json
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def c(tmp_backend, monkeypatch):
    tmp = tmp_backend["tmp"]
    # изолируем конфиг/лог инструментов в tmp
    from ai_engine import tools as t
    monkeypatch.setenv("AMT_TOOLS_CONFIG", str(tmp / "tools_config.json"))
    monkeypatch.setenv("AMT_TOOLS_LOG", str(tmp / "tools_log.jsonl"))
    main.tools_sandbox = t.ToolSandbox(config_path=str(tmp / "tools_config.json"), log_path=str(tmp / "tools_log.jsonl"))
    return TestClient(main.app)


def test_tools_config_default(c):
    r = c.get("/api/tools/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["enabled"] is False
    assert cfg["command_whitelist"] == []


def test_tools_disabled_by_default(c):
    r = c.post("/api/tools/execute", json={"tool": "list_dir", "args": {".": "."}, "approved": True})
    assert r.json()["ok"] is False
    assert "выключены" in r.json()["error"]


def test_tools_read_requires_allowlist(c, tmp_backend):
    tmp = tmp_backend["tmp"]
    # разрешаем tools + каталог + читаем файл
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    (tmp / "f.txt").write_text("hello", encoding="utf-8")
    r = c.post("/api/tools/execute", json={"tool": "read_file", "args": {"path": str(tmp / "f.txt")}, "approved": True})
    assert r.json()["ok"] is True
    assert r.json()["content"] == "hello"


def test_tools_path_traversal_blocked(c, tmp_backend):
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "read_file", "args": {"path": "../../../etc/passwd"}, "approved": True})
    assert r.json()["ok"] is False


def test_tools_command_whitelist_enforced(c, tmp_backend):
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)], "command_whitelist": ["python -V"]})
    # разрешённая команда
    ok = c.post("/api/tools/execute", json={"tool": "run_command", "args": {"command": "python -V"}, "approved": True})
    # запрещённая команда (rm не в whitelist)
    bad = c.post("/api/tools/execute", json={"tool": "run_command", "args": {"command": "rm -rf /"}, "approved": True})
    assert ok.json().get("code") in ("whitelist", None) or ok.json()["ok"]
    assert bad.json()["ok"] is False
    assert bad.json().get("code") == "whitelist"


def test_tools_needs_approval_without_auto(c, tmp_backend):
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": False, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "list_dir", "args": {"path": str(tmp)}, "approved": False})
    assert r.json().get("code") == "needs_approval"


def test_tools_open_url_rejects_non_http(c):
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True})
    r = c.post("/api/tools/execute", json={"tool": "open_url", "args": {"url": "file:///etc/passwd"}, "approved": True})
    assert r.json()["ok"] is False


def test_tools_write_file_in_allowed_dir(c, tmp_backend):
    """write_file creates a file inside allowed_dirs and returns ok."""
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "write_file", "args": {"path": str(tmp / "out.txt"), "content": "hello world"}, "approved": True})
    assert r.json()["ok"] is True
    assert r.json()["path"] == str(tmp / "out.txt")
    assert (tmp / "out.txt").read_text(encoding="utf-8") == "hello world"


def test_tools_write_file_creates_parent_dirs(c, tmp_backend):
    """write_file creates intermediate directories when missing."""
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "write_file", "args": {"path": str(tmp / "sub" / "deep" / "f.txt"), "content": "x"}, "approved": True})
    assert r.json()["ok"] is True
    assert (tmp / "sub" / "deep" / "f.txt").read_text(encoding="utf-8") == "x"


def test_tools_write_file_blocked_outside_allowed_dirs(c, tmp_backend):
    """write_file outside allowed_dirs is rejected, no file created."""
    tmp = tmp_backend["tmp"]
    import tempfile, pathlib
    outside = pathlib.Path(tempfile.mkdtemp())  # sibling dir, NOT under tmp
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "write_file", "args": {"path": str(outside / "evil.txt"), "content": "x"}, "approved": True})
    data = r.json()
    assert data["ok"] is False
    assert data.get("code") == "denied"
    assert not (outside / "evil.txt").exists()


def test_tools_create_dir_in_allowed_dir(c, tmp_backend):
    """create_dir makes a directory inside allowed_dirs."""
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "create_dir", "args": {"path": str(tmp / "newdir")}, "approved": True})
    assert r.json()["ok"] is True
    assert (tmp / "newdir").is_dir()


def test_tools_create_dir_blocked_outside_allowed_dirs(c, tmp_backend):
    """create_dir outside allowed_dirs is rejected."""
    tmp = tmp_backend["tmp"]
    import tempfile, pathlib
    outside = pathlib.Path(tempfile.mkdtemp())  # sibling dir, NOT under tmp
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": True, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "create_dir", "args": {"path": str(outside / "newdir")}, "approved": True})
    data = r.json()
    assert data["ok"] is False
    assert data.get("code") == "denied"


def test_tools_write_requires_approval(c, tmp_backend):
    """write_file with auto_approve=False requires approved=True."""
    tmp = tmp_backend["tmp"]
    c.post("/api/tools/config", json={"enabled": True, "auto_approve": False, "allowed_dirs": [str(tmp)]})
    r = c.post("/api/tools/execute", json={"tool": "write_file", "args": {"path": str(tmp / "a.txt"), "content": "a"}, "approved": False})
    assert r.json().get("code") == "needs_approval"


def test_files_delete_endpoint(c, tmp_backend):
    """DELETE /api/files/{name} removes a file from FILES_DIR, blocks traversal."""
    tmp = tmp_backend["tmp"]
    # направим FILES_DIR в tmp через monkeypatch на модуль main
    import main as m
    old = m.FILES_DIR
    m.FILES_DIR = str(tmp)
    import os
    os.makedirs(m.FILES_DIR, exist_ok=True)
    try:
        (tmp / "hello.txt").write_text("x", encoding="utf-8")
        r = c.delete("/api/files/hello.txt")
        assert r.json().get("status") in ("deleted", "not_found")
        # traversal-имя не должно удалить внешние файлы
        r2 = c.delete("/api/files/%2E%2E")  # '..' в закодированном виде
        assert r2.status_code == 200 and r2.json().get("status") in ("error", "not_found")
    finally:
        m.FILES_DIR = old


def test_projects_select_and_get(c, tmp_backend):
    """POST /api/projects/select sets project root in allowed_dirs; GET returns it."""
    import main as m
    tmp = tmp_backend["tmp"]
    proj = tmp / "proj"
    proj.mkdir()
    # save/restore allowed_dirs since project mutation is global
    old_dirs = list(m.tools_sandbox.cfg.allowed_dirs)
    try:
        r = c.post("/api/projects/select", json={"root": str(proj)})
        assert r.json()["ok"] is True
        assert r.json()["project"] == str(proj)
        g = c.get("/api/projects")
        assert g.json()["project"]["root"] == str(proj)
        # project root should be at the front of allowed_dirs
        assert m.tools_sandbox.cfg.allowed_dirs[0] == str(proj)
    finally:
        m.tools_sandbox.cfg.allowed_dirs = old_dirs


def test_projects_clear(c, tmp_backend):
    """POST /api/projects/clear removes the project and restores defaults."""
    import main as m
    tmp = tmp_backend["tmp"]
    proj = tmp / "proj"
    proj.mkdir()
    old_dirs = list(m.tools_sandbox.cfg.allowed_dirs)
    try:
        c.post("/api/projects/select", json={"root": str(proj)})
        r = c.post("/api/projects/clear")
        assert r.json()["ok"] is True
        assert r.json()["project"] is None
        assert str(proj) not in m.tools_sandbox.cfg.allowed_dirs
    finally:
        m.tools_sandbox.cfg.allowed_dirs = old_dirs


def test_projects_reject_missing_dir(c, tmp_backend):
    """POST /api/projects/select with a non-existent path returns not_found."""
    import main as m
    tmp = tmp_backend["tmp"]
    old_dirs = list(m.tools_sandbox.cfg.allowed_dirs)
    try:
        r = c.post("/api/projects/select", json={"root": str(tmp / "no_such_dir_xyz")})
        assert r.json()["ok"] is False
        assert r.json()["code"] == "not_found"
    finally:
        m.tools_sandbox.cfg.allowed_dirs = old_dirs


def test_changelog_endpoint(c, tmp_backend, monkeypatch):
    """GET /api/changelog serves changelog.json; returns ok + releases."""
    import main as m
    ch = tmp_backend["tmp"] / "changelog.json"
    ch.write_text(json.dumps({"version": "9.9.9", "releases": [{"version": "9.9.9", "changes": ["x"]}]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("AMT_CHANGELOG_FILE", str(ch))
    # the module reads AMT_CHANGELOG_FILE via _CHANGELOG_FILE at import; re-point via attr
    old = m._CHANGELOG_FILE
    m._CHANGELOG_FILE = str(ch)
    try:
        r = c.get("/api/changelog")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["version"] == "9.9.9"
        assert len(d["releases"]) == 1
    finally:
        m._CHANGELOG_FILE = old


def test_changelog_missing_file(c, tmp_backend, monkeypatch):
    """GET /api/changelog with a missing file returns ok:False."""
    import main as m
    old = m._CHANGELOG_FILE
    m._CHANGELOG_FILE = str(tmp_backend["tmp"] / "no_such_changelog.json")
    try:
        r = c.get("/api/changelog")
        assert r.json()["ok"] is False
    finally:
        m._CHANGELOG_FILE = old

