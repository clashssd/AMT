# backend/tests/test_rag_server.py
"""Tests for the local RAG server (engine + parsers + MCP tools)."""
import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_server.engine import RAGEngine, KnowledgeBase, tokenize
from rag_server import parsers


def _corpus(root: str) -> list[str]:
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    os.makedirs(os.path.join(root, "code"), exist_ok=True)
    with open(os.path.join(root, "docs", "contract.md"), "w", encoding="utf-8") as f:
        f.write("# Contract\nThe total contract amount is 42000 USD.\n\nPayment: net-30.\n")
    with open(os.path.join(root, "code", "util.py"), "w", encoding="utf-8") as f:
        f.write("def compute_total(items):\n    total = 0\n    for it in items:\n        total += it.get('qty',0) * it.get('price',0)\n    return total\n")
    return [
        os.path.join(root, "docs", "contract.md"),
        os.path.join(root, "code", "util.py"),
    ]


def test_tokenize():
    toks = tokenize("hello World_2 foo bar")
    assert "hello" in toks and "world_2" in toks
    assert "foo" in toks and "bar" in toks


def test_parse_code_chunks_locator():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "x.py")
        with open(p, "w") as f:
            f.write("line a\nline b\nline c\n")
        chunks = parsers.parse_file(p, d)
        assert chunks and chunks[0]["kind"] == "code"
        assert "L" in chunks[0]["locator"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_parser_skips_own_data_dir():
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, ".amt_rag", "bases"), exist_ok=True)
        with open(os.path.join(d, "a.txt"), "w") as f:
            f.write("hello")
        files = list(parsers.walk_files(d))
        rels = [os.path.relpath(x, d) for x in files]
        assert any(r.replace("\\", "/").endswith("a.txt") for r in rels)
        assert not any(".amt_rag" in r.replace("\\", "/") for r in rels)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_incremental_indexing():
    d = tempfile.mkdtemp()
    try:
        files = _corpus(d)
        data = os.path.join(d, ".amt_rag")
        eng = RAGEngine(data)
        kb = eng.get("b", create=True)
        s1 = kb.index_files(files, base_root=d)
        assert s1["indexed"] == 2 and s1["chunks_total"] == 2
        # Re-run on an identical set -> all skipped.
        kb2 = RAGEngine(data).get("b", create=False)
        s2 = kb2.index_files(files, base_root=d)
        assert s2["indexed"] == 0 and s2["skipped"] == 2
        # Modify one file -> only that re-indexes.
        with open(os.path.join(d, "docs", "contract.md"), "a", encoding="utf-8") as f:
            f.write("Amendment: total 45000.\n")
        kb3 = RAGEngine(data).get("b", create=False)
        s3 = kb3.index_files(files, base_root=d)
        assert s3["indexed"] == 1 and s3["skipped"] == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_search_returns_citations():
    d = tempfile.mkdtemp()
    try:
        files = _corpus(d)
        eng = RAGEngine(os.path.join(d, ".amt_rag"))
        kb = eng.get("b", create=True)
        kb.index_files(files, base_root=d)
        res = kb.search("total amount", top_k=3)
        assert res
        assert any("contract.md" in r["source"].replace("\\", "/") for r in res)
        assert all("score" in r and "locator" in r for r in res)
        # exact-function-name search (code)
        res2 = kb.search("compute_total", top_k=3)
        assert any("util.py" in r["source"].replace("\\", "/") for r in res2)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_base_delete():
    d = tempfile.mkdtemp()
    try:
        eng = RAGEngine(os.path.join(d, ".amt_rag"))
        kb = eng.get("gone", create=True)
        kb.index_files(_corpus(d), base_root=d)
        assert any(b["id"] == "gone" for b in eng.list_bases())
        assert eng.delete_base("gone")
        assert not any(b["id"] == "gone" for b in eng.list_bases())
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_mcp_tools_registered():
    from rag_server.server import build_server
    mcp = build_server()
    # list_tools is async on mcp v2
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    for expected in ("index_folder", "search_documents", "read_chunk",
                     "list_bases", "base_info", "delete_base"):
        assert expected in names, f"missing tool {expected}"


def test_tool_schemas_have_input_schema():
    from rag_server.server import build_server
    import asyncio
    mcp = build_server()
    tools = asyncio.run(mcp.list_tools())
    t = {x.name: x for x in tools}["search_documents"]
    # mcp v2 exposes input_schema (snake_case); v1 inputSchema.
    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
    assert schema and "query" in schema.get("properties", {})
