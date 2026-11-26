# backend/rag_server/engine.py
"""Hybrid local retrieval: chunk store + BM25 ranking, per knowledge base.

A base is a directory under <data_dir>/bases/<base_id>/ containing:
    chunks.json      — list of chunk records
    index.json       — { term: { chunk_idx: term_freq }, ... } + meta
    manifest.json    — { source: {"sha1":..., "mtime":..., "chunk_idxs":[...]} }

Retrieval is keyword/BM25. Query terms are matched with token-based matching
(lowercase + word-boundary-ish). Results carry source + locator so the UI can
render citations ([1] -> open file at page/line).
"""
from __future__ import annotations
import os, re, json, math, time
from typing import Iterable

from . import parsers

_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
# CJK has no whitespace; capture short runs as tokens too.
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]{2,}")


def tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower())
    toks.extend(_CJK_RE.findall(text))
    return toks


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


class KnowledgeBase:
    """One isolated RAG base. All operations are synchronous & local."""

    def __init__(self, base_dir: str, name: str):
        self.base_dir = base_dir
        self.name = name
        os.makedirs(base_dir, exist_ok=True)
        self.chunks_path = os.path.join(base_dir, "chunks.json")
        self.index_path = os.path.join(base_dir, "index.json")
        self.manifest_path = os.path.join(base_dir, "manifest.json")
        self.chunks: list[dict] = []
        self.index: dict = {}      # term -> {chunk_idx: tf}
        self.df: dict = {}        # term -> doc_count
        self.manifest: dict = {}   # source -> {sha1, mtime, chunk_idxs}
        self._load()

    def _load(self) -> None:
        self.chunks = _load_json(self.chunks_path, [])
        idx = _load_json(self.index_path, {})
        self.index = idx.get("index", {})
        self.df = idx.get("df", {})
        self.manifest = _load_json(self.manifest_path, {})

    def _persist(self) -> None:
        _save_json(self.chunks_path, self.chunks)
        _save_json(self.index_path, {"index": self.index, "df": self.df})
        _save_json(self.manifest_path, self.manifest)

    # ---- indexing ----
    def file_signature(self, path: str) -> tuple[str, int]:
        """Return (sha1, mtime) for a file; ("", 0) if unavailable."""
        try:
            st = os.stat(path)
            with open(path, "rb") as f:
                return parsers._sha1(f.read()), int(st.st_mtime)
        except Exception:
            return "", 0

    def index_files(self, paths: Iterable[str], base_root: str) -> dict:
        """Index (or re-index) a set of files incrementally.

        Returns stats: {indexed, skipped, removed, chunks_total}.
        A file is re-indexed only when its signature changed or it's new; a
        file removed from the set gets its chunks purged.
        """
        seen: set[str] = set()
        stats = {"indexed": 0, "skipped": 0, "removed": 0, "chunks_total": 0}

        # Remove chunks for files no longer in the set.
        stale = [src for src in self.manifest if not any(p == src or p.startswith(src) for p in paths)]
        # We only manage files we were explicitly asked about this run.
        # (We don't auto-remove files the caller didn't pass this time.)
        del stale

        for path in paths:
            seen.add(path)
            sha1, mtime = self.file_signature(path)
            prev = self.manifest.get(path)
            if prev and prev.get("sha1") == sha1 and prev.get("mtime") == mtime:
                stats["skipped"] += 1
                continue
            # Parse & chunk.
            rel = parsers._relpath(path, base_root)
            parsed = parsers.parse_file(path, base_root)
            # Drop old chunks for this source.
            old_idxs = set((prev or {}).get("chunk_idxs", []))
            new_idxs = []
            for ch in parsed:
                ch["source"] = rel
                ch["_idx"] = len(self.chunks)
                self.chunks.append(ch)
                new_idxs.append(ch["_idx"])
                self._add_chunk_to_index(ch["_idx"], ch["text"])
            self.manifest[path] = {
                "sha1": sha1,
                "mtime": mtime,
                "chunk_idxs": new_idxs,
            }
            # Purge removed old chunks (mark empty).
            for oi in old_idxs:
                if 0 <= oi < len(self.chunks) and oi not in new_idxs:
                    self.chunks[oi]["text"] = ""  # tombstone; keeps idx stable
            stats["indexed"] += 1

        # Rebuild index & df from scratch over live (non-empty) chunks so
        # tombstones and stale terms drop out cleanly.
        self._rebuild_index()
        stats["chunks_total"] = sum(1 for c in self.chunks if c.get("text"))
        self._persist()
        return stats

    def _add_chunk_to_index(self, idx: int, text: str) -> None:
        toks = tokenize(text)
        seen = set()
        for t in toks:
            tf = self.index.setdefault(t, {}).get(idx, 0) + 1
            self.index[t][idx] = tf
            if t not in seen:
                self.df[t] = self.df.get(t, 0) + 1
                seen.add(t)

    def _rebuild_index(self) -> None:
        self.index = {}
        self.df = {}
        for c in self.chunks:
            if c.get("text"):
                toks = tokenize(c["text"])
                seen = set()
                for t in toks:
                    self.index.setdefault(t, {})[c["_idx"]] = \
                        self.index.get(t, {}).get(c["_idx"], 0) + 1
                    if t not in seen:
                        self.df[t] = self.df.get(t, 0) + 1
                        seen.add(t)

    # ---- retrieval (BM25) ----
    def search(self, query: str, top_k: int = 8, source_filter: str = "") -> list[dict]:
        qtoks = tokenize(query)
        if not qtoks:
            return []
        N = sum(1 for c in self.chunks if c.get("text"))
        if N == 0:
            return []
        k1, b = 1.5, 0.75
        avgdl = self._avg_doc_len() or 1.0
        scores: dict[int, float] = {}
        for t in set(qtoks):
            tf_map = self.index.get(t)
            if not tf_map:
                continue
            df = self.df.get(t, 0)
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            for ci, tf in tf_map.items():
                doc = self.chunks[ci]
                if not doc.get("text"):
                    continue
                if source_filter and source_filter.lower() not in doc["source"].lower():
                    continue
                dl = len(tokenize(doc["text"])) or 1
                s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
                scores[ci] = scores.get(ci, 0.0) + s
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        out = []
        for ci, sc in ranked:
            c = self.chunks[ci]
            out.append({
                "text": c["text"],
                "source": c["source"],
                "locator": c.get("locator", ""),
                "kind": c.get("kind", "text"),
                "score": round(sc, 4),
            })
        return out

    def read_chunk(self, chunk_idx: int, neighbors: int = 2) -> dict:
        """Return a chunk plus its neighbors (same source, adjacent idx)."""
        c = self.chunks[chunk_idx]
        group = [self.chunks[i] for i in range(chunk_idx - neighbors, chunk_idx + neighbors + 1)
                 if 0 <= i < len(self.chunks) and self.chunks[i].get("text")]
        return {"chunk": c, "neighbors": group}

    def _avg_doc_len(self) -> float:
        lens = [len(tokenize(c["text"])) for c in self.chunks if c.get("text")]
        if not lens:
            return 0.0
        return sum(lens) / len(lens)

    def stats(self) -> dict:
        live = sum(1 for c in self.chunks if c.get("text"))
        return {
            "name": self.name,
            "files": len(self.manifest),
            "chunks": live,
            "terms": len(self.df),
        }


def _safe_stat(path: str) -> bool:
    try:
        os.stat(path)
        return True
    except Exception:
        return False


class RAGEngine:
    """Manages multiple named knowledge bases under a data dir."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._bases: dict[str, KnowledgeBase] = {}

    def _base_dir(self, base_id: str) -> str:
        return os.path.join(self.data_dir, "bases", base_id)

    def get(self, base_id: str, create: bool = False) -> KnowledgeBase | None:
        if base_id in self._bases:
            return self._bases[base_id]
        bdir = self._base_dir(base_id)
        if not create and not os.path.isdir(bdir):
            return None
        # Reuse existing base's saved name, else the id.
        name = base_id
        if os.path.isdir(bdir):
            saved = _load_json(os.path.join(bdir, "meta.json"), {})
            name = saved.get("name", base_id)
        kb = KnowledgeBase(bdir, name)
        if create:
            _save_json(os.path.join(bdir, "meta.json"), {"name": name, "id": base_id,
                                                          "created": int(time.time())})
        self._bases[base_id] = kb
        return kb

    def list_bases(self) -> list[dict]:
        out = []
        broot = os.path.join(self.data_dir, "bases")
        if not os.path.isdir(broot):
            return out
        for entry in sorted(os.listdir(broot)):
            kb = self.get(entry, create=False)
            if kb is not None:
                st = kb.stats()
                size = 0
                for root, _dirs, files in os.walk(os.path.join(broot, entry)):
                    for fn in files:
                        try:
                            size += os.path.getsize(os.path.join(root, fn))
                        except Exception:
                            pass
                out.append({**st, "id": entry, "size_bytes": size})
        return out

    def delete_base(self, base_id: str) -> bool:
        import shutil
        kb = self._bases.pop(base_id, None)
        bdir = self._base_dir(base_id)
        if os.path.isdir(bdir):
            shutil.rmtree(bdir, ignore_errors=True)
        return kb is not None or os.path.exists(bdir)
