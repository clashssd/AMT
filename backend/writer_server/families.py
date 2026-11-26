# backend/writer_server/families.py
"""Per-family content builders + post-write validation for the Writer server.

Each build_* returns (bytes, meta) or raises a typed Err payload via _fail.
Post-write validate_* opens the artifact with the family's library and checks
structure (magic-bytes, sheet/paragraph/slide counts, AST parse, CSV columns).

Reuses ai_engine.filegen where it exists (Office/PDF generators are already
battle-tested there); falls back to a DEPENDENCY_MISSING hint when the
optional library is absent.
"""
from __future__ import annotations
import json, io, os, zipfile, csv, base64
from typing import Optional, Tuple, List

from .core import Err

def _fail(code: str, msg: str, **extra):
    return Err.payload(code, msg, extra or None)


# ===== Text & data families =====
def build_text(content: str, title: str = "") -> Tuple[Optional[bytes], dict, Optional[dict]]:
    if content is None:
        return None, {}, _fail(Err.INVALID_SPEC, "content is empty")
    data = content.encode("utf-8")
    return data, {"encoding": "utf-8", "lines": content.count("\n") + 1}, None

def build_data(spec, title: str = "") -> Tuple[Optional[bytes], dict, Optional[dict]]:
    """spec: a python object (json), or {"yaml": "..."}, or a CSV string.
    The tool layer hands it a parsed value; we normalize + validate."""
    if isinstance(spec, dict) and spec.get("yaml"):
        return _build_yaml(spec["yaml"])
    if isinstance(spec, str):
        s = spec.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                spec = json.loads(s)
            except Exception:
                return _build_csv(s)
        else:
            return _build_csv(s)
    # JSON object/array
    try:
        data = json.dumps(spec, ensure_ascii=False, indent=2).encode("utf-8")
        # round-trip validation
        json.loads(data.decode("utf-8"))
        return data, {"fmt": "json"}, None
    except Exception as e:
        return None, {}, _fail(Err.INVALID_SPEC, f"JSON spec invalid: {str(e)[:120]}")

def _build_yaml(text: str):
    try:
        import yaml
    except ImportError:
        return None, {}, _fail(Err.DEPENDENCY_MISSING, "PyYAML not installed")
    try:
        obj = yaml.safe_load(text)
        data = yaml.safe_dump(obj, allow_unicode=True).encode("utf-8")
        return data, {"fmt": "yaml"}, None
    except Exception as e:
        return None, {}, _fail(Err.INVALID_SPEC, f"YAML invalid: {str(e)[:120]}")

def _build_csv(text: str):
    rows = list(csv.reader(io.StringIO(text)))
    # column-consistency check
    widths = {len(r) for r in rows if r}
    if len(widths) > 1:
        return None, {}, _fail(Err.INVALID_SPEC, f"CSV columns inconsistent: {sorted(widths)}")
    return text.encode("utf-8"), {"fmt": "csv", "rows": len(rows), "cols": len(rows[0]) if rows else 0}, None


# ===== Code =====
def build_code(spec, lang: str = "py") -> Tuple[Optional[bytes], dict, Optional[dict]]:
    """spec: {"scaffold": {...}} or a raw code string. AST-parse python for syntax."""
    if isinstance(spec, dict):
        code = spec.get("code", "")
    else:
        code = str(spec or "")
    data = code.encode("utf-8")
    if lang in ("py", "python"):
        import ast
        try:
            ast.parse(code)
        except SyntaxError as e:
            return None, {}, _fail(Err.VALIDATION_FAILED, f"Python syntax error: {e.msg} (line {e.lineno})")
    return data, {"lang": lang}, None


# ===== Office + PDF (reuse ai_engine.filegen) =====
def build_office(family: str, spec, title: str = "") -> Tuple[Optional[bytes], dict, Optional[dict]]:
    """family in {docx, xlsx, pptx, pdf}. Reuse ai_engine.filegen when available."""
    try:
        from ai_engine import filegen
    except ImportError:
        # fallback: minimal builders
        if family == "docx":
            return _build_docx_fallback(spec, title)
        if family == "pdf":
            return _build_pdf_fallback(spec, title)
        return None, {}, _fail(Err.DEPENDENCY_MISSING, "ai_engine.filegen unavailable and no fallback for this family")
    try:
        data, fname = filegen.generate_file(family, _spec_to_content(family, spec), title)
        return data, {"family": family, "filename": fname}, None
    except NotImplementedError as e:
        return None, {}, _fail(Err.FORMAT_UNSUPPORTED, str(e)[:150])
    except ImportError as e:
        return None, {}, _fail(Err.DEPENDENCY_MISSING, f"Office library missing: {str(e)[:120]}")
    except Exception as e:
        return None, {}, _fail(Err.INVALID_SPEC, f"Office build failed: {str(e)[:150]}")

def _spec_to_content(family: str, spec) -> str:
    """filegen expects a string content for docx/pdf, JSON-ish for xlsx/pptx."""
    if isinstance(spec, str):
        return spec
    if isinstance(spec, (dict, list)):
        return json.dumps(spec, ensure_ascii=False)
    return str(spec or "")


def merge_source(spec, source_b64: str, family: str):
    """Read a user-sent file (base64) and merge its structure into the spec.

    The model already produced `spec` from the user's instruction; `source_b64`
    is the actual file the user uploaded. For Office/data families we parse the
    source so the result preserves real data (rows, paragraphs) rather than
    regenerating from scratch. Returns the (possibly-merged) spec.
    If the source can't be parsed for this family, returns spec unchanged and
    the caller proceeds with the model-generated spec only.
    """
    if not source_b64 or not family:
        return spec
    import base64 as _b64
    try:
        raw = _b64.b64decode(source_b64)
    except Exception:
        return spec
    fam = (family or "").lower()
    try:
        if fam == "xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), read_only=False, data_only=False)
            merged_sheets = []
            for ws in wb.worksheets:
                # Keep formula strings (e.g. "=D5-D4") so they're preserved as real formulas
                rows = []
                for row in ws.iter_rows(values_only=False):
                    rows.append([
                        cell.value if cell.value is not None else None
                        for cell in row
                    ])
                merged_sheets.append({"name": ws.title, "rows": rows})
            # Model's spec may add new sheets or override same-named ones.
            if isinstance(spec, dict) and spec.get("sheets"):
                model_sheets = spec["sheets"] if isinstance(spec["sheets"], list) else [spec["sheets"]]
                for s in model_sheets:
                    if not isinstance(s, dict):
                        continue
                    name = s.get("name")
                    if name and any(m.get("name") == name for m in merged_sheets):
                        # override the matching sheet
                        merged_sheets = [s if m.get("name") == name else m for m in merged_sheets]
                    else:
                        merged_sheets.append(s)
            return {"sheets": merged_sheets}
        if fam == "docx":
            from docx import Document
            doc = Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs)
            # Append the model's instruction so it can modify, not just echo.
            return (text + "\n\n" + _spec_to_content(family, spec)) if spec is not None else text
        if fam in ("csv", "json", "yaml"):
            # Reuse the parsed source as the base data value
            text = raw.decode("utf-8", "ignore")
            return text
        if fam == "pdf":
            # Extract text if pypdf is available; otherwise just fall back to spec
            try:
                import pypdf
                r = pypdf.PdfReader(io.BytesIO(raw))
                text = "\n".join((pg.extract_text() or "") for pg in r.pages)
                return (text + "\n\n" + _spec_to_content(family, spec)) if spec else text
            except Exception:
                return spec
    except Exception:
        return spec
    return spec

def _build_docx_fallback(spec, title):
    try:
        from docx import Document
    except ImportError:
        return None, {}, _fail(Err.DEPENDENCY_MISSING, "python-docx not installed")
    text = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
    from docx import Document
    doc = Document()
    if title:
        doc.add_heading(title, level=0)
    for para in text.split("\n"):
        if para.strip().startswith("#"):
            doc.add_heading(para.lstrip("# ").strip(), level=1)
        elif para.strip().startswith("- "):
            doc.add_paragraph(para[2:], style="List Bullet")
        else:
            doc.add_paragraph(para)
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue(), {"family": "docx", "paragraphs": len(doc.paragraphs)}, None

def _build_pdf_fallback(spec, title):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return None, {}, _fail(Err.DEPENDENCY_MISSING, "reportlab not installed")
    text = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4; y = h - 56
    c.setFont("Helvetica-Bold", 18); c.drawString(56, y, (title or "Document")[:80]); y -= 24
    c.setFont("Helvetica", 11)
    for line in text.split("\n"):
        if y < 56:
            c.showPage(); c.setFont("Helvetica", 11); y = h - 56
        c.drawString(56, y, line[:110]); y -= 16
    c.save()
    return buf.getvalue(), {"family": "pdf", "pages": 1}, None


# ===== Archive =====
def build_archive(spec) -> Tuple[Optional[bytes], dict, Optional[dict]]:
    """spec: {"files": {name: b64content}, "format": "zip"|"tar"}."""
    fmt = (spec.get("format", "zip")).lower()
    files = spec.get("files", {})
    if fmt not in ("zip", "tar"):
        return None, {}, _fail(Err.FORMAT_UNSUPPORTED, f"archive format '{fmt}' not supported (use zip or tar)")
    total_uncomp = 0
    if fmt == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, b64 in files.items():
                if ".." in name or name.startswith("/"):
                    return None, {}, _fail(Err.PATH_TRAVERSAL, f"archive entry '{name}' escapes root")
                raw = base64.b64decode(b64 or "")
                total_uncomp += len(raw)
                zf.writestr(name, raw)
        err = None
        import zlib
        # rough compression ratio check
        comp = buf.tell()
        if total_uncomp and comp:
            ratio = total_uncomp / max(comp, 1)
            if ratio > 100 or total_uncomp > 500 * 1024 * 1024:
                err = Err.LIMIT_EXCEEDED
        if err:
            return None, {}, _fail(err, f"archive limit exceeded (uncompressed {total_uncomp} bytes)")
        return buf.getvalue(), {"format": "zip", "entries": len(files)}, None
    # tar
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, b64 in files.items():
            if ".." in name or name.startswith("/"):
                return None, {}, _fail(Err.PATH_TRAVERSAL, f"archive entry '{name}' escapes root")
            raw = base64.b64decode(b64 or "")
            total_uncomp += len(raw)
            import tarfile as _tf
            ti = _tf.TarInfo(name)
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
    return buf.getvalue(), {"format": "tar", "entries": len(files)}, None


# ===== Magic-byte + structure validation =====
_MAGIC = {
    "docx": b"PK\x03\x04", "xlsx": b"PK\x03\x04", "pptx": b"PK\x03\x04",
    "pdf": b"%PDF", "zip": b"PK\x03\x04", "png": b"\x89PNG",
    "mp3": b"ID3", "wav": b"RIFF",
}

def validate(family: str, data: bytes) -> dict:
    """Post-write structure check. Returns {valid: bool, notes: [...], code?: ...}."""
    notes = []
    # 1) magic-byte sanity for binary families
    fam = (family or "").lower()
    if fam in _MAGIC:
        magic = _MAGIC[fam]
        if not data.startswith(magic) and not data[:4] in (b"PK\x03\x04", b"%PDF", b"\x89PNG", b"ID3", b"RIFF"):
            # docx/xlsx/pptx/zip all start with PK; pdf with %PDF
            expected = b"%PDF" if fam == "pdf" else b"PK\x03\x04"
            if not data.startswith(expected[:4]):
                return {"valid": False, "code": Err.VALIDATION_FAILED,
                        "notes": [f"magic bytes for {fam} do not match"]}
    # 2) family-specific structure check
    try:
        if fam == "docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            notes.append(f"docx: {len(doc.paragraphs)} paragraphs")
        elif fam in ("xlsx", "sheet"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            notes.append(f"xlsx: {len(wb.worksheets)} sheets, formulas: "
                         + str(any(c and str(c).startswith("=") for ws in wb.worksheets for row in ws.iter_rows() for c in row)))
        elif fam == "pptx":
            from pptx import Presentation
            prs = Presentation(io.BytesIO(data))
            notes.append(f"pptx: {len(prs.slides)} slides")
        elif fam == "pdf":
            txt = data.decode("latin-1", "ignore")
            notes.append(f"pdf: {txt.count(' /Page ')} page markers")
        elif fam in ("py", "python"):
            import ast; ast.parse(data.decode("utf-8")); notes.append("code: parses to AST")
        elif fam == "csv":
            rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
            widths = {len(r) for r in rows if r}
            if len(widths) > 1:
                return {"valid": False, "code": Err.VALIDATION_FAILED,
                        "notes": [f"CSV column mismatch: {sorted(widths)}"]}
            notes.append(f"csv: {len(rows)} rows x {len(rows[0]) if rows else 0} cols")
        elif fam in ("json",):
            json.loads(data.decode("utf-8")); notes.append("json: valid")
    except ImportError as e:
        notes.append(f"validation lib missing ({str(e)[:40]}) — structural check skipped")
    except Exception as e:
        return {"valid": False, "code": Err.VALIDATION_FAILED, "notes": [f"structural check failed: {str(e)[:150]}"]}
    return {"valid": True, "notes": notes}
