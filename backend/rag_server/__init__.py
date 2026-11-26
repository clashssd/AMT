# backend/rag_server/__init__.py
"""Local RAG MCP server for AMT.

A standalone STDIO MCP server that indexes folders of local files (docs, code,
tables, media) and answers retrieval queries with a hybrid keyword index
(BM25-style ranking) — no external APIs, fully local. Launched by AMT as an
MCP server; AMT auto-registers its tools (index_folder, search_documents,
read_chunk, list_bases, base_info, delete_base) into the Tool Registry.

Design (per user decisions):
  * Pure-Python keyword/BM25 engine now; no heavy embedding deps (no torch /
    lancedb / sentence-transformers) so it runs inside the packaged app today.
  * Incremental indexing (sha256 + mtime); multiple isolated knowledge bases.
"""
__version__ = "1.0.0"
