# backend/writer_server/server.py
"""STDIO MCP server exposing AMT's file-generation ("writer") tools.

Tools (auto-registered as mcp__writer__<tool>):
  create_text / create_data / create_code / create_office / create_pdf /
  create_archive / create_media / convert /
  read_artifact / list_artifacts / artifact_info /
  preview_generation / commit / diff_artifact / validate_artifact /
  delete_artifact / restore_artifact / cancel_job /
  render_template / list_templates / template_info

Contract: preview -> approve -> commit -> validate. Typed errors, sandboxed
roots, idempotency, artifact manifest. Reads are auto; commits write to the
temp root by default (auto-commit + download). Media delegation reuses the
same media_creds.json the media server uses.

Transport: STDIO. Launched by AMT via the writer preset.
"""
from __future__ import annotations
import os, json, asyncio, logging, time

logging.basicConfig(level=logging.INFO, stream=os.sys.stderr)
log = logging.getLogger("writer_server")

from .core import (Err, build_roots, Manifest, PreviewTokens, Trash,
                  artifact_id, hash_bytes, sanitize, zip_bomb_check,
                  MAX_FILE_BYTES, _data_dir)
from . import families

_ROOTS  = build_roots()
_MAN    = Manifest()
_TOKENS = PreviewTokens()
_TRASH  = Trash()

_CREDS_FILE = os.environ.get("AMT_MEDIA_CREDS_FILE") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media_creds.json")
_FILES_DIR = os.environ.get("AMT_FILES_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")


def _j(out: dict) -> str:
    return json.dumps(out, ensure_ascii=False, indent=2)


def _write_artifact(root_id: str, rel_path: str, data: bytes, family: str,
                    source: str, idem_key: str = "", overwrite: bool = False) -> dict:
    """Write bytes into a root, record manifest, return typed result."""
    abs_path, err, msg = _ROOTS.resolve(root_id, rel_path)
    if err:
        return Err.payload(err, msg)
    if os.path.exists(abs_path) and not overwrite:
        return Err.payload(Err.CONFLICT_EXISTING,
                           f"'{rel_path}' already exists in root '{root_id}'",
                           target=rel_path, root_id=root_id)
    if len(data) > MAX_FILE_BYTES:
        return Err.payload(Err.LIMIT_EXCEEDED, f"{len(data)} bytes > limit {MAX_FILE_BYTES}")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    val = families.validate(family, data)
    aid = artifact_id()
    rec = {
        "artifact_id": aid, "path": rel_path, "root_id": root_id,
        "family": family, "size": len(data), "hash": hash_bytes(data),
        "source": source, "status": "committed" if val["valid"] else "invalid",
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "validation": val, "idempotency_key": idem_key,
    }
    if not val["valid"] and val.get("code"):
        # commit did NOT finalize — surface as a typed failure
        return Err.payload(val["code"], "post-write validation failed",
                           artifact_id=aid, notes=val.get("notes"), target=rel_path)
    _MAN.record(rec)
    return Err.ok(
        artifact_id=aid, action="create" if not overwrite else "update",
        path=rel_path, root_id=root_id, family=family,
        bytes=len(data), hash=rec["hash"],
        validation=val, stored_name=os.path.basename(abs_path),
    )


def _media_creds() -> dict:
    try:
        if os.path.exists(_CREDS_FILE):
            with open(_CREDS_FILE) as f:
                return json.load(f)
    except Exception as e:
        log.warning("writer: failed to load media creds: %s", e)
    return {}


def build_server():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer(
        "AMT-Writer",
        description="AMT file writer — create, read, edit, validate files across families "
                    "(text, data, Office, code, archives, media) with a typed contract.",
        instructions=(
            "Generate files. Flow: create_* (or preview_generation -> commit) -> "
            "validate_artifact. Reads/preview/validate are auto-approved; commits "
            "write to the temp root by default and return a stored_name you can hand "
            "to the user as a download. If a tool returns code=DEPENDENCY_MISSING, "
            "an optional library is absent. Never pass absolute paths — use "
            "root_id + relative path."
        ),
    )

    # ---------- reads / metadata ----------
    @mcp.tool(description="List registered roots (workspace/output/temp/user) with their access policy.")
    def list_roots() -> str:
        return _j({"ok": True, "roots": _ROOTS.all()})

    @mcp.tool(description="List generated artifacts (newest first) from the manifest.")
    def list_artifacts(limit: int = 50) -> str:
        return _j({"ok": True, "artifacts": _MAN.list(limit)})

    @mcp.tool(description="Return one artifact's manifest record (metadata + validation).")
    def artifact_info(artifact_id_: str) -> str:
        rec = _MAN.get(artifact_id_)
        if rec is None:
            return _j(Err.payload(Err.INVALID_SPEC, f"artifact '{artifact_id_}' not found"))
        return _j({"ok": True, "artifact": rec})

    @mcp.tool(description="Read a committed artifact's bytes (base64) + family + size. Auto-approved read.")
    def read_artifact(root_id: str, path: str, artifact_id_: str = "") -> str:
        abs_path, err, msg = _ROOTS.resolve(root_id, path)
        if err:
            return _j(Err.payload(err, msg))
        if not os.path.exists(abs_path):
            return _j(Err.payload(Err.INVALID_SPEC, f"'{path}' not found in root '{root_id}'"))
        with open(abs_path, "rb") as f:
            raw = f.read()
        import base64 as _b64
        return _j({"ok": True, "root_id": root_id, "path": path, "bytes": len(raw),
                   "b64": _b64.b64encode(raw).decode("ascii")})

    @mcp.tool(description="Validate a family spec without writing (dry-run structure check).")
    def validate_artifact(family: str, spec="", data_b64: str = "") -> str:
        import base64 as _b64
        data = _b64.b64decode(data_b64) if data_b64 else None
        if data is None:
            # build-then-validate path
            if family in ("json", "yaml", "csv", "data"):
                data, _, err = families.build_data(spec)
                if err:
                    return _j(err)
            elif family == "code":
                data, _, err = families.build_code(spec)
                if err:
                    return _j(err)
            else:
                return _j(Err.payload(Err.INVALID_SPEC, "spec or data_b64 required"))
        val = families.validate(family, data)
        return _j({"ok": val["valid"], "validation": val,
                   **({} if val["valid"] else {"code": val.get("code")})})

    @mcp.tool(description="Structural diff between two artifacts (line-level for text, count-level for binary).")
    def diff_artifact(a_root_id: str, a_path: str, b_root_id: str, b_path: str) -> str:
        import difflib
        def _read(rid, p):
            abs_p, err, _ = _ROOTS.resolve(rid, p)
            if err or not os.path.exists(abs_p):
                return ""
            try:
                with open(abs_p, "rb") as f:
                    return f.read().decode("utf-8", "ignore")
            except Exception:
                return ""
        ta, tb = _read(a_root_id, a_path), _read(b_root_id, b_path)
        diff = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(), "a", "b", lineterm=""))
        return _j({"ok": True, "changed": bool(diff),
                   "added": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
                   "removed": sum(1 for l in diff if l.startswith("-") and not l.startswith("---")),
                   "diff": sanitize("\n".join(diff[:400]))})

    # ---------- templates ----------
    def _tpl_dir() -> str:
        d = os.path.join(_data_dir(), "templates")
        os.makedirs(d, exist_ok=True)
        return d

    @mcp.tool(description="List available templates (id + version + family).")
    def list_templates() -> str:
        out = []
        for fn in sorted(os.listdir(_tpl_dir())):
            try:
                with open(os.path.join(_tpl_dir(), fn), encoding="utf-8") as f:
                    t = json.load(f)
                out.append({"id": t.get("id", fn), "version": t.get("version", 1),
                            "family": t.get("family"), "description": t.get("description", "")})
            except Exception:
                continue
        return _j({"ok": True, "templates": out})

    @mcp.tool(description="Return one template's full definition (vars, conditions, loops).")
    def template_info(template_id: str) -> str:
        p = os.path.join(_tpl_dir(), f"{template_id}.json")
        if not os.path.exists(p):
            return _j(Err.payload(Err.TEMPLATE_MISSING, f"template '{template_id}' not found"))
        with open(p, encoding="utf-8") as f:
            return _j({"ok": True, "template": json.load(f)})

    @mcp.tool(description="Render a template with vars -> bytes. No commit (call create_* with the result, or commit).")
    def render_template(template_id: str, variables: dict) -> str:
        p = os.path.join(_tpl_dir(), f"{template_id}.json")
        if not os.path.exists(p):
            return _j(Err.payload(Err.TEMPLATE_MISSING, f"template '{template_id}' not found"))
        with open(p, encoding="utf-8") as f:
            tpl = json.load(f)
        body = tpl.get("body", "")
        for k, v in (variables or {}).items():
            body = body.replace("{{" + k + "}}", str(v))
        family = tpl.get("family", "txt")
        data, meta, err = families.build_text(body, tpl.get("title", template_id))
        if err:
            return _j(err)
        return _j({"ok": True, "b64": _b64(data), "family": family, "template": template_id,
                   "unresolved": [k for k in _unresolved(body, variables)]})

    # ---------- create (auto-commit to temp root unless root_id given) ----------
    @mcp.tool(description="Create a text/markdown/txt file. Auto-commits to the temp root by default; "
                          "returns artifact_id + stored_name for download. Idempotent by idempotency_key.")
    def create_text(content: str, title: str = "", root_id: str = "", rel_path: str = "",
                    source_b64: str = "", idempotency_key: str = "") -> str:
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        rel = rel_path or f"{title or 'file'}.txt"
        # If a user file was uploaded, read its text and combine with the instruction.
        if source_b64:
            merged = families.merge_source(content, source_b64, "text")
            content = merged if isinstance(merged, str) else content
        data, meta, err = families.build_text(content, title)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, "txt", "create_text", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create a data file (json/yaml/csv). spec is the value (or JSON string / CSV string). "
                          "Pass source_b64 to base it on a user-uploaded data file.")
    def create_data(spec="", title: str = "", fmt: str = "json", root_id: str = "",
                    rel_path: str = "", source_b64: str = "", idempotency_key: str = "") -> str:
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        rel = rel_path or f"{title or 'data'}.{fmt}"
        spec = families.merge_source(spec, source_b64, fmt)
        data, meta, err = families.build_data(spec, title)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, fmt, "create_data", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create a code file from a schema/scaffold or raw code. Python is AST-validated. "
                          "No execution of generated code.")
    def create_code(spec="", lang: str = "py", title: str = "", root_id: str = "",
                    rel_path: str = "", idempotency_key: str = "") -> str:
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        rel = rel_path or f"{title or 'code'}.{'py' if lang in ('py','python') else lang}"
        data, meta, err = families.build_code(spec, lang)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, "code", "create_code", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create an Office file (docx/xlsx/pptx) from Markdown or a structural spec. "
                          "Pass source_b64 (base64 of a user-uploaded file) to base the result on the "
                          "actual file contents (preserves real rows/paragraphs) and combine with the spec. "
                          "Reuses ai_engine.filegen.")
    def create_office(family: str, spec="", title: str = "", root_id: str = "",
                      rel_path: str = "", source_b64: str = "", idempotency_key: str = "") -> str:
        if family not in ("docx", "xlsx", "pptx"):
            return _j(Err.payload(Err.FORMAT_UNSUPPORTED, "family must be docx/xlsx/pptx"))
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        rel = rel_path or f"{title or 'doc'}.{family}"
        spec = families.merge_source(spec, source_b64, family)
        data, meta, err = families.build_office(family, spec, title)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, family, "create_office", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create a PDF from Markdown/HTML or a structural spec. "
                          "Pass source_b64 to base it on a user-uploaded file's text.")
    def create_pdf(spec="", title: str = "", root_id: str = "", rel_path: str = "",
                   source_b64: str = "", idempotency_key: str = "") -> str:
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        rel = rel_path or f"{title or 'doc'}.pdf"
        spec = families.merge_source(spec, source_b64, "pdf")
        data, meta, err = families.build_office("pdf", spec, title)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, "pdf", "create_pdf", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create an archive (zip/tar) from named entries. Zip-bomb guard + '..' ban.")
    def create_archive(spec: dict, title: str = "", root_id: str = "", rel_path: str = "",
                       idempotency_key: str = "") -> str:
        existing = _MAN.idempotent(idempotency_key) if idempotency_key else None
        if existing:
            return _j(Err.ok(artifact_id=existing, action="no-op", note="idempotent hit"))
        rid = root_id or _ROOTS.temp_root()["id"]
        fmt = (spec.get("format", "zip")).lower()
        rel = rel_path or f"{title or 'archive'}.{fmt}"
        data, meta, err = families.build_archive(spec)
        if err:
            return _j(err)
        out = _write_artifact(rid, rel, data, fmt, "create_archive", idempotency_key)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    @mcp.tool(description="Create a media file by delegating to the media provider (image/video/audio). "
                          "Uses the same media_creds.json as the media server. The writer owns "
                          "save + metadata + validation + preview of the result.")
    def create_media(kind: str, prompt: str = "", spec: dict = "") -> str:
        """kind in {image, video, audio}. Delegates to ai_engine.media when available."""
        c = _media_creds()
        if not c.get(f"{kind}_api_key") and not c.get("api_key"):
            return _j(Err.payload(Err.DEPENDENCY_MISSING,
                                  f"No {kind} API key in media creds. Set it in AMT's media settings."))
        try:
            from ai_engine import media as mgen
        except ImportError:
            return _j(Err.payload(Err.DEPENDENCY_MISSING, "ai_engine.media unavailable"))
        kw = dict(spec or {})
        if kind == "image":
            res = mgen.generate_image_ref(
                base_url=kw.get("base_url") or c.get("image_base_url") or c.get("base_url"),
                api_key=kw.get("api_key") or c.get("image_api_key") or c.get("api_key"),
                model=kw.get("model") or c.get("image_model") or c.get("model"),
                prompt=prompt, size=kw.get("size", "1024x1024"),
                ref_image_b64=kw.get("ref_image_b64", ""),
                proxy=c.get("proxy", ""))
        elif kind == "video":
            res = mgen.generate_video(
                base_url=kw.get("base_url") or c.get("video_base_url") or c.get("base_url"),
                api_key=kw.get("api_key") or c.get("video_api_key") or c.get("api_key"),
                model=kw.get("model") or c.get("video_model") or c.get("model"),
                prompt=prompt, duration=str(kw.get("duration", "5")),
                aspect_ratio=kw.get("aspect_ratio", "16:9"),
                proxy=c.get("proxy", ""))
        else:
            res = mgen.generate_audio(
                base_url=kw.get("base_url") or c.get("audio_base_url") or c.get("base_url"),
                api_key=kw.get("api_key") or c.get("audio_api_key") or c.get("api_key"),
                model=kw.get("model") or c.get("audio_model") or c.get("model"),
                text=prompt, voice_id=kw.get("voice_id") or c.get("audio_voice_id", ""),
                proxy=c.get("proxy", ""))
        if not res.get("ok"):
            return _j({**res, "code": res.get("code", Err.VALIDATION_FAILED)})
        import base64 as _b64
        b64 = res.get("b64", "")
        if not b64:
            return _j({"ok": True, "note": "async media (video) — task_id below",
                       "task_id": res.get("task_id", ""), "kind": kind})
        rid = _ROOTS.temp_root()["id"]
        ext = {"image": "png", "video": "mp4", "audio": "mp3"}.get(kind, "bin")
        rel = f"media_{int(time.time())}_{kind}.{ext}"
        data = _b64.b64decode(b64)
        out = _write_artifact(rid, rel, data, kind, f"create_media:{kind}")
        if out.get("ok"):
            out["mime"] = res.get("mime", "")
            out["kind"] = kind
        return _j(out)

    # ---------- preview / commit (strict flow) ----------
    @mcp.tool(description="Preview a generation: list the files to create/overwrite, sizes, structural "
                          "diff, warnings, and mint an approval token. Auto-approved.")
    def preview_generation(family: str, root_id: str, rel_path: str, spec="",
                           overwrite: bool = False, idempotency_key: str = "") -> str:
        rid = root_id or _ROOTS.temp_root()["id"]
        abs_path, err, msg = _ROOTS.resolve(rid, rel_path)
        if err:
            return _j(Err.payload(err, msg))
        # size estimate
        if family in ("json", "yaml", "csv", "data"):
            data, _, err2 = families.build_data(spec)
            if err2:
                return _j(err2)
        elif family == "code":
            data, _, err2 = families.build_code(spec)
            if err2:
                return _j(err2)
        elif family in ("docx", "xlsx", "pptx", "pdf"):
            data, _, err2 = families.build_office(family, spec)
            if err2:
                return _j(err2)
        else:
            data, _, err2 = families.build_text(spec if isinstance(spec, str) else json.dumps(spec))
            if err2:
                return _j(err2)
        exists = os.path.exists(abs_path)
        warns = []
        if exists and not overwrite:
            warns.append(f"'{rel_path}' exists — set overwrite=true to replace (double-confirm).")
        token = _TOKENS.mint(family, rid, rel_path, spec, overwrite)
        return _j({"ok": True, "token": token, "action": "update" if exists else "create",
                   "path": rel_path, "root_id": rid, "bytes": len(data),
                   "warnings": warns, "overwrite": overwrite})

    @mcp.tool(description="Commit a previewed generation using its token. Rejects if the spec or target "
                          "changed since the preview. Writes + validates + records in the manifest.")
    def commit(family: str, token: str, root_id: str = "", rel_path: str = "", spec="",
               overwrite: bool = False, idempotency_key: str = "") -> str:
        rid = root_id or _ROOTS.temp_root()["id"]
        bad = _TOKENS.consume(token, family, rid, rel_path, spec, overwrite)
        if bad:
            return _j(Err.payload(bad, "preview token invalid or spec/target changed since preview"))
        # build + write
        if family in ("json", "yaml", "csv", "data"):
            data, meta, err = families.build_data(spec)
        elif family == "code":
            data, meta, err = families.build_code(spec)
        elif family in ("docx", "xlsx", "pptx", "pdf"):
            data, meta, err = families.build_office(family, spec)
        else:
            data, meta, err = families.build_text(spec if isinstance(spec, str) else json.dumps(spec))
        if err:
            return _j(err)
        out = _write_artifact(rid, rel_path, data, family, "commit", idempotency_key, overwrite=True)
        if out.get("ok"):
            out["meta"] = meta
        return _j(out)

    # ---------- delete / restore (soft) ----------
    @mcp.tool(description="Soft-delete an artifact (moves to .trash/, restorable). Overwrite/delete is "
                          "the highest-risk tier — requires an explicit artifact_id.")
    def delete_artifact(artifact_id_: str) -> str:
        rec = _MAN.get(artifact_id_)
        if rec is None:
            return _j(Err.payload(Err.INVALID_SPEC, f"artifact '{artifact_id_}' not found"))
        rid = rec.get("root_id", "")
        abs_path, err, msg = _ROOTS.resolve(rid, rec.get("path", ""))
        if err or not os.path.exists(abs_path):
            return _j(Err.payload(Err.INVALID_SPEC, "artifact file missing (already moved?)"))
        moved = _TRASH.move(abs_path, artifact_id_, "delete")
        rec["status"] = "deleted"
        _MAN.record({**rec, "status": "deleted", "deleted_date": time.strftime("%Y-%m-%dT%H:%M:%S")})
        return _j({"ok": True, "artifact_id": artifact_id_, "moved_to_trash": moved,
                   "restorable": moved})

    @mcp.tool(description="Restore a soft-deleted artifact from .trash/ to its original path.")
    def restore_artifact(artifact_id_: str) -> str:
        rec = _MAN.get(artifact_id_)
        if rec is None:
            return _j(Err.payload(Err.INVALID_SPEC, f"artifact '{artifact_id_}' not found"))
        rid = rec.get("root_id", "")
        abs_path, err, msg = _ROOTS.resolve(rid, rec.get("path", ""))
        if err:
            return _j(Err.payload(err, msg))
        if _TRASH.restore(artifact_id_, abs_path):
            rec["status"] = "restored"
            _MAN.record(rec)
            return _j({"ok": True, "artifact_id": artifact_id_, "restored": True, "path": rec["path"]})
        return _j(Err.payload(Err.INVALID_SPEC, f"artifact '{artifact_id_}' not in trash"))

    @mcp.tool(description="Cancel a long-running generation job (best-effort).")
    def cancel_job(job_id: str) -> str:
        return _j({"ok": True, "job_id": job_id, "note": "cancellation requested"})

    @mcp.tool(description="Convert an existing artifact to another family (e.g. docx->pdf, md->html).")
    def convert(artifact_id_: str, to_family: str) -> str:
        rec = _MAN.get(artifact_id_)
        if rec is None:
            return _j(Err.payload(Err.INVALID_SPEC, f"artifact '{artifact_id_}' not found"))
        rid = rec.get("root_id", "")
        abs_path, err, msg = _ROOTS.resolve(rid, rec.get("path", ""))
        if err or not os.path.exists(abs_path):
            return _j(Err.payload(Err.INVALID_SPEC, "source artifact missing"))
        with open(abs_path, "rb") as f:
            src = f.read()
        # Simple conversions via families (text->html, json->csv are limited; Office via filegen)
        if to_family in ("docx", "xlsx", "pptx", "pdf"):
            text = src.decode("utf-8", "ignore")
            data, meta, err2 = families.build_office(to_family, text, rec.get("path", "doc"))
            if err2:
                return _j(err2)
        else:
            data, meta, err2 = families.build_text(src.decode("utf-8", "ignore"))
            if err2:
                return _j(err2)
        rel = os.path.splitext(rec.get("path", "out"))[0] + "." + to_family
        out = _write_artifact(rid, rel, data, to_family, f"convert:{artifact_id_}")
        return _j(out)

    return mcp


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode("ascii")


def _unresolved(body: str, variables: dict) -> list:
    import re
    toks = set(re.findall(r"{{\s*([a-zA-Z_][\w]*)\s*}}", body))
    return sorted(t for t in toks if t not in (variables or {}))


def main() -> None:
    mcp = build_server()
    log.info("AMT-Writer server starting (data dir %s)", _data_dir())
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
