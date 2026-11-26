# backend/rag_server/parsers.py
"""File -> chunk extraction for the local RAG server.

Each parser returns a list of Chunk dicts:
    {
      "text": str,
      "source": str,        # relative or absolute path of the file
      "locator": str,       # "L<start>-L<end>" | "P<page>" | "S<sheet>" | ""
      "kind": str,          # "code" | "text" | "table" | "media" | "unknown"
    }

Parsers use best-effort import guards: if an optional lib is missing the file
falls back to a raw-text (or binary-skip) chunk so indexing never hard-crashes.
"""
from __future__ import annotations
import os, re, hashlib
from typing import Iterator

# Chunk size target for prose (~400 chars) with ~60 char overlap.
CHUNK_TARGET = 400
CHUNK_OVERLAP = 60
# Hard cap on a single chunk so one giant line can't blow the context.
CHUNK_MAX = 2000


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:16]


def _relpath(path: str, base: str) -> str:
    try:
        return os.path.relpath(path, base)
    except Exception:
        return path


def _code_split(text: str, path: str, ext: str) -> list[dict]:
    """Split source code by lines with a soft cap; locator = line range."""
    lines = text.splitlines()
    chunks: list[dict] = []
    start = 0
    while start < len(lines):
        buf, chars = [], 0
        end = start
        while end < len(lines) and (chars < CHUNK_MAX or not buf):
            buf.append(lines[end])
            chars += len(lines[end]) + 1
            end += 1
            # stop once we reach target and on a blank-line boundary if possible
            if chars >= CHUNK_TARGET and end < len(lines) and lines[end] == "":
                end += 1
                break
        if buf:
            chunks.append({
                "text": "\n".join(buf).strip(),
                "source": path,
                "locator": f"L{start + 1}-L{end}",
                "kind": "code",
            })
        start = end
        if start == len(lines):
            break
    return [c for c in chunks if c["text"]]


def _prose_split(text: str, path: str, locator_prefix: str = "") -> list[dict]:
    """Split prose by paragraph/section; locator optional."""
    chunks: list[dict] = []
    # Normalize whitespace but keep line boundaries meaningful.
    text = re.sub(r"\n{3,}", "\n\n", text)
    buf = ""
    for part in text.split("\n\n"):
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 1 > CHUNK_TARGET and buf:
            chunks.append({"text": buf.strip(), "source": path,
                          "locator": locator_prefix, "kind": "text"})
            buf = part[-CHUNK_OVERLAP:] if len(part) > CHUNK_OVERLAP else ""
        else:
            buf = (buf + "\n" + part) if buf else part
    if buf.strip():
        chunks.append({"text": buf.strip(), "source": path, "locator": locator_prefix, "kind": "text"})
    return [c for c in chunks if c["text"]]


def _extract_text_file(path: str, base: str, ext: str) -> list[dict]:
    with open(path, "rb") as f:
        raw = f.read()
    # Sniff encoding.
    text = None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp",
               ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh",
               ".sql", ".html", ".css", ".vue", ".svelte", ".csharp", ".mjs"):
        return _code_split(text, path, ext)
    return _prose_split(text, path)


def _extract_docx(path: str, base: str) -> list[dict]:
    try:
        import docx  # python-docx
    except Exception:
        return _extract_text_file(path, base, ".txt")
    try:
        d = docx.Document(path)
    except Exception:
        return _extract_text_file(path, base, ".txt")
    parts = []
    for p in d.paragraphs:
        t = (p.text or "").strip()
        if t:
            style = p.style.name.lower() if p.style else ""
            if any(h in style for h in ("heading", "title")):
                parts.append("# " + t)
            else:
                parts.append(t)
    # tables
    for tbl in d.tables:
        for row in tbl.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            parts.append(" | ".join(cells))
    return _prose_split("\n".join(parts), path)


def _extract_pdf(path: str, base: str) -> list[dict]:
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(path)
        chunks = []
        for i, page in enumerate(reader.pages):
            t = (page.extract_text() or "").strip()
            if t:
                chunks.append({"text": t, "source": path,
                               "locator": f"P{i + 1}", "kind": "text"})
        return chunks
    except Exception:
        # Fall back to scanning the raw bytes for text — crude but keeps it
        # from silently returning nothing.
        try:
            with open(path, "rb") as f:
                raw = f.read()
            text = raw.decode("utf-8", errors="ignore")
            text = re.sub(r"[^\x20-\x7E\n]", "", text)
            return _prose_split(text, path)
        except Exception:
            return []


def _extract_xlsx(path: str, base: str) -> list[dict]:
    try:
        import openpyxl  # type: ignore
    except Exception:
        return _extract_text_file(path, base, ".txt")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    chunks = []
    for ws in wb.worksheets:
        header = None
        rows_buf = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if header is None:
                header = cells
                continue
            line = " | ".join(cells)
            if line.strip():
                rows_buf.append(line)
                if len(rows_buf) >= 40:
                    chunks.append({"text": " | ".join(header) + "\n" + "\n".join(rows_buf),
                                   "source": path, "locator": f"S{ws.title}", "kind": "table"})
                    rows_buf = []
        if rows_buf:
            chunks.append({"text": " | ".join(header or []) + "\n" + "\n".join(rows_buf),
                           "source": path, "locator": f"S{ws.title}", "kind": "table"})
    return chunks


def _extract_pptx(path: str, base: str) -> list[dict]:
    try:
        import pptx  # type: ignore
    except Exception:
        return _extract_text_file(path, base, ".txt")
    prs = pptx.Presentation(path)
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = (shape.text_frame.text or "").strip()
                if t:
                    texts.append(t)
        if texts:
            parts.append(f"--- Slide {i} ---\n" + "\n".join(texts))
    return _prose_split("\n\n".join(parts), path)


def _extract_image(path: str, base: str) -> list[dict]:
    """Image -> placeholder chunk (no OCR / vision model installed).

    Keeps a record so the file is represented in the index; the locator is the
    filename. A future optional vision profile can replace this body.
    """
    return [{
        "text": f"[image: {os.path.basename(path)}] (no OCR/vision model available in this profile)",
        "source": path, "locator": "", "kind": "media",
    }]


# extension -> parser map
_PARSERS = {
    ".py": _extract_text_file, ".js": _extract_text_file, ".ts": _extract_text_file,
    ".jsx": _extract_text_file, ".tsx": _extract_text_file, ".go": _extract_text_file,
    ".rs": _extract_text_file, ".java": _extract_text_file, ".c": _extract_text_file,
    ".cpp": _extract_text_file, ".h": _extract_text_file, ".hpp": _extract_text_file,
    ".cs": _extract_text_file, ".rb": _extract_text_file, ".php": _extract_text_file,
    ".swift": _extract_text_file, ".kt": _extract_text_file, ".scala": _extract_text_file,
    ".sh": _extract_text_file, ".sql": _extract_text_file, ".html": _extract_text_file,
    ".css": _extract_text_file, ".vue": _extract_text_file, ".svelte": _extract_text_file,
    ".md": _extract_text_file, ".markdown": _extract_text_file,
    ".txt": _extract_text_file, ".json": _extract_text_file, ".yaml": _extract_text_file,
    ".yml": _extract_text_file, ".toml": _extract_text_file, ".ini": _extract_text_file,
    ".csv": _extract_text_file, ".log": _extract_text_file, ".r": _extract_text_file,
    ".lua": _extract_text_file, ".pl": _extract_text_file,
    ".docx": _extract_docx,
    ".pdf": _extract_pdf,
    ".xlsx": _extract_xlsx, ".xlsm": _extract_xlsx,
    ".pptx": _extract_pptx,
    ".png": _extract_image, ".jpg": _extract_image, ".jpeg": _extract_image,
    ".gif": _extract_image, ".bmp": _extract_image, ".webp": _extract_image, ".svg": _extract_image,
}

# Directories / files we never index (noise + safety).
_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
              ".idea", ".vscode", "dist", "build", ".next", ".nuxt", "target",
              ".amt_rag", ".rag"}  # never index the RAG data store itself
_SKIP_FILES = {".DS_Store", "Thumbs.db", ".gitkeep", "mcp_key.key"}


def parse_file(path: str, base: str) -> list[dict]:
    ext = os.path.splitext(path)[1].lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        # Unknown binary type: skip quietly (don't poison the index).
        return []
    try:
        chunks = parser(path, base, ext)
    except Exception:
        # Crude last resort for text-ish unknowns.
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return _prose_split(f.read(), path)
        except Exception:
            return []
    return chunks


def should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.endswith(".lock")


def is_indexable(path: str) -> bool:
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1].lower()
    if name in _SKIP_FILES:
        return False
    return ext in _PARSERS


def walk_files(root: str) -> Iterator[str]:
    """Yield indexable file paths under root (skips venv/node_modules/etc.)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if is_indexable(full):
                yield full
