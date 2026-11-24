"""Tests for the file generation engine + endpoints."""
import json
import pytest
from fastapi.testclient import TestClient

import main
from ai_engine import filegen


def test_generate_docx_valid():
    data, fname = filegen.generate_file("docx", "Отчёт\n# Введение\nтекст\n- п1", "Отчёт.docx")
    assert fname.endswith(".docx")
    assert data[:2] == b"PK"  # zip container


def test_generate_xlsx_from_spec():
    spec = json.dumps({"sheets": [{"name": "L1", "rows": [["a", "b"], [1, 2]]}]})
    data, fname = filegen.generate_file("xlsx", spec, "tab.xlsx")
    assert data[:2] == b"PK"


def test_generate_pptx_from_spec():
    spec = json.dumps({"slides": [{"title": "S1", "body": "b"}, {"title": "S2", "body": "c"}]})
    data, fname = filegen.generate_file("pptx", spec, "pres.pptx")
    assert data[:2] == b"PK"


def test_generate_pdf_valid():
    data, fname = filegen.generate_file("pdf", "line1\nline2", "d.pdf")
    assert data[:4] == b"%PDF"


def test_generate_code_files():
    for ft, content in [("py", "print(1)"), ("md", "# hi"), ("json", '{"a":1}'), ("csv", "a,b\n1,2"), ("txt", "hi")]:
        data, fname = filegen.generate_file(ft, content, "f." + ft)
        assert len(data) > 0


def test_preview_html_for_code():
    h = filegen.preview_html("py", "def f(): pass")
    assert "<html" in h


def test_preview_csv_table():
    h = filegen.preview_html("csv", "a,b\n1,2")
    assert "<table" in h


def test_unsupported_media_raises():
    with pytest.raises(NotImplementedError):
        filegen.generate_file("png", "", "x")
    with pytest.raises(NotImplementedError):
        filegen.generate_file("mp4", "", "x")
    with pytest.raises(NotImplementedError):
        filegen.generate_file("mp3", "", "x")


@pytest.fixture
def c(tmp_backend):
    return TestClient(main.app)


def test_filegen_generate_endpoint(c):
    r = c.post("/api/filegen/generate", json={"filetype": "py", "content": "print('hi')", "title": "main.py"})
    assert r.json()["status"] == "ok"
    assert r.json()["filename"] == "main.py"
    assert r.json()["b64"]


def test_filegen_preview_endpoint(c):
    r = c.post("/api/filegen/preview", json={"filetype": "md", "content": "# hi", "title": "t"})
    assert r.json()["status"] == "ok"
    assert "<html" in r.json()["html"]


def test_filegen_not_implemented_media(c):
    r = c.post("/api/filegen/generate", json={"filetype": "png", "content": "", "title": "x"})
    assert r.json()["status"] == "not_implemented"
