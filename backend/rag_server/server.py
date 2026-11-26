# backend/rag_server/server.py
"""STOIO MCP server exposing the local RAG engine as MCP tools.

Tools (auto-registered into AMT's Tool Registry as mcp__rag__<tool>):
    index_folder   — (re)index a folder into a named knowledge base
    search_documents — hybrid keyword retrieval over a base
    read_chunk     — read a chunk + neighbors for deeper context
    list_bases     — list knowledge bases + stats
    base_info      — stats for one base
    delete_base    — remove a base

Transport: STDIO. Launched by AMT via the preset (command = python -m rag_server).
Data dir: env AMT_RAG_DATA_DIR (defaults to <repo>/.amt_rag).
"""
from __future__ import annotations
import os, json, asyncio, logging

from .engine import RAGEngine
from . import parsers

# The MCP server speaks JSON-RPC over stdout — logging must go to stderr.
logging.basicConfig(level=logging.INFO, stream=os.sys.stderr)
log = logging.getLogger("rag_server")

_DATA_DIR = os.environ.get(
    "AMT_RAG_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".amt_rag"),
)
_engine = RAGEngine(_DATA_DIR)


def _resolve_base(base_id: str):
    kb = _engine.get(base_id, create=True)
    if kb is None:
        raise ValueError(f"Base '{base_id}' not found")
    return kb


def _find_files(root: str) -> list[str]:
    root = os.path.abspath(root)
    if os.path.isfile(root):
        return [root]
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Path not found: {root}")
    files = list(parsers.walk_files(root))
    return files


# ---- build the MCP server (mcp v2 API) ----
def build_server():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer(
        "AMT-RAG",
        description="Local RAG knowledge-base server (keyword/BM25, fully local).",
        instructions=(
            "Index folders of local documents into named knowledge bases, then "
            "retrieve relevant chunks with source+page/line citations. Use "
            "search_documents for questions about the user's files; use "
            "read_chunk for deeper context. If a search returns no relevant "
            "chunks, say so honestly."
        ),
    )

    def _json(result: dict) -> str:
        # structured_output=False would auto-JSON dict returns; we keep it
        # explicit so mcp_manager.call_tool sees a single text block.
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(description=(
        "Index (or incrementally re-index) a folder of files into a named "
        "knowledge base. Unchanged files are skipped by hash+mtime. Returns "
        "stats {indexed, skipped, chunks_total, base}."
    ))
    def index_folder(folder: str, base: str = "default") -> dict:
        kb = _resolve_base(base)
        files = _find_files(folder)
        if not files:
            return {"error": "No indexable files found in the given path.",
                    "base": base, "indexed": 0}
        stats = kb.index_files(files, base_root=os.path.abspath(folder))
        stats["base"] = base
        stats["root"] = os.path.abspath(folder)
        return stats

    @mcp.tool(description=(
        "Hybrid keyword retrieval: return the top-N most relevant chunks from a "
        "knowledge base for a query. Each result has text, source (file), "
        "locator (page/line), kind, score. Pass source_filter to restrict to a "
        "substring of the file path."
    ))
    def search_documents(query: str, base: str = "default",
                         top_k: int = 8, source_filter: str = "") -> dict:
        kb = _resolve_base(base)
        results = kb.search(query, top_k=max(1, min(int(top_k), 50)),
                           source_filter=source_filter or "")
        return {"query": query, "base": base, "count": len(results),
                "results": results}

    @mcp.tool(description=(
        "Read a specific chunk by index from a base, plus its neighbours "
        "(same file, adjacent chunks) for fuller context. chunk_index must "
        "match an index returned by search_documents (use the same base)."
    ))
    def read_chunk(chunk_index: int, base: str = "default",
                   neighbors: int = 2) -> dict:
        kb = _resolve_base(base)
        out = kb.read_chunk(int(chunk_index), neighbors=int(neighbors))
        return {
            "base": base,
            "chunk": {k: out["chunk"].get(k) for k in ("text", "source", "locator", "kind")},
            "neighbors": [
                {k: c.get(k) for k in ("text", "source", "locator", "kind", "_idx")}
                for c in out["neighbors"]
            ],
        }

    @mcp.tool(description="List all knowledge bases with their file/chunk stats.")
    def list_bases() -> dict:
        return {"bases": _engine.list_bases()}

    @mcp.tool(description="Stats for one knowledge base (files, chunks, terms).")
    def base_info(base: str = "default") -> dict:
        kb = _engine.get(base, create=False)
        if kb is None:
            return {"error": f"Base '{base}' not found", "base": base}
        return kb.stats()

    @mcp.tool(description="Delete a knowledge base and its index data.")
    def delete_base(base: str = "default") -> dict:
        ok = _engine.delete_base(base)
        return {"deleted": ok, "base": base}

    return mcp


def main() -> None:
    mcp = build_server()
    log.info("AMT-RAG server starting (data dir: %s)", _DATA_DIR)
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
