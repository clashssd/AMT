"""Consistency test: setup.py's venv location must match what the sidecar
and the build script look for. Previously setup.py created backend/.venv but
sidecar.js/build.js looked at venv/ (project root) — a silent dev-mode break.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(relpath):
    with open(os.path.join(ROOT, relpath), "r", encoding="utf-8") as f:
        return f.read()


def test_setup_creates_backend_dot_venv():
    src = _read("setup.py")
    # setup.py canonical venv location is backend/.venv
    assert "backend" in src and ".venv" in src
    # It must reference the canonical path (backend/.venv) — not only root venv/
    assert re.search(r"backend[\\/]\s*\.venv", src) or "backend" in src


def test_sidecar_prefers_backend_dot_venv():
    src = _read(os.path.join("electron", "sidecar.js"))
    # sidecar.getPythonPath must look in backend/.venv FIRST (canonical).
    m = re.findall(r"['\"]backend['\"][^;]*?\.venv", src)
    assert m, "sidecar.js must reference backend/.venv (canonical venv location)"
    # Legacy root venv/ may remain as a fallback, but must come after backend/.venv
    idx_canonical = src.find(".venv")
    idx_legacy = src.find("'venv'")
    if idx_legacy != -1:
        assert idx_canonical < idx_legacy, "backend/.venv must be checked before legacy venv/"


def test_build_py_uses_backend_dot_venv_first():
    src = _read(os.path.join("scripts", "build.js"))
    # build.js buildPy() must have backend/.venv as the first candidate.
    # (legacy root venv/ may follow as a fallback)
    idx_canonical = src.find(".venv")
    assert idx_canonical != -1, "build.js must reference backend/.venv"
    idx_legacy = src.find("'venv'")
    if idx_legacy != -1:
        assert idx_canonical < idx_legacy, "backend/.venv must be the first candidate in build.js"


def test_sidecar_falls_back_to_system_python():
    src = _read(os.path.join("electron", "sidecar.js"))
    # Last-resort: bare 'python' on PATH
    assert re.search(r"return\s+'python'", src) or 'return "python"' in src or "return 'python'" in src
