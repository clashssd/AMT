# media.py — Universal Generation Facade (Design)

## Intent

Rewrite the generation logic in `backend/ai_engine/media.py` so it is **universal,
modular, and fault-tolerant**. Users set API keys / base URLs / models / endpoint
paths in the UI. **Every one of those fields is optional**: if a field is empty,
`None`, or whitespace, the app auto-substitutes a default constant. If the user
entered something, it is used **verbatim** (no trimming, no re-formatting). There
are **no hardcoded paths in the main logic** — every path comes from settings or a
default constant.

New universal entry point: `generate_media(...)`, which routes by the presence of
an attached file + the prompt, picks the right endpoint path, attempts the
**custom** config first, and on failure **falls back to strict defaults**,
surfacing both errors if both fail.

The existing 5 public functions stay and delegate to the new shared helpers, so
`main.py` dispatch and the test suite keep working.

## Goals / Non-goals

Goals:
- New `generate_media()` facade with the try-custom → try-defaults fallback.
- Helper functions `_prepare_payload`, `_make_request`, `_get_path`.
- `DEFAULT_*` constants (provider-neutral: empty by default, overridable via env).
- A minimal UI hook so chat-attached files reach `generate_media` as `attached_file`.
- The 5 existing public functions (`generate_image`, `generate_image_ref`,
  `generate_video`, `generate_video_example`, `generate_audio`) keep their exact
  signatures; their internals delegate to the shared helpers.

Non-goals:
- Do NOT rewrite `main.py`'s dispatch or collapse the 5 functions into one.
- Do NOT bake a real default provider/key into `media.py` (provider-neutral
  defaults are empty; `tests/test_provider_neutral.py` must keep passing).
- Do NOT change the chat `[[GEN:...]]` token protocol or add a new media button.

## Constraints

- `tests/test_provider_neutral.py` pins: `Settings()` defaults are empty; a
  non-OpenAI `base_url` flows through verbatim; empty base_url+key → graceful
  "need base url". `media.py` must keep returning graceful `{ok:False, code:...}`
  dicts and keep its provider-neutral behavior.
- The 5 public function signatures/return contracts are consumed by `main.py`
  (`_media_generate_inner`, dispatch at main.py:4500–4525) and by
  `tests/test_media_filegen.py`, `test_media_chat.py`, `test_agnes_media.py`,
  `test_theming_configs.py` (they monkeypatch `media._client`). All must stay.
- `main.py`'s `MediaGenRequest` already has `ref_image_b64` and
  `video_example_b64` fields. `main.py`'s `_media_cfg` already does
  optional→settings fallback. The new facade adds the **default-constant** layer
  on top of that.

## Approaches considered

**A. Facade alongside existing functions (CHOSEN).**
Add `generate_media()` + helpers + `DEFAULT_*` constants to `media.py`. The 5
existing functions keep their signatures and delegate to the new shared helpers.
`main.py` keeps dispatching as today; tests untouched. `generate_media()` is the
new recommended single entry point (used by the chat-attach UI hook and any
future code).
- Why chosen: matches the user's spec literally (new universal fn + helpers +
  constants), zero breakage to the test suite / `main.py` / provider-neutrality.
- Tradeoff: two entry points coexist until `main.py` migrates to the facade.

**B. Replace the 5 functions with `generate_media()`; rewrite `main.py`.**
- Rejected: rewrites `main.py` dispatch and breaks every test that calls
  `media.generate_*`. The user asked for a generation-logic rewrite, not a
  `main.py` overhaul.

**C. `attached_file` UI hook.**
The chat already attaches files (`uploadAttachments()` → backend `/api/files/upload`
→ `FILES_DIR`, sent to `/api/chat` as `attachments`). Media gen in-chat happens
via `[[GEN:...]]` tokens that call `/api/media/generate` — which today sends
**no** attached file. The hook: when a chat message has attached files AND the
assistant emits a `[[GEN:…]]` media token, pass the first attachment's
`ref_image_b64` (or its uploaded path) into the `/api/media/generate` body so it
lands in `generate_media(…, attached_file=…)`. This makes the image→media and
text+image→media routes reachable from the UI without a new button.
- Why chosen: reuses the existing attachment pipeline (files already uploaded and
  stored in `FILES_DIR`); minimal surface; no new protocol.

## Design

### 1. Constants (provider-neutral, env-overridable)

```python
import os
DEFAULT_API_KEY      = os.environ.get("AMT_DEFAULT_API_KEY", "")
DEFAULT_BASE_URL     = os.environ.get("AMT_DEFAULT_BASE_URL", "")
DEFAULT_MODEL        = os.environ.get("AMT_DEFAULT_MODEL", "")
DEFAULT_PATH_TEXT_TO_MEDIA      = os.environ.get("AMT_PATH_TEXT_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_IMAGE_TO_MEDIA    = os.environ.get("AMT_PATH_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA = os.environ.get("AMT_PATH_TEXT_IMAGE_TO_MEDIA", "v1/images/generations")
DEFAULT_PATH_VOICE   = os.environ.get("AMT_PATH_VOICE", "v1/audio/speech")
```

Empty key/url/model keep provider-neutrality (a user who set none gets graceful
"need base url" behavior, exactly as today). Path constants have sensible
provider-neutral defaults so the fallback has *something* to try.

### 2. `_prepare_payload(prompt, model, attached_file=None)`

Builds the JSON dict. Always adds `prompt` and `model`. If `attached_file` is a
path string or bytes: read it (path → bytes), base64-encode, and add to the
payload. Field name chosen by content type (image → `image`, generic file →
`file`); returns the dict. No trimming of `prompt`.

### 3. `_make_request(api_key, base_url, model, path, prompt, attached_file=None)`

```python
url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
payload = _prepare_payload(prompt, model, attached_file)
resp = httpx.post(url, json=payload,
                  headers={"Authorization": f"Bearer {api_key}"},
                  timeout=60)
resp.raise_for_status()
return resp.json()
```

### 4. `_get_path(has_file, prompt, is_voice, user_paths=None)`

Returns the chosen **path string**. Resolution order per branch:
- `is_voice` → `user_paths['voice']` if set else `DEFAULT_PATH_VOICE`.
- `has_file` and prompt non-empty → `user_paths['text_image_to_media']` else
  `DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA`.
- `has_file` and prompt empty → `user_paths['image_to_media']` else
  `DEFAULT_PATH_IMAGE_TO_MEDIA`.
- else → `user_paths['text_to_media']` else `DEFAULT_PATH_TEXT_TO_MEDIA`.

`user_paths` is the dict the caller passes (from settings or env); missing/empty
entries fall back to the `DEFAULT_PATH_*` constants.

### 5. `generate_media(user_api_key, user_base_url, user_model, user_paths,
prompt, attached_file=None, is_voice=False)`

Return shape (SETTLED): **always a FLAT dict** — provider keys land at the
top level, never nested under a `result` key. On success the facade takes the
provider's JSON body from `_make_request` and flattens it: `{"ok": True,
<b64/url/...>}`. On double-failure the spec's literal string
`f"Ошибка кастомного API: {err1}. Ошибка дефолтного API: {err2}"` is placed in
`res["error"]` (with `ok: False, code: "api_error"`). Never a bare string,
never `{"ok": True, "result": {...}}`.

user_paths source (SETTLED): a new optional `Settings.paths` surface —
`MediaGenRequest.paths: dict` + `Settings.imagePath/videoPath/audioPath`
(per-kind, all optional, default ""). `main.py` builds `user_paths` from
`req.paths` (falling back to `Settings.paths`), passing it into the facade. The
facade's `_get_path` reads `user_paths` by key (`voice`, `text_image_to_media`,
`image_to_media`, `text_to_media`), substituting the `DEFAULT_PATH_*` constant
when the key is missing/empty.

1. Determine `has_file = bool(attached_file)` and `is_voice`.
2. `path = _get_path(has_file, prompt, is_voice, user_paths)` (custom path).
3. Build the *active* config (custom-first):
   ```python
   active_api_key   = user_api_key   if user_api_key   else DEFAULT_API_KEY
   active_base_url  = user_base_url  if user_base_url  else DEFAULT_BASE_URL
   active_model     = user_model     if user_model     else DEFAULT_MODEL
   active_path      = user_paths.get('…', path) if (user_paths or {}).get('…') else path
   ```
4. **Attempt 1** (try): `_make_request(active_…)`; on success → return result.
   On exception: `err1 = str(e)`; log `err1`.
5. **Attempt 2** (strict defaults, new try): `_make_request(DEFAULT_API_KEY,
   DEFAULT_BASE_URL, DEFAULT_MODEL, <default path for this branch>, prompt,
   attached_file)` — same `prompt`/`attached_file`. On success → return.
   On exception: `err2 = str(e)`.
6. Both failed → return the error string
   `f"Ошибка кастомного API: {err1}. Ошибка дефолтного API: {err2}"`
   (wrapped in the module's result-dict shape: `{"ok": False, "code": "api_error",
   "error": that_string}` for API consumers; the facade returns a plain string
   when called with no config and both fail, matching the spec's literal
   "Верни строку").
7. On success: flatten the provider body one level into the top-level dict and
   return `{"ok": True, **provider_keys}`.

### `_prepare_payload` attached-file handling (base64-aware, SETTLED)

The frontend sends files as **base64 strings** (`ref_image_b64`), so a string
`attached_file` is NOT assumed to be a path. Decision order:
1. `bytes` → base64-encode → store under `"image"`.
2. str starting with `data:` (data URI) → strip the prefix up to and including
   the comma → store the remainder under `"image"`.
3. str that is a plain base64 string (no `data:` prefix AND not a path to an
   existing file) → use **as-is** → store under `"image"`.
4. str that IS a path to an existing file (`os.path.exists`) → read + b64-encode
   → store under `"image"`.
Never call `open()` on a non-file string.

The empty-checks use a `_is_empty(v)` helper (`None`/`""`/whitespace-only → not
set → substitute `DEFAULT_*`). The **verbatim** rule means if a user typed a
non-whitespace value, we send that value byte-for-byte (no `.strip()`/
`.rstrip('/')` on the *user's* model/key/path — only `base_url`/`path`
URL-join normalization, which is structural, not a value change).

### 6. Delegation of the 5 existing functions

Each existing function (`generate_image`, `generate_image_ref`, `generate_video`,
`generate_video_example`, `generate_audio`) keeps its signature and return-dict
shape, but its HTTP body is built through `_prepare_payload` + `_make_request`
so the payload/URL logic is shared and consistent. The provider-specific
quirks (ElevenLabs host detection, base-URL tail trimming, task polling for
video) remain in thin wrappers; the request construction is centralized. No
signature or contract change.

### 7. UI hook (chat-attach → `generate_media` attached_file)

In `frontend/js/main.js`:
- `renderGenInChat` currently posts `{kind, prompt, …}` to
  `/api/media/generate` with **no** attachment. Capture the most recent
  `attachmentsPayload` from the current chat message (already in `FILES_DIR`
  with a `{path, filename, mime_type}` shape). When posting an image/video
  GEN token, if the chat message had a file attachment, include
  `ref_image_b64` (read the first attachment from `FILES_DIR` on the backend,
  or pass its path).
- Backend: `main.py`'s `_media_cfg`/`_media_generate_inner` already reads
  `req.ref_image_b64`. For the *new* universal path, `main.py` gains a thin
  wrapper endpoint (or the existing `/api/media/generate` body is extended) that
  forwards `ref_image_b64`/`attached_file` into `media_gen.generate_media(…,
  attached_file=ref_image_b64)`. The 5-function dispatch is left in place.

Minimal, reuses existing fields. No new UI button, no protocol change.

## Settled builder calls

- Result-dict shape: always `{ok, code, error, b64/url}`; double-failure string
  goes in `error` (see §5).
- `ref_image_b64` / `attached_file`: read **server-side** from `FILES_DIR` via
  the existing `_fetch_url_to_b64` / attachment path resolution. The frontend
  only needs to ship the attachment's `path`/`filename` (already in
  `attachmentsPayload`); the backend converts to base64 before calling
  `generate_media(attached_file=...)`. Keeps the UI hook minimal.
- Logging: `logging.getLogger(__name__)` for the `err1` log line; the module
  may already have a logger — reuse it if present.

## What's left to the builder

- Wire the new `Settings.paths` fields into `main.py`'s `_media_cfg` so
  `user_paths` is assembled and passed to `generate_media` from
  `/api/media/generate`.
- Preserve the video task-poll and ElevenLabs host-rewrite logic inside the 5
  delegated functions (they are NOT simple URL joins — see builder check #4).

## Files touched

- `backend/ai_engine/media.py` — new constants, 4 helpers, `generate_media`;
  5 functions delegate.
- `frontend/js/main.js` — `renderGenInChat` carries the attachment into the
  media request.
- `backend/main.py` — optional: forward `attached_file` into
  `generate_media` (thin, no dispatch rewrite).
- Tests: new `tests/test_media_facade.py` covering the fallback + empty-default
  substitution (existing tests untouched).
