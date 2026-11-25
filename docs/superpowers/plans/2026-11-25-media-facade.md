# media.py Universal Generation Facade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a universal, modular, fault-tolerant `generate_media()` facade to `backend/ai_engine/media.py` with optional-settings fallback to `DEFAULT_*` constants, while keeping the 5 existing public functions and all tests intact.

**Architecture:** Provider-neutral. New `DEFAULT_*` constants (empty key/url by default, env-overridable; path constants have provider-neutral defaults). Three helpers: `_prepare_payload`, `_make_request`, `_get_path`. New `generate_media()` does try-custom → try-defaults fallback. The 5 existing functions keep their exact signatures but centralize payload/URL construction through the new helpers. A thin `main.py` surface forwards an optional `user_paths` dict + `attached_file` into the facade. A minimal frontend hook carries a chat-attached file's `ref_image_b64` into the media request.

**Tech Stack:** Python 3 / FastAPI / httpx / pytest; JS (vanilla) for the frontend hook.

**Spec:** `docs/superpowers/specs/2026-11-25-media-facade-design.md`

## Global Constraints

- **Provider-neutral defaults.** `DEFAULT_API_KEY` / `DEFAULT_BASE_URL` / `DEFAULT_MODEL` are **empty by default** (env-overridable). A user who sets nothing must get the same graceful "need base url" behavior as today — `tests/test_provider_neutral.py` must keep passing.
- **Verbatim rule.** If a user supplied a value for model/key/path, send it byte-for-byte. No `.strip()`/`.rstrip()` on the user's *model/key/path values*. The only allowed normalization is structural URL-join (`base_url.rstrip('/')`, `path.lstrip('/')`) — that is join syntax, not a value change.
- **No hardcoded paths in main logic.** Every endpoint path comes from `user_paths` or a `DEFAULT_PATH_*` constant.
- **Preserve signatures.** `generate_image`, `generate_image_ref`, `generate_video`, `generate_video_example`, `generate_audio` keep their exact parameter lists and `{ok, code, error, b64/url...}` return shape. `main.py` dispatch (lines 4498–4525) and the test suite (`test_media_filegen.py`, `test_media_chat.py`, `test_agnes_media.py`, `test_theming_configs.py`) are untouched.
- **Flat-dict return.** `generate_media` returns a **flat** dict on every outcome — provider keys at top level, NEVER nested under a `result` key. Success: `{"ok": True, **provider_keys}`. Double failure: `{"ok": False, "code": "api_error", "error": "..."}` (the literal error string in `res["error"]`).
- **base64-aware attachment.** `_prepare_payload` treats a string `attached_file` as base64 (or a data-URI), NOT as a path, unless it is a path to an existing file. Never `open()` a non-file string.
- **Preserve provider quirks.** Video task-poll and ElevenLabs host-rewrite logic inside the 5 functions must NOT be flattened into `_make_request` (they are not simple URL joins).

## Review Focus

Five input classes / failure modes the spec implies but no single task's tests exercise outright — add the listed test to the owning task:

- **Whitespace-only user field.** User enters `"   "` for `model` → treated as "not set" → `DEFAULT_MODEL` substituted. Test in Task 3 (facade).
- **Non-empty user field used verbatim.** User enters a custom `base_url` with a trailing slash and a model with leading spaces → URL-join normalizes only the slash; model passes through untouched. Test in Task 3.
- **Custom attempt fails, default succeeds (fallback happy path).** `httpx.post` raises for the custom config but succeeds for `DEFAULT_*` → returns the default attempt's result. Test in Task 3 (monkeypatch `_make_request` to fail once then succeed).
- **Both attempts fail (double error).** Both raise → returns `{ok:False, code:"api_error", error:"Ошибка кастомного API: …"}`. Test in Task 3.
- **attached_file is bytes vs. path string.** `_prepare_payload` accepts both; encodes to base64 into the payload. Test in Task 1 (helpers).

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/ai_engine/media.py` | Add `DEFAULT_*` constants, 3 helpers, `generate_media`; 5 fns delegate to helpers |
| `tests/test_media_facade.py` | New tests: helpers + facade fallback + verbatim/whitespace |
| `backend/main.py` | Optional `MediaGenRequest.paths` field; `main.py` builds `user_paths` + `attached_file` and can call `generate_media` (thin, no dispatch rewrite) |
| `frontend/js/main.js` | `renderGenInChat` carries a chat-attached file's `ref_image_b64` into the media POST |

---

### Task 1: Helpers `_prepare_payload`, `_make_request`, `_get_path` + `DEFAULT_*` constants

**Files:**
- Modify: `backend/ai_engine/media.py` (insert after the `_ELEVENLABS_HOST` block ~line 82, before `provider_profile`)
- Test: `tests/test_media_facade.py` (create)

**Interfaces:**
- Produces:
  - `DEFAULT_API_KEY: str`, `DEFAULT_BASE_URL: str`, `DEFAULT_MODEL: str` (empty by default, env-overridable)
  - `DEFAULT_PATH_TEXT_TO_MEDIA`, `DEFAULT_PATH_IMAGE_TO_MEDIA`, `DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA`, `DEFAULT_PATH_VOICE` (env-overridable, sensible defaults)
  - `_prepare_payload(prompt: str, model: str, attached_file=None) -> dict`
  - `_make_request(api_key: str, base_url: str, model: str, path: str, prompt: str, attached_file=None) -> dict`
  - `_get_path(has_file: bool, prompt: str, is_voice: bool, user_paths: dict = None) -> str`

- [ ] **Step 1: Write failing tests for the three helpers**

Create `tests/test_media_facade.py`:

```python
import base64
import media  # from backend, via conftest sys.path

def test_prepare_payload_minimal():
    p = media._prepare_payload("make a cat", "model-x")
    assert p["prompt"] == "make a cat"
    assert p["model"] == "model-x"
    assert "image" not in p and "file" not in p

def test_prepare_payload_attached_bytes():
    raw = b"\x89PNG\r\n\x1a\n"
    p = media._prepare_payload("cat", "m", attached_file=raw)
    expected = base64.b64encode(raw).decode("ascii")
    # image bytes -> "image" field
    assert p["image"] == expected or p["file"] == expected

def test_prepare_payload_attached_path(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"imgdata")
    p = media._prepare_payload("cat", "m", attached_file=str(f))
    assert p["image"] == base64.b64encode(b"imgdata").decode("ascii") or \
           p["file"] == base64.b64encode(b"imgdata").decode("ascii")

def test_prepare_payload_attached_b64_string_used_as_is():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=b64val)
    # a plain base64 string that is NOT a file path -> used as-is
    assert p["image"] == b64val

def test_prepare_payload_attached_data_uri_stripped():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=f"data:image/png;base64,{b64val}")
    assert p["image"] == b64val

def test_get_path_branches():
    assert media._get_path(False, "p", False) in (media.DEFAULT_PATH_TEXT_TO_MEDIA,)
    assert media._get_path(True, "p", False) in (media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA,)
    assert media._get_path(True, "", False) in (media.DEFAULT_PATH_IMAGE_TO_MEDIA,)
    assert media._get_path(False, "", True) in (media.DEFAULT_PATH_VOICE,)

def test_get_path_user_paths_override():
    up = {"text_to_media": "my/custom/path"}
    assert media._get_path(False, "p", False, up) == "my/custom/path"
    # empty user_paths entry falls back to default
    assert media._get_path(False, "p", False, {"text_to_media": ""}) == media.DEFAULT_PATH_TEXT_TO_MEDIA
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_facade.py -v`
Expected: FAIL with "module 'media' has no attribute '_prepare_payload'"

- [ ] **Step 3: Implement constants + 3 helpers in `backend/ai_engine/media.py`**

Insert after the `_ELEVENLABS_HOST = "elevenlabs.io"` line. Constants:

```python
import os, logging
_log = logging.getLogger(__name__)
DEFAULT_API_KEY = os.environ.get("AMT_DEFAULT_API_KEY", "")
DEFAULT_BASE_URL = os.environ.get("AMT_DEFAULT_BASE_URL", "")
DEFAULT_MODEL = os.environ.get("AMT_DEFAULT_MODEL", "")
DEFAULT_PATH_TEXT_TO_MEDIA = os.environ.get("AMT_PATH_TEXT_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_IMAGE_TO_MEDIA = os.environ.get("AMT_PATH_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA = os.environ.get("AMT_PATH_TEXT_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_VOICE = os.environ.get("AMT_PATH_VOICE", "v1/audio/speech")
```

`_get_path(has_file, prompt, is_voice, user_paths=None)`: branch per spec; read `user_paths.get(key)` and use it when truthy, else the matching `DEFAULT_PATH_*`. Keys: `text_to_media`, `image_to_media`, `text_image_to_media`, `voice`.

`_prepare_payload(prompt, model, attached_file=None)`: start with `{"prompt": prompt, "model": model}`. Then handle `attached_file` by type (front-end sends base64-strings, so string input is NOT assumed to be a path):
- **bytes** → `b64 = base64.b64encode(attached_file).decode("ascii")` → store under `"image"`.
- **str starting with `data:` (data URI)** → strip the prefix up to and including the comma (e.g. `data:image/png;base64,`), use the remainder as the base64 value → store under `"image"`.
- **str that is a plain base64 string** (not a `data:` URI AND not a path to an existing file) → use it AS-IS (do NOT call `open()`) → store under `"image"`.
- **str that IS a path to an existing file** (`os.path.exists(path)`) → `open(path,'rb').read()` then b64-encode → store under `"image"`.
Decision order matters: check `data:` prefix first, then `os.path.exists`, otherwise treat the string as already-encoded base64. Never trim `prompt`. Never call `open()` on a non-file string.

`_make_request(api_key, base_url, model, path, prompt, attached_file=None)`:
`url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"`; `payload = _prepare_payload(...)`; `resp = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)`; `resp.raise_for_status()`; `return resp.json()`.

Reuse the module's existing `httpx` import. Use `_log` for logging.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_facade.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ai_engine/media.py tests/test_media_facade.py
git commit -m "feat(media): add DEFAULT_* constants and _prepare_payload/_make_request/_get_path helpers"
```

---

### Task 2: `generate_media()` facade with try-custom → try-defaults fallback

**Files:**
- Modify: `backend/ai_engine/media.py` (add after the 5 existing functions)
- Test: `tests/test_media_facade.py` (append)

**Interfaces:**
- Consumes: `_make_request`, `_get_path`, `DEFAULT_*` from Task 1; the kind-specific function the facade routes to.
- Produces: `generate_media(user_api_key, user_base_url, user_model, user_paths, prompt, attached_file=None, is_voice=False) -> dict`

- [ ] **Step 1: Write failing tests for the facade**

Append to `tests/test_media_facade.py`:

```python
import types

def test_generate_media_success_custom(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None):
        captured.update(api_key=api_key, base_url=base_url, model=model, path=path, prompt=prompt)
        # provider-style body (what _make_request returns via resp.json())
        return {"b64": "AAAA", "url": "u"}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("KEY", "https://api.example", "mod-1",
                               {"text_to_media": "my/path"}, "a cat")
    # FLAT contract: provider keys land at top level, no "result" nesting
    assert res["ok"] is True
    assert res["b64"] == "AAAA"
    assert "result" not in res
    assert captured["api_key"] == "KEY"
    assert captured["base_url"] == "https://api.example"
    assert captured["model"] == "mod-1"
    assert captured["path"] == "my/path"

def test_generate_media_fallback_to_defaults(monkeypatch):
    calls = []
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None):
        calls.append((api_key, base_url, model, path))
        if api_key == "BAD_KEY":
            raise RuntimeError("custom failed: 401")
        return {"b64": "BBBB"}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("BAD_KEY", "https://bad", "bad-model", {}, "prompt", attached_file=b"raw")
    assert res["ok"] is True
    assert res["b64"] == "BBBB"      # flat: from the successful default attempt
    assert "result" not in res
    assert len(calls) == 2
    # second call used strict defaults
    assert calls[1][0] == media.DEFAULT_API_KEY
    assert calls[1][1] == media.DEFAULT_BASE_URL
    assert calls[1][2] == media.DEFAULT_MODEL

def test_generate_media_double_failure(monkeypatch):
    def fake_make_request(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    res = media.generate_media("K", "U", "M", {}, "p")
    assert res["ok"] is False
    assert res["code"] == "api_error"
    assert "Ошибка кастомного API" in res["error"]
    assert "Ошибка дефолтного API" in res["error"]

def test_generate_media_whitespace_user_field_substituted(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None):
        captured["model"] = model
        return {"ok": True}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    # whitespace model -> DEFAULT_MODEL on attempt 1
    media.generate_media("KEY", "BASE", "   ", {}, "p")
    assert captured["model"] == media.DEFAULT_MODEL

def test_generate_media_verbatim_model_not_trimmed(monkeypatch):
    captured = {}
    def fake_make_request(api_key, base_url, model, path, prompt, attached_file=None):
        captured["model"] = model
        return {"ok": True}
    monkeypatch.setattr(media, "_make_request", fake_make_request)
    media.generate_media("KEY", "BASE", "  my-model  ", {}, "p")
    # verbatim: NOT trimmed
    assert captured["model"] == "  my-model  "
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_facade.py -v`
Expected: FAIL with "module 'media' has no attribute 'generate_media'"

- [ ] **Step 3: Implement `generate_media` in `backend/ai_engine/media.py`**

```python
def _is_empty(v):
    """Whitespace/None/'' all count as 'not set' -> substitute default."""
    return (v is None) or (v.strip() == "")

def generate_media(user_api_key, user_base_url, user_model, user_paths,
                   prompt, attached_file=None, is_voice=False):
    has_file = bool(attached_file)
    path = _get_path(has_file, prompt, is_voice, user_paths)
    up = user_paths or {}

    # attempt 1: user values verbatim when set, else strict DEFAULT_*
    active_api_key = user_api_key if not _is_empty(user_api_key) else DEFAULT_API_KEY
    active_base_url = user_base_url if not _is_empty(user_base_url) else DEFAULT_BASE_URL
    active_model = user_model if not _is_empty(user_model) else DEFAULT_MODEL
    # active path: user's path if set (verbatim), else the _get_path default
    active_path_key = "voice" if is_voice else \
        "text_image_to_media" if has_file and prompt else \
        "image_to_media" if has_file else "text_to_media"
    active_path = up.get(active_path_key) if not _is_empty(up.get(active_path_key)) else path

    try:
        result = _make_request(active_api_key, active_base_url, active_model,
                               active_path, prompt, attached_file)
        return {"ok": True, "result": result}   # _make_request already returns a dict
    except Exception as e:
        err1 = str(e)
        _log.warning("media: custom config failed, falling back to defaults: %s", err1)
        try:
            result = _make_request(DEFAULT_API_KEY, DEFAULT_BASE_URL, DEFAULT_MODEL,
                                   path, prompt, attached_file)
            return {"ok": True, "result": result}
        except Exception as e2:
            err2 = str(e2)
            return {"ok": False, "code": "api_error",
                    "error": f"Ошибка кастомного API: {err1}. Ошибка дефолтного API: {err2}"}
```

**Flat return contract (CRITICAL):** `generate_media` returns a **flat** dict, never one nested under a `result` key. The two successful returns above already look like `{"ok": True, "result": <dict>}` where `<dict>` is the value `_make_request` produced — i.e. the provider's JSON body. **Flatten it one level into the top-level dict** so the app sees `{"ok": True, ...provider_keys...}` with no nesting:

```python
        result = _make_request(active_api_key, active_base_url, active_model,
                               active_path, prompt, attached_file)
        out = {"ok": True}
        out.update(result if isinstance(result, dict) else {"data": result})
        return out
```

Apply the identical flatten to the default-attempt branch. On double failure return exactly `{"ok": False, "code": "api_error", "error": "..."}` (already shown above).

Note: `_is_empty` treats `None`/`""`/whitespace-only as "not set" → substitute the `DEFAULT_*`. A non-whitespace user value (e.g. `"  my-model  "`) is **sent verbatim, untrimmed** — this satisfies both the whitespace-substitution test and the verbatim test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_media_facade.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ai_engine/media.py tests/test_media_facade.py
git commit -m "feat(media): add generate_media facade with custom->defaults fallback"
```

---

### Task 3: Delegate the 5 existing functions to shared helpers (no signature change)

**Files:**
- Modify: `backend/ai_engine/media.py` (the 5 functions' HTTP bodies)
- Test: `tests/test_media_facade.py` (append a guard) + existing `tests/test_media_filegen.py`, `tests/test_media_chat.py` (must keep passing)

**Interfaces:**
- Consumes: `_prepare_payload`, `_make_request` from Task 1.
- Produces: same 5 public signatures.

- [ ] **Step 1: Add a regression guard test**

Append to `tests/test_media_facade.py`:

```python
def test_generate_image_signature_unchanged():
    # generate_image must keep its exact param names
    import inspect
    sig = inspect.signature(media.generate_image)
    assert list(sig.parameters) == ["base_url", "api_key", "model", "prompt",
                                    "size", "proxy", "extra"]
```

- [ ] **Step 2: Centralize payload/URL in the 5 functions**

In each of `generate_image_ref`, `generate_video`, `generate_video_example`, `generate_audio`, `generate_image`:
- Build the request body via `_prepare_payload(prompt, model, attached)` instead of hand-rolling the dict, **except** where a function has provider-specific extra fields (size, duration, aspect_ratio, voice, ElevenLabs params) — those are merged in AFTER `_prepare_payload`.
- For the plain POST, route through `_make_request` where the URL is a simple base+path join. **Do NOT** flatten ElevenLabs host-rewrite or video task-poll — those keep their special logic; only the payload-construction step is shared.
- No change to any public signature or return dict.

- [ ] **Step 3: Run the full media test suite**

Run: `pytest tests/test_media_facade.py tests/test_media_filegen.py tests/test_media_chat.py tests/test_agnes_media.py tests/test_theming_configs.py tests/test_provider_neutral.py -v`
Expected: PASS (all pre-existing media tests + the new facade tests)

- [ ] **Step 4: Commit**

```bash
git add backend/ai_engine/media.py tests/test_media_facade.py
git commit -m "refactor(media): delegate 5 public functions to shared payload/URL helpers"
```

---

### Task 4: `main.py` surface — forward `user_paths` + `attached_file` into the facade

**Files:**
- Modify: `backend/main.py` — `MediaGenRequest` (add optional `paths: dict = None`), and a thin wrapper path that calls `media_gen.generate_media` when `req.paths` or an attached file is present; otherwise keep the existing 5-function dispatch.

**Interfaces:**
- Consumes: `media_gen.generate_media` (Task 2).
- Produces: `/api/media/generate` now accepts `paths` and forwards `ref_image_b64`/`video_example_b64` as `attached_file` to the facade.

- [ ] **Step 1: Add optional `paths` field**

In `MediaGenRequest` (main.py:4400): add `paths: dict = None`. This is the `user_paths` the facade consumes. No new `Settings` fields required for the facade path (the dict is passed through verbatim from the request; `Settings` stays provider-neutral).

- [ ] **Step 2: Thin facade branch in `_media_generate_inner`**

After `cfg = _media_cfg(req)`, if `req.paths is not None` OR `req.ref_image_b64` is set, route through the facade:
```python
if req.paths is not None or req.ref_image_b64:
    attached = req.ref_image_b64 or req.video_example_b64 or None
    is_voice = (req.kind == "audio")
    return media_gen.generate_media(cfg["key"], cfg["base"], cfg["model"],
                                     req.paths, req.prompt,
                                     attached_file=attached, is_voice=is_voice)
# else: existing 5-function dispatch unchanged
```
This is additive — the existing dispatch is untouched, so no test breaks.

- [ ] **Step 3: Verify existing endpoints still work**

Run: `pytest tests/test_media_chat.py tests/test_media_filegen.py -v`
Expected: PASS (existing dispatch unchanged)

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(main): forward user_paths + attached_file into generate_media facade"
```

---

### Task 5: Frontend hook — carry a chat-attached file into the media request

**Files:**
- Modify: `frontend/js/main.js` — `renderGenInChat` (line ~4220) and the `uploadAttachments`/`attachedFiles` flow.

**Interfaces:**
- Produces: when the current chat message had a file attachment and the assistant emits a `[[GEN:image|…]]` / `[[GEN:video|…]]` token, the POST body includes `ref_image_b64` so the backend forwards it to `generate_media(attached_file=…)`.

- [ ] **Step 1: Read the attachment as base64 in `renderGenInChat`**

In `renderGenInChat`, before the image/video `post(...)`, check whether the chat message's `attachments` (from `getCurrentChat().messages[last].files` or the `attachmentsPayload` captured at send time) has an image entry. If so, read it via the existing `readFileAsBase64` helper and include `ref_image_b64` in the POST body:
```js
const att = _currentMsgAttachments[0]; // image attachment, if any
if (att && /^(image|video)$/.test(kind)) {
    body.ref_image_b64 = await readFileAsBase64(att.file);
}
```
Capture the send-time `attachmentsPayload` into a module-scoped `_currentMsgAttachments` that `processGenTokens` can read (set it in `sendMessage` right before `streamViaWebSocket`).

- [ ] **Step 2: Verify the JS is syntactically valid**

Run: `node --check frontend/js/main.js`
Expected: no syntax errors

- [ ] **Step 3: Commit**

```bash
git add frontend/js/main.js
git commit -m "feat(frontend): forward chat-attached file as ref_image_b64 into media gen"
```

---

## Self-Review Notes

- **Spec coverage:** constants (T1), 3 helpers (T1), facade + fallback + verbatim/whitespace (T2), 5-fn delegation (T3), main.py surface (T4), UI hook (T5). All sections of the spec mapped.
- **Step scan:** each code step gives exact signature + the one decision left to the builder (e.g., T3 "which functions keep special logic"). No transcript bodies except T2/T3 where the algorithm is non-trivial and pinned by tests.
- **Type consistency:** `user_paths` keys (`text_to_media`, `image_to_media`, `text_image_to_media`, `voice`) are identical in T1 (`_get_path`), T2 (`generate_media`), and T4 (`req.paths`). `attached_file` is `None|str|bytes` consistently.
- **Review Focus:** all five failure modes pinned to T1/T2 tests (whitespace→default, verbatim, fallback happy path, double failure, bytes-vs-path).
- **Proportion:** plan is ~ the size of the spec; bodies appear only where tests don't determine the algorithm.
