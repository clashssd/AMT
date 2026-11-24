"""Tests for the extension loader."""
import os
import json
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def api_c(tmp_backend, monkeypatch):
    """TestClient + extensions dir isolated to the real examples folder."""
    monkeypatch.setenv("AMT_EXTENSIONS_DIR", os.path.join(os.path.dirname(__file__), "..", "extensions"))
    from ai_engine import extensions as ext
    ext._REGISTRY.clear()
    ext._LOADED = False
    c = TestClient(main.app)
    return c


def test_extensions_list_endpoint(api_c):
    r = api_c.get("/api/extensions/list")
    assert r.status_code == 200
    names = [e["name"] for e in r.json()["extensions"]]
    assert "example" in names


def test_ext_index_js_endpoint(api_c):
    r = api_c.get("/api/extensions/example/index.js")
    assert r.status_code == 200
    assert "init" in r.text
    # unknown ext → 404
    r2 = api_c.get("/api/extensions/nonexistent/index.js")
    assert r2.status_code == 404


def test_ext_toggle_and_state(api_c, tmp_backend):
    """toggle disables an extension; state reflects it; list shows enabled=False."""
    # выключить
    r = api_c.post("/api/extensions/example/toggle", json={"enabled": False})
    assert r.json()["ok"] is True
    assert r.json()["enabled"] is False
    # в списке — enabled=False
    lst = api_c.get("/api/extensions/list").json()["extensions"]
    ex = next(e for e in lst if e["name"] == "example")
    assert ex["enabled"] is False
    # state endpoint
    st = api_c.get("/api/extensions/state").json()["state"]
    assert st.get("example") is False
    # обратно включить
    r2 = api_c.post("/api/extensions/example/toggle", json={"enabled": True})
    assert r2.json()["enabled"] is True


def test_ext_toggle_unknown(api_c):
    r = api_c.post("/api/extensions/does_not_exist/toggle", json={"enabled": True})
    assert r.json()["ok"] is False
    assert r.json()["code"] == "not_found"


def test_ext_reload(api_c):
    r = api_c.post("/api/extensions/reload")
    assert r.json()["ok"] is True
    assert r.json()["count"] >= 1



@pytest.fixture
def ext_env(tmp_path, monkeypatch):
    """Создаёт temp extensions dir с двумя расширениями и направяет туда loader."""
    ext_root = tmp_path / "extensions"
    ext_root.mkdir()

    # Пример: корректное расширение с backend
    good = ext_root / "good"
    good.mkdir()
    (good / "manifest.json").write_text(
        json.dumps({"name": "good", "version": "1.0.0", "backend": True, "frontend": True}),
        encoding="utf-8"
    )
    (good / "backend.py").write_text(
        "def init(ctx):\n    ctx['loaded'] = True\n", encoding="utf-8"
    )

    # Пример: расширение с ошибкой в backend (не должно ронять)
    bad = ext_root / "bad"
    bad.mkdir()
    (bad / "manifest.json").write_text(
        json.dumps({"name": "bad", "version": "1.0.0", "backend": True}),
        encoding="utf-8"
    )
    (bad / "backend.py").write_text(
        "def init(ctx):\n    raise RuntimeError('boom')\n", encoding="utf-8"
    )

    # Расширение без manifest — должно игнорироваться
    (ext_root / "no_manifest").mkdir()

    monkeypatch.setenv("AMT_EXTENSIONS_DIR", str(ext_root))

    # сбросим регистр loader, чтобы пересканировать
    from ai_engine import extensions as ext
    ext._REGISTRY.clear()
    ext._LOADED = False
    return ext, ext_root


@pytest.fixture
def ext_api(tmp_backend, tmp_path, monkeypatch):
    """TestClient + изолированный каталог расширений (temp) + state в tmp."""
    ext_root = tmp_path / "ext_root"
    ext_root.mkdir()
    monkeypatch.setenv("AMT_EXTENSIONS_DIR", str(ext_root))
    from ai_engine import extensions as ext
    ext._REGISTRY.clear()
    ext._LOADED = False
    c = TestClient(main.app)
    return c, ext_root, ext


def test_loads_good_extension(ext_env):
    ext, ext_root = ext_env
    reg = ext.load_extensions()
    assert "good" in reg
    assert reg["good"]["ok"] is True


def test_bad_extension_does_not_crash(ext_env):
    ext, _ = ext_env
    reg = ext.load_extensions()
    # bad расширение: ok=False, но приложение не упало
    assert "bad" in reg
    assert reg["bad"]["ok"] is False
    # good при этом загружено
    assert reg["good"]["ok"] is True


def test_no_manifest_skipped(ext_env):
    ext, ext_root = ext_env
    reg = ext.load_extensions()
    # папка без manifest не в реестре
    for name in reg:
        assert name != "no_manifest"


def test_list_for_api_shape(ext_env):
    ext, _ = ext_env
    lst = ext.list_for_api()
    names = [e["name"] for e in lst]
    assert "good" in names
    for e in lst:
        assert "version" in e
        assert "ok" in e


class TestExtensionsAddRemove:
    """Новые эндпоинты /api/extensions/add и /api/extensions/{name}/remove."""

    def test_add_extension_copies_folder(self, ext_api, tmp_path):
        c, ext_root, ext = ext_api
        # исходная папка-расширение вне корня
        src = tmp_path / "new_ext"
        src.mkdir()
        (src / "manifest.json").write_text(
            json.dumps({"name": "new_ext", "version": "0.1.0", "frontend": True}), encoding="utf-8"
        )
        r = c.post("/api/extensions/add", json={"source_dir": str(src)})
        assert r.json()["ok"] is True
        # папка скопирована в корень
        assert (ext_root / "new_ext" / "manifest.json").exists()
        # расширение в списке
        lst = c.get("/api/extensions/list").json()
        assert "new_ext" in [e["name"] for e in lst["extensions"]]

    def test_add_rejects_folder_without_manifest(self, ext_api, tmp_path):
        c, ext_root, ext = ext_api
        src = tmp_path / "not_ext"
        src.mkdir()
        r = c.post("/api/extensions/add", json={"source_dir": str(src)})
        assert r.json()["ok"] is False
        assert "manifest" in r.json()["error"]

    def test_add_rejects_missing_folder(self, ext_api, tmp_path):
        c, _, _ = ext_api
        r = c.post("/api/extensions/add", json={"source_dir": str(tmp_path / "nope")})
        assert r.json()["ok"] is False

    def test_add_duplicate_rejected(self, ext_api, tmp_path):
        c, ext_root, ext = ext_api
        src1 = tmp_path / "dup"
        src1.mkdir()
        (src1 / "manifest.json").write_text(json.dumps({"name": "dup"}), encoding="utf-8")
        assert c.post("/api/extensions/add", json={"source_dir": str(src1)}).json()["ok"] is True
        # вторая папка с тем же именем — отклоняется
        src2 = tmp_path / "other" / "dup"
        src2.mkdir(parents=True)
        (src2 / "manifest.json").write_text(json.dumps({"name": "dup"}), encoding="utf-8")
        r = c.post("/api/extensions/add", json={"source_dir": str(src2)})
        assert r.json()["ok"] is False

    def test_remove_extension_deletes_folder(self, ext_api, tmp_path):
        c, ext_root, ext = ext_api
        src = tmp_path / "removeme"
        src.mkdir()
        (src / "manifest.json").write_text(json.dumps({"name": "removeme", "version": "1"}), encoding="utf-8")
        c.post("/api/extensions/add", json={"source_dir": str(src)})
        assert (ext_root / "removeme").exists()
        r = c.post("/api/extensions/removeme/remove")
        assert r.json()["ok"] is True
        assert not (ext_root / "removeme").exists()
        lst = c.get("/api/extensions/list").json()
        assert "removeme" not in [e["name"] for e in lst["extensions"]]

    def test_remove_unknown_extension(self, ext_api):
        c, _, _ = ext_api
        r = c.post("/api/extensions/ghost/remove")
        assert r.json()["ok"] is False
        assert r.json().get("code") == "not_found" or "error" in r.json()

    def test_list_includes_dir(self, ext_api):
        c, ext_root, _ = ext_api
        r = c.get("/api/extensions/list")
        assert r.json().get("dir") == str(ext_root)

    def test_remove_clears_state_entry(self, ext_api, tmp_backend):
        c, ext_root, ext = ext_api
        src = ext_root / "statext"
        src.mkdir()
        (src / "manifest.json").write_text(json.dumps({"name": "statext"}), encoding="utf-8")
        # выключить, чтобы state-запись появилась
        c.post("/api/extensions/statext/toggle", json={"enabled": False})
        state_file = json.loads(open(tmp_backend["tmp"] / "extensions_state.json", encoding="utf-8").read()) \
            if (tmp_backend["tmp"] / "extensions_state.json").exists() else {}
        assert state_file.get("statext") is False
        r = c.post("/api/extensions/statext/remove")
        assert r.json()["ok"] is True
        state_file2 = json.loads(open(tmp_backend["tmp"] / "extensions_state.json", encoding="utf-8").read())
        assert "statext" not in state_file2
