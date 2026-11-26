# Plan — Writer MCP server + advanced media MCP

## Goal
1. **Remove** the simple `generate_file` tool from `media_server` (it becomes the dedicated Writer server's job).
2. **Build** a new `writer_server` MCP — a file-generator that creates/reads/edits/validates files across families (text, data, Office, code, archives, media) with a typed contract: `preview → commit → validate`, sandboxed roots, typed errors, idempotency, artifact manifest.
3. **Add advanced audio/video/image features** to the media MCP server — voice settings, voice clone/list, video2video example, image analysis + image-to-image via prompt, advanced quality settings. Delegate to `ai_engine.media`.
4. **Wire** a user-facing API + front form: user asks to generate a file → task routes to the Writer MCP → user gets back a finished file (download card in chat / form). All keys come from settings.

## Decisions (from user)
- **Scope:** full catalog now (text, data, Office, code, archives, media-delegation, templates, convert).
- **Approval:** auto-commit to temp root + download. Overwrite of existing file → double-confirm.
- **Media advanced:** everything in `ai_engine.media` (voice settings, clone/list, video2video, Agnes model, progress) + advanced image (analysis, image-to-image, quality) + prompt-driven advanced settings + text-rendering hints to reduce RU/cyrillic word errors.
- **Chat delivery:** explicit API + front form (not pure LLM tool-calling).

## Architecture

### `backend/writer_server/` (NEW — mirrors `rag_server`/`media_server`)
- `__init__.py`, `__main__.py`, `server.py`
- `server.py` uses `from mcp.server.mcpserver import MCPServer` (v2 API, same as rag_server/server.py).
- `main()` → `asyncio.run(mcp.run_stdio_async())`.

### Core engine (`writer_server/core.py`)
- **Root registry:** `workspace`, `output`, `temp`, plus user roots (read-only/write). Tools accept `root_id` + relative path; canonicalize + check containment (not string prefix). Symlink policy explicit (resolve + re-check).
- **Artifact manifest:** `manifest.jsonl` in the data dir. Each artifact: `artifact_id, path, family, size, version, date, hash, source, status`. Powers `list_artifacts`, `artifact_info`.
- **Typed errors:** taxonomy codes — `PATH_OUTSIDE_ROOT, PATH_TRAVERSAL, INVALID_SPEC, TEMPLATE_MISSING, FORMAT_UNSUPPORTED, LIMIT_EXCEEDED, CONFLICT_EXISTING_FILE, VALIDATION_FAILED, DEPENDENCY_MISSING, CANCELLED, TIMEOUT`. Every tool returns JSON with `ok, code, error` (never free-text).
- **Idempotency:** `idempotency_key` — repeat returns same `artifact_id`, not a duplicate.
- **Preview token:** `preview` mints a token bound to spec-hash + target path; `commit` validates it (spec change between preview and commit → reject).
- **Sanitization:** control chars / invisible unicode / secret redaction (keys, tokens, `.ssh`, `.env`) in preview/diff/logs. Tool responses are data, not instructions.
- **Limits:** max file size, line/cell/slide counts, archive depth, zip-bomb guard (ratio + absolute cap), `..`-in-archive block, content listing before extraction.
- **Trash/soft-delete:** overwrite → old version to `.trash/`; delete → soft with `restore`.

### Tool catalog (writer_server/server.py)
Common: `create_text`, `create_data` (json/yaml/csv), `create_code`, `create_office` (docx/xlsx/pptx), `create_pdf`, `create_archive` (zip/tar), `create_media` (delegate to media creds), `convert`, `read_artifact`, `list_artifacts`, `artifact_info`, `preview_generation`, `commit`, `diff_artifact`, `validate_artifact`, `delete_artifact`, `restore_artifact`, `cancel_job`, `render_template`, `list_templates`, `template_info`.

Family specifics:
- **Text/data:** markdown/json/yaml/csv validation (schema check for JSON/YAML, CSV column consistency, encoding/line-ending normalization).
- **Office:** input = Markdown or structural spec (NOT raw OOXML); templates with vars/conditions/loops; in-place edit (cells/sheets/paragraphs/slides) preserving formulas + formatting; PDF from Markdown/HTML + text extraction. Reuse `ai_engine.filegen` (docx/xlsx/pptx/pdf generators already exist).
- **Code:** scaffold from schema, patch existing, format; `dry_run`, diff, AST-parse after write (python/py_compile + language-aware); NO execution of generated code.
- **Media:** generator delegates to media provider (reuses media_creds) but owns save/metadata/validation/preview.
- **Archives:** zip/tar with bomb limits, `..` ban, content listing pre-extract.
- **Templates:** separate store, versioned, `list_templates`/`template_info`/`render_template`.

Two-stage validation: pre-write spec check + post-write open-with-library structure check (DOCX reads, XLSX opens + formulas intact, PDF page count, code parses to AST, CSV consistent, archive lists). Magic-bytes vs extension mismatch → `VALIDATION_FAILED`.

### main.py wiring
- `_writer_preset_config()` (mirror `_media_preset_config`): id `writer`, dev `python -m writer_server` + PYTHONPATH + `AMT_WRITER_DATA_DIR`; frozen `AMT_BACKEND_MODE=writer`. `auto_approve: False` (writes are high-risk).
- Endpoints: `GET/POST /api/mcp/presets/writer`, `POST /api/mcp/presets/writer/creds` (refresh media creds for the media-delegation family + write writer data dir env).
- `__main__` mode dispatch: add `elif _mode == "writer": from writer_server.server import main`.
- **Explicit user API:** `POST /api/writer/generate` (body: family, spec/content, title, template, overwrite) → calls the writer MCP tool `create_*` (or direct filegen for speed), saves to temp root, returns `download_url` + `preview`. Front form posts here.

### media_server additions (server.py)
New/extended tools (delegate to `ai_engine.media` when importable, else fallback):
- `generate_image` — add `quality`, `style`, `image_analysis` (describe/OCR an image), and a **text-rendering hint builder** (RU words → add `text="..."` guidance / use `ref_image_b64`) to reduce cyrillic word errors. Advanced prompt shaping.
- `generate_image_ref` — image-to-image / edit.
- `analyze_image` — vision: describe / extract text / extract structure from an image (OpenAI-compatible vision or provider-specific).
- `generate_audio` — `voice_settings` (speed/stability/style/similarity), `output_format`.
- `clone_voice`, `list_voices` — ElevenLabs + OpenAI-compatible.
- `generate_video` — `example_b64` (video2video), `quality`, `size`, `aspect_ratio`, Agnes model auto-select.
- `check_video` — progress field.
- Remove `generate_file` (moved to writer server).

Creds: `_write_media_creds` already has all needed keys. Add `audio_voice_id` + any vision fields if needed.

### Frontend
- `home.html` MCP section: add a third preset button `writer` (next to RAG + media) → `mcpInstallWriterPreset()`.
- `mcp.js`: add `mcpInstallWriterPreset()` (mirror `mcpInstallMediaPreset`).
- **Writer form:** new settings-page section `sec-writer` (or a generation panel) with family picker (Текст/Данные/Офис/Код/Архив/Медиа/Шаблон), spec textarea, title, template, overwrite toggle. Posts to `/api/writer/generate`. Result: download card + preview.
- Chat delivery: when a generation lands, surface the download card via the existing `tj.stored_name` / `download_url` pattern (init.js 548).

### Persistence decision
- **Manifest: persist** (JSONL in writer data dir) — historical queries ("what was generated when by what"), rotation/compaction, user diagnostics. Not cheap to derive.
- **Creds: persist** via existing `media_creds.json` (already wired).
- **Artifacts themselves: temp/output roots**, not a DB.

### Test plan
- Unit: path canonicalization + traversal, symlink policy, error taxonomy, limits/zip-bomb, idempotency, preview-token reject-on-change.
- Golden files per family: docx/xlsx/pptx/pdf/code/csv/json — generate + validate structure.
- E2E: API `/api/writer/generate` → create → preview → commit → validate → manifest entry → download.
- Contract: preview token — change spec between preview and commit → `CONFLICT`.
- Media: voice settings passthrough, clone/list, video2video, image analysis smoke.

### Rollout + risk
- Additive only: new server dir + new endpoints + one new preset button. Existing media `generate_file` is removed from media server but `ai_engine.filegen` + `/api/filegen/*` remain (no regression).
- Risk: zip-bomb / path traversal in writer → mitigated by canonicalization + limits + content listing.
- Risk: media "advanced" adds provider-dependent branches → keep fallbacks honest (`unsupported`).

## File list
NEW:
- `backend/writer_server/__init__.py`
- `backend/writer_server/__main__.py`
- `backend/writer_server/server.py`
- `backend/writer_server/core.py`
- `PLANS/writer-mcp.md` (this file)

MODIFY:
- `backend/main.py` (preset + endpoints + `__main__` dispatch + `/api/writer/generate`)
- `backend/media_server/server.py` (add advanced tools, drop `generate_file`)
- `frontend/home.html` (writer preset button + writer form section)
- `frontend/js/mcp/mcp.js` (`mcpInstallWriterPreset`)
- `frontend/js/core/main.js` (writer form submit handler)
