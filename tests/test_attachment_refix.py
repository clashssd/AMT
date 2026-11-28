"""Regression tests for the 'AI does not see attached photo/file' fix.

Pins the two root causes that made the model say «не вижу фото»:

1. A stored attachment whose absolute `path` is stale (app rebuilt / moved /
   dev↔frozen switch) no longer lives under the CURRENT FILES_DIR. The
   attachment loop used to `continue` (silently drop) → only the filename
   reached the model. Now it re-resolves the name against the current
   FILES_DIR via _resolve_attachment_name.

2. An attachment with an empty / `application/octet-stream` mime_type (e.g. a
   pasted .jpg whose file.type came through empty) used to fall into the
   generic `[Файл: name]` placeholder in parse_file_for_ai → no base64 data-URL
   → the model saw no pixels. Now the loop normalizes the mime via
   _guess_mime before parsing, so images route to the image branch.

These tests exercise the pure backend helpers so they run without the full
FastAPI app / LLM provider.
"""
import os
import glob

import main


def _make_file(files_dir, stored_name, content=b"hello"):
    p = os.path.join(files_dir, stored_name)
    with open(p, "wb") as f:
        f.write(content)
    return p


def test_guess_mime_maps_dotted_extension(tmp_path):
    # _guess_mime keeps the dot: MIME_MAP keys are dotted ('.jpg', '.mp4').
    assert main._guess_mime("photo.jpg") == "image/jpeg"
    assert main._guess_mime("photo.JPG") == "image/jpeg"
    assert main._guess_mime("clip.mp4") == "video/mp4"
    assert main._guess_mime("noext") == "application/octet-stream"
    # Unknown-but-known extension still resolves
    assert main._guess_mime("data.xlsx").startswith("application/")


def test_guess_mime_does_not_crash_on_empty(tmp_path):
    assert main._guess_mime("") == "application/octet-stream"


def test_resolve_attachment_name_exact_match(tmp_path, monkeypatch):
    f = _make_file(str(tmp_path), "cbbabc.jpg", b"\xff\xd8")
    monkeypatch.setattr(main, "FILES_DIR", str(tmp_path))
    d = main._resolve_attachment_name("cbbabc.jpg")
    assert d is not None
    assert d["path"] == f
    assert d["mime_type"] == "image/jpeg"
    # filename reported as the ORIGINAL name (not the ts-prefixed stored one)
    assert d["filename"] == "cbbabc.jpg"


def test_resolve_attachment_name_ts_prefix_fallback(tmp_path, monkeypatch):
    # /api/files/upload stores as {ts}_{name}; resolve must find it by name.
    _make_file(str(tmp_path), "1799000000_cbbabc.jpg", b"\xff\xd8")
    monkeypatch.setattr(main, "FILES_DIR", str(tmp_path))
    d = main._resolve_attachment_name("cbbabc.jpg")
    assert d is not None
    assert d["filename"] == "cbbabc.jpg"
    assert "1799000000_cbbabc.jpg" in d["path"]
    assert d["mime_type"] == "image/jpeg"


def test_resolve_attachment_name_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FILES_DIR", str(tmp_path))
    assert main._resolve_attachment_name("does_not_exist.jpg") is None


def test_stale_path_falls_back_to_current_files_dir(tmp_path, tmp_path_factory, monkeypatch):
    """Core regression: a stored absolute path that no longer exists under the
    current FILES_DIR must be re-resolved by filename, NOT silently dropped.

    Replicates the exact decision logic added to call_ai_api's attachment loop.
    """
    old_dir = str(tmp_path_factory.mktemp("old_files"))
    cur_dir = str(tmp_path_factory.mktemp("cur_files"))
    # The file genuinely exists in the CURRENT files dir (ts-prefixed).
    _make_file(cur_dir, "1799000001_cbbabc.jpg", b"\xff\xd8\xff")
    # The attachment dict carries a STALE path from a previous FILES_DIR.
    stale_path = os.path.join(old_dir, "cbbabc.jpg")
    att = {"path": stale_path, "filename": "cbbabc.jpg", "mime_type": "image/jpeg"}

    monkeypatch.setattr(main, "FILES_DIR", cur_dir)

    # Mirror the production loop body:
    path = att.get("path", "")
    fname = att.get("filename", "")
    mime = att.get("mime_type", "")
    if not mime or mime == "application/octet-stream":
        mime = main._guess_mime(fname or path)
    files_dir_real = os.path.realpath(cur_dir)
    real = os.path.realpath(path) if path else ""
    resolved_by_fallback = False
    if not real or not real.startswith(files_dir_real) or not os.path.isfile(real):
        re_resolved = main._resolve_attachment_name(fname) if fname else None
        assert re_resolved is not None, "stale path should re-resolve by name"
        real = os.path.realpath(re_resolved["path"])
        mime = re_resolved.get("mime_type") or mime
        resolved_by_fallback = True

    assert resolved_by_fallback is True
    # Resolved to the real file in the CURRENT dir with a valid image mime.
    assert os.path.isfile(real)
    assert real.endswith("cbbabc.jpg")
    assert mime.startswith("image/")


def test_empty_mime_normalizes_to_image_before_parse(tmp_path, monkeypatch):
    """An attachment with empty mime for a .jpg must be normalized to
    image/jpeg so parse_file_for_ai routes it to the image (base64) branch."""
    _make_file(str(tmp_path), "1799000002_pic.jpg", b"\xff\xd8\xff")
    monkeypatch.setattr(main, "FILES_DIR", str(tmp_path))

    fname = "pic.jpg"
    mime = ""  # e.g. pasted image with empty file.type
    if not mime or mime == "application/octet-stream":
        mime = main._guess_mime(fname)
    assert mime == "image/jpeg"
    assert mime.startswith("image/")  # would enter the image branch in parse_file_for_ai
