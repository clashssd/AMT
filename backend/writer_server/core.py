# backend/writer_server/core.py
"""Safety backbone for the AMT Writer MCP server.

Provides:
  * root registry (workspace / output / temp / user roots) with canonicalized
    containment checks (NOT string-prefix) and explicit symlink policy
  * artifact manifest (JSONL) powering list_artifacts / artifact_info
  * typed error taxonomy (codes the LLM can retry on, not parse free-text)
  * idempotency (same idempotency_key -> same artifact_id, no duplicate)
  * preview -> commit token binding (spec-hash + target path; change => reject)
  * limits + zip-bomb guard, secret sanitization, .trash soft-delete

The server is a separate, higher-risk lane than read-only tools: mass writes,
overwrites, generation. Its auto-approval is configured separately.
"""
from __future__ import annotations
import os, json, time, uuid, hashlib, shutil, base64, logging
from typing import Optional, Tuple

log = logging.getLogger("writer_server.core")

# ---- Typed error codes (LLM can retry on these, not parse free-text) ----
class Err:
    PATH_OUTSIDE_ROOT   = "PATH_OUTSIDE_ROOT"
    PATH_TRAVERSAL      = "PATH_TRAVERSAL"
    INVALID_SPEC        = "INVALID_SPEC"
    TEMPLATE_MISSING    = "TEMPLATE_MISSING"
    FORMAT_UNSUPPORTED  = "FORMAT_UNSUPPORTED"
    LIMIT_EXCEEDED      = "LIMIT_EXCEEDED"
    CONFLICT_EXISTING   = "CONFLICT_EXISTING_FILE"
    VALIDATION_FAILED   = "VALIDATION_FAILED"
    DEPENDENCY_MISSING  = "DEPENDENCY_MISSING"
    CANCELLED           = "CANCELLED"
    TIMEOUT             = "TIMEOUT"
    NO_ROOT             = "NO_ROOT"

    _HINTS = {
        PATH_OUTSIDE_ROOT:  "Target path resolves outside the named root. Use root_id + a relative path that stays inside it.",
        PATH_TRAVERSAL:     "Path contains '..' that escapes the root. Strip traversal or pick a different relative path.",
        INVALID_SPEC:       "Spec does not match the family schema. Fix the structure and retry with the same idempotency_key.",
        TEMPLATE_MISSING:   "Template id not found in the template store. Call list_templates to see valid ids.",
        FORMAT_UNSUPPORTED: "Family/extension not supported by this tool. Pick a supported family or a different tool.",
        LIMIT_EXCEEDED:      "Input exceeds a size/depth/row limit. Split the input or raise the limit if appropriate.",
        CONFLICT_EXISTING:  "Target file already exists. Set overwrite=true (and re-preview) to replace it.",
        VALIDATION_FAILED:  "Post-write validation failed (structure/magic-bytes). The commit was not finalized.",
        DEPENDENCY_MISSING: "An optional library for this family is not installed. Install the extra or use another family.",
        CANCELLED:          "Job was cancelled before completion.",
        TIMEOUT:            "Job exceeded its time budget. Retry with a smaller input or raise the timeout.",
        NO_ROOT:            "Root id not registered. Call list_roots (or use 'temp') to see valid roots.",
    }
    @classmethod
    def payload(cls, code: str, msg: str = "", extra: dict = None) -> dict:
        out = {"ok": False, "code": code, "error": msg or cls._HINTS.get(code, ""), "hint": cls._HINTS.get(code, "")}
        if extra:
            out.update(extra)
        return out

    @staticmethod
    def ok(**fields) -> dict:
        out = {"ok": True}
        out.update(fields)
        return out


# ---- Data dir (manifest, trash, idempotency store, templates) ----
_DATA_DIR = os.environ.get("AMT_WRITER_DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".amt_writer"
)


def _data_dir() -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return _DATA_DIR


# ---- Root registry ----
class RootRegistry:
    """Holds named roots. Each root: {id, path, access}. access in {read,write}."""

    def __init__(self):
        self._roots: dict[str, dict] = {}
        base = os.path.dirname(_DATA_DIR)
        # temp lives under the data dir (isolated from write roots), output under APPDATA
        self._seed(os.path.join(_DATA_DIR, "temp"))
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        self._seed(os.path.join(appdata, "AMT Chat", "output"))

    def _seed(self, path: str, rid: str = "", access: str = "write"):
        rid = rid or self._next_id(path)
        if rid not in self._roots:
            os.makedirs(path, exist_ok=True)
            self._roots[rid] = {"id": rid, "path": os.path.realpath(path), "access": access, "builtin": True}
        return rid

    def _next_id(self, path: str) -> str:
        name = os.path.basename(os.path.normpath(path))
        base = ("temp" if "temp" in name else "output" if "output" in name else "root")
        used = {r["id"] for r in self._roots.values()}
        n = 1
        while f"{base}{n}" in used:
            n += 1
        return f"{base}{n}"

    def add(self, rid: str, path: str, access: str = "write") -> dict:
        rid = rid or self._next_id(path)
        rp = os.path.realpath(os.path.expandvars(os.path.expanduser(path)))
        os.makedirs(rp, exist_ok=True)
        self._roots[rid] = {"id": rid, "path": rp, "access": access, "builtin": False}
        return self._roots[rid]

    def get(self, rid: str) -> Optional[dict]:
        return self._roots.get(rid)

    def all(self) -> list[dict]:
        return list(self._roots.values())

    def temp_root(self) -> dict:
        for r in self._roots.values():
            if r["id"].startswith("temp"):
                return r
        return self._roots[self._seed(os.path.join(_DATA_DIR, "temp"))["id"]]

    def resolve(self, rid: str, rel_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (abs_path, error_code, message). Canonicalize + containment check.
        Symlinks are resolved via realpath, then re-checked against the root's realpath."""
        root = self._roots.get(rid)
        if root is None:
            return None, Err.NO_ROOT, f"Root '{rid}' is not registered"
        rp = root["path"]
        # Forbid absolute paths in the relative arg (caller must pass relative)
        target = os.path.join(rp, rel_path or "")
        real = os.path.realpath(target)
        # Containment: real target must be inside real root (os.path.commonpath-safe)
        if real != rp and not real.startswith(rp + os.sep):
            return None, Err.PATH_OUTSIDE_ROOT, f"'{rel_path}' resolves outside root '{rid}'"
        return real, None, ""


def build_roots() -> RootRegistry:
    return RootRegistry()


# ---- Manifest (JSONL) ----
class Manifest:
    """Artifact manifest. One JSON object per line. Powers list/info/diagnostics."""

    def __init__(self, data_dir: str = ""):
        self._path = os.path.join(data_dir or _data_dir(), "manifest.jsonl")
        self._dir = data_dir or _data_dir()
        os.makedirs(self._dir, exist_ok=True)
        self._by_idempotency: dict = {}
        self._load_idem()

    def _load_idem(self):
        self._by_idempotency = {}
        if os.path.exists(self._path):
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        k = rec.get("idempotency_key")
                        if k:
                            self._by_idempotency[k] = rec.get("artifact_id")
                    except Exception:
                        pass

    def record(self, rec: dict):
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        k = rec.get("idempotency_key")
        if k:
            self._by_idempotency[k] = rec.get("artifact_id")

    def idempotent(self, key: str) -> Optional[str]:
        return self._by_idempotency.get(key)

    def list(self, limit: int = 100) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        out = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
        return out[-limit:]

    def get(self, artifact_id: str) -> Optional[dict]:
        if not os.path.exists(self._path):
            return None
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("artifact_id") == artifact_id:
                    return rec
        return None


# ---- Preview token ----
class PreviewTokens:
    """preview -> commit binding. Token binds spec-hash + target + family."""

    def __init__(self, data_dir: str = ""):
        self._path = os.path.join(data_dir or _data_dir(), "preview_tokens.json")
        self._dir = data_dir or _data_dir()
        os.makedirs(self._dir, exist_ok=True)
        self._tok: dict = {}
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._tok = json.load(f)
            except Exception:
                self._tok = {}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._tok, f, ensure_ascii=False)

    @staticmethod
    def _hash_spec(spec) -> str:
        try:
            raw = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        except Exception:
            raw = str(spec)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def mint(self, family: str, root_id: str, rel_path: str, spec, overwrite: bool) -> str:
        token = uuid.uuid4().hex
        self._tok[token] = {
            "family": family, "root_id": root_id, "rel_path": rel_path,
            "spec_hash": self._hash_spec(spec), "overwrite": bool(overwrite),
            "ts": time.time(),
        }
        self._save()
        return token

    def consume(self, token: str, family: str, root_id: str, rel_path: str, spec, overwrite: bool) -> Optional[str]:
        """Return None if valid, else an Err code. Removes token on success."""
        rec = self._tok.get(token)
        if rec is None:
            return Err.PATH_OUTSIDE_ROOT  # unknown/rotated token
        if rec.get("family") != family or rec.get("root_id") != root_id or rec.get("rel_path") != rel_path:
            self._tok.pop(token, None); self._save()
            return Err.CONFLICT_EXISTING
        if rec.get("spec_hash") != self._hash_spec(spec) or bool(rec.get("overwrite")) != bool(overwrite):
            self._tok.pop(token, None); self._save()
            return Err.CONFLICT_EXISTING
        self._tok.pop(token, None)
        self._save()
        return None


# ---- Limits + sanitization + trash ----
MAX_FILE_BYTES = int(os.environ.get("AMT_WRITER_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
MAX_ZIP_RATIO  = float(os.environ.get("AMT_WRITER_MAX_ZIP_RATIO", "100"))
MAX_ZIP_UNCOMP = int(os.environ.get("AMT_WRITER_MAX_ZIP_UNCOMP", str(500 * 1024 * 1024)))

_SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "[REDACTED-AWS-KEY]"),
    (r"ghp_[A-Za-z0-9]{20,}", "[REDACTED-GITHUB-TOKEN]"),
    (r"-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----", "[REDACTED-PRIVATE-KEY]"),
    (r"(?i)\b(api[_-]?key|token|secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]", "[REDACTED-SECRET]"),
]

def sanitize(text: str) -> str:
    """Strip control/invisible unicode and redact obvious secrets.
    Tool responses are DATA, not instructions to the model."""
    if not text:
        return text
    import re
    # Remove C0/C1 control chars except \n \t \r
    cleaned = "".join(ch for ch in text if ch in "\n\t\r" or (ord(ch) >= 32 and ch not in "\u200b\u200c\u200d\ufeff\u2028\u2029"))
    for pat, rep in _SECRET_PATTERNS:
        cleaned = re.sub(pat, rep, cleaned)
    return cleaned


def zip_bomb_check(uncompressed: int, compressed: int) -> Optional[dict]:
    if compressed > 0 and uncompressed / compressed > MAX_ZIP_RATIO:
        return Err.payload(Err.LIMIT_EXCEEDED, f"Zip bomb suspected (ratio {uncompressed/compressed:.1f})")
    if uncompressed > MAX_ZIP_UNCOMP:
        return Err.payload(Err.LIMIT_EXCEEDED, f"Archive exceeds max uncompressed size ({MAX_ZIP_UNCOMP} bytes)")
    return None


class Trash:
    """Soft-delete: overwrites/deletes go to .trash/<artifact_id>/ instead of vanishing."""

    def __init__(self, data_dir: str = ""):
        self._path = os.path.join(data_dir or _data_dir(), ".trash")
        os.makedirs(self._path, exist_ok=True)

    def move(self, src_abs: str, artifact_id: str, reason: str) -> bool:
        dest = os.path.join(self._path, artifact_id)
        os.makedirs(dest, exist_ok=True)
        try:
            shutil.move(src_abs, os.path.join(dest, os.path.basename(src_abs)))
            with open(os.path.join(dest, "_meta.json"), "w", encoding="utf-8") as f:
                json.dump({"artifact_id": artifact_id, "reason": reason, "ts": time.time()}, f)
            return True
        except Exception as e:
            log.warning("trash move failed: %s", e)
            return False

    def restore(self, artifact_id: str, target_abs: str) -> bool:
        src = os.path.join(self._path, artifact_id, os.path.basename(target_abs))
        if not os.path.exists(src):
            return False
        try:
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            shutil.move(src, target_abs)
            return True
        except Exception:
            return False

    def list(self) -> list[str]:
        return [d for d in (os.listdir(self._path) if os.path.isdir(self._path) else [])
                if os.path.isdir(os.path.join(self._path, d))]


# ---- Convenience builder for tool responses ----
def artifact_id() -> str:
    return "art_" + uuid.uuid4().hex[:16]


def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
