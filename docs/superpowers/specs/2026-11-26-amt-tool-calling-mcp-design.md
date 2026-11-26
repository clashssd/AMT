# Design: AMT Native Tool Calling + MCP Integration

**Date:** 2026-11-26  
**Author:** Agnes-3.0-flash  
**Status:** Draft for approval

---

## 1. Intent & Why

AMT currently drives LLM interactions via a custom text-tag protocol (`[[GEN:...]]`, `[[SYS:...]]`, `[[WEBSEARCH:...]]`). This is brittle: tags leak into user-visible text when models misparse, models without tool support require the entire protocol to stay alive, and adding a new tool means editing regex + prompt blocks + frontend parsers.

This design replaces the text-tag approach with **native LLM tool calling** (OpenAI-compatible `tools` / `tool_calls` / `tool` messages) for supported models, while keeping `[[GEN]]` as a fallback for models that don't support tools. It also adds **MCP (Model Context Protocol)** as an external tool source so users can connect STDIO or HTTP MCP servers and their tools become callable by the LLM alongside native tools.

**Why now:** The AMT chat is the primary user surface; making tools first-class (schemas sent to LLM, structured `tool_calls` in responses) improves reliability, enables richer tool visualization in the UI, and opens the door to the ecosystem of MCP servers without custom per-tool code.

---

## 2. Goals

- G1: LLM receives tool schemas (JSON) in the `tools` field of `/chat/completions` when the model supports tool-calling.
- G2: When the LLM returns `tool_calls`, AMT executes them via a unified **Tool Registry**, appends `tool`-role messages, and re-calls the LLM (loop, max N iterations).
- G3: Native tools registered: `generate_image`, `generate_video`, `generate_audio`, `generate_file`. Each maps to existing `media.py` / `filegen.py` functions.
- G4: MCP servers (STDIO + HTTP) can be added, listed, enabled/disabled, and deleted from settings UI. Their tools appear in the LLM's tool list with `mcp__<server>__<tool>` name prefix.
- G5: `[[GEN]]` parsing is retained as a fallback path for models that don't support native tool-calling. The LLM prompt still includes the MEDIA_CAPABILITY block when the model lacks tool support.
- G6: MCP server env vars are encrypted at rest (backend-level Fernet key).
- G7: MCP child processes are killed on app exit (backend atexit + Electron `before-quit` already stops the sidecar).
- G8: Tool-call events are streamed to the frontend via WS so the UI can render a "tool running" indicator.

## 3. Non-Goals

- No MCP stdio servers auto-discovered from system paths.
- No OAuth/token exchange for MCP HTTP servers (user provides raw env/headers).
- No changes to existing `/api/media/*` or `/api/tools/*` REST endpoints (they remain for direct UI use).
- No tool-call visualization beyond a simple inline card (image/video/audio/file result reuses existing `renderGenInChat`-style rendering).
- No migration of `[[SYS:...]]` system-interaction tags to native tools in this pass (they stay as-is for the sysinteraction subsystem).

## 4. Constraints

- AMT backend is Python 3.10+, FastAPI + httpx.
- LLM API is OpenAI-compatible (any base_url). Some models (e.g. older Ollama, some local models) don't support `tools` field → fallback path needed.
- `call_ai_api()` already has multi-key rotation, context compaction, jailbreak retry. Tool-calling loop must compose with these.
- Frontend is vanilla JS in `home.html` + `main.js` (no framework).
- PyInstaller build: `mcp` SDK adds ~2 MB; acceptable.
- Security: AMT already has Host/Origin validation, CORS allowlist, internal secrets channel. MCP tool execution must respect the existing `/api/tools/execute` approval gate for system-level tools; media/file-gen tools are safe (no filesystem write beyond FILES_DIR).

---

## 5. Approaches Considered

| Approach | Description | Trade-offs | Picked? |
|----------|-------------|------------|---------|
| **A. Unified Tool Registry + native tool-calling loop** | One `tool_registry.py` that builds OpenAI-format schemas from native tools + MCP tools. `call_ai_api()` adds a post-response loop: if `tool_calls` present, execute via registry, append `tool` messages, re-call LLM. `[[GEN]]` stays as fallback when model lacks tool support. | Clean separation; LLM sees structured tools; loop is bounded (max 5 iterations). Slightly more code in `call_ai_api()`. | ✅ **Picked** |
| **B. Keep `[[GEN]]` tags as primary, add MCP as separate subsystem** | Don't change the LLM prompt; MCP tools are invoked via a separate orchestrator that intercepts tool responses. | Simpler diff, but two parallel tool systems; LLM can't "decide" to use MCP tools autonomously; `[[GEN]]` fragility remains. | ❌ |
| **C. Full migration: remove `[[GEN]]` entirely, use native tools for all models** | Hard cutover; models without tool support break. | Cleanest long-term, but breaks users on tool-incapable models. | ❌ (spec says keep fallback) |

**Chosen:** Approach A. It's the incremental path the spec calls for: additive tool-calling for capable models, `[[GEN]]` fallback preserved, MCP as an external source feeding into the same registry.

---

## 6. Architecture

### 6.1 Tool Registry (`backend/ai_engine/tool_registry.py`)

```python
@dataclass
class ToolDef:
    name: str            # e.g. "generate_image" or "mcp__fs__read_file"
    description: str
    parameters: dict     # JSON Schema (OpenAI function-calling format)
    handler: Callable    # async fn(**kwargs) -> str (JSON-serializable result)
    source: str          # "native" | "mcp:<server_id>"

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef): ...
    def unregister_prefix(self, prefix: str): ...  # e.g. "mcp__server1"
    def schemas(self) -> list[dict]:
        """Return OpenAI-format: [{"type":"function","function":{"name","description","parameters"}}]"""
    async def execute(self, name: str, args: dict) -> str:
        """Execute tool, return JSON string result. Raises ToolExecutionError on failure."""
```

Native tools registered at import time:

| Tool name | Handler | Maps to |
|-----------|---------|---------|
| `generate_image` | `media.generate_image(prompt, size, model, ref_image_b64?)` | `/api/media/generate` kind=image |
| `generate_video` | `media.generate_video(prompt, aspect_ratio, duration, model)` | `/api/media/generate` kind=video |
| `generate_audio` | `media.generate_audio(text, voice_id, model)` | `/api/media/generate` kind=audio |
| `generate_file` | `filegen.generate_file(filetype, content, title, lang)` → save to FILES_DIR, return stored_name + preview | `/api/filegen/generate` |

MCP tools: when an MCP server is enabled, `MCPManager` lists its tools and registers each as `mcp__<server>__<tool>` with the server's JSON schema. Handler wraps `MCPManager.call_tool(server, tool, args)`.

### 6.2 MCP Manager (`backend/ai_engine/mcp_manager.py`)

```python
@dataclass
class MCPServerConfig:
    id: str
    name: str
    transport: str      # "stdio" | "http"
    command: str        # stdio: "npx", args stored in list
    args: list[str]
    url: str            # http: "http://localhost:3000/mcp"
    headers: dict
    env: dict           # encrypted at rest
    enabled: bool

class MCPManager:
    def __init__(self, data_dir: str):
        self.servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}  # connected instances
        self._fkey: Fernet

    # -- Config CRUD (persisted to mcp_servers.json, env vars Fernet-encrypted)
    def list_servers(self) -> list[MCPServerConfig]
    def add_server(self, cfg: MCPServerConfig)
    def update_server(self, cfg: MCPServerConfig)
    def remove_server(self, server_id: str)
    def set_enabled(self, server_id: str, enabled: bool)

    # -- Connection management (lifecycle)
    async def connect(self, server_id: str) -> None     # spawns subprocess or opens HTTP
    async def disconnect(self, server_id: str) -> None  # kills subprocess / closes session
    async def list_tools(self, server_id: str) -> list[dict]  # [{name, description, inputSchema}]
    async def call_tool(self, server_id: str, tool: str, args: dict) -> str
    async def health(self, server_id: str) -> dict     # {status: "connected"|"disconnected"|"error", message}

    # -- Cleanup
    def shutdown(self) -> None   # kills all child processes
```

**Transport details:**
- **STDIO:** Uses `mcp` SDK's `stdio_client` → spawns `command args` subprocess, speaks JSON-RPC over stdin/stdout. Tracked in `self._procs: dict[str, asyncio.subprocess.Process]`.
- **HTTP:** Uses `mcp` SDK's `streamable_http_client` → opens session to `url` with optional `headers`. No child process; just an HTTP connection.
- **Timeout:** Tool calls have a 30 s timeout (`asyncio.wait_for`). On timeout, the tool result is an error string: `{"error": "MCP tool call timed out after 30s"}`.
- **Name prefixing:** All MCP tools are registered as `mcp__<server_id>__<tool_name>` to avoid collisions with native tools.

**Encryption (env vars):**
- Fernet key stored in `<data_dir>/mcp_key.key` (auto-created on first use).
- `MCPServerConfig.env` dict values are encrypted before persisting to `mcp_servers.json`.
- On load, values are decrypted in memory. The JSON file on disk never contains plaintext env.

**Process cleanup:**
- `MCPManager.shutdown()` iterates `self._procs` and sends SIGTERM → SIGKILL (same pattern as sidecar).
- Registered via `atexit.register(mcp_manager.shutdown)` in `main.py` at app startup.
- Electron sidecar stop already sends SIGTERM to the Python process, which triggers atexit → MCP children killed.

### 6.3 Chat Flow Change (`call_ai_api()` in `backend/main.py`)

Current flow:
```
build messages → httpx POST /chat/completions → return text
```

New flow:
```
build messages →
if model_supports_tools(settings.model):
    body["tools"] = registry.schemas()
httpx POST /chat/completions →
if response has tool_calls:
    for i in range(MAX_TOOL_ITERATIONS=5):
        for tc in response.tool_calls:
            result = await registry.execute(tc.function.name, json.loads(tc.function.arguments))
            messages.append({"role":"tool","tool_call_id":tc.id,"content":result})
        response = await httpx POST /chat/completions (with updated messages)
        if not response.tool_calls: break
    return final text
else:
    # fallback: existing [[GEN]] parsing
    return text
```

**Model capability detection:**
- A small heuristic: if `settings.model` contains known tool-incapable patterns (e.g. "gpt-3.5", "llama", "mistral" without tool variant), skip `tools` field and use `[[GEN]]` fallback.
- Alternatively: try with `tools` first; if the API returns 400 mentioning "tools", fall back to no-tools mode for that request. (Simpler: per-model config flag in Settings: `toolCalling: bool`, default true; user can toggle off.)
- **Decision:** Add `toolCalling: bool` to Settings (default true). When false, don't send `tools` field; LLM uses `[[GEN]]` tags. When true, send schemas; `[[GEN]]` parsing still runs on the final text as a safety net (some models emit tags even when tools are available).

### 6.4 WS Chat Streaming + Tool Events

Current WS `/ws/chat` streams 4-char chunks. When tool-calling is active, the backend will emit structured events:

```json
{"type": "tool_call_start", "tool": "mcp__fs__read_file", "args": {...}}
{"type": "tool_call_result", "tool": "mcp__fs__read_file", "result": "..."}
{"type": "chunk", "text": "..."}
{"type": "done", "usage": {...}}
```

Frontend `streamViaWebSocket()` handles `tool_call_start` / `tool_call_result` by showing a small inline card in the chat bubble: "🔧 Calling mcp__fs__read_file…" → "✅ read_file returned 1.2 KB".

### 6.5 REST Endpoints (new)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/mcp/servers` | List MCP server configs (env vars masked) |
| POST | `/api/mcp/servers` | Add server |
| PUT | `/api/mcp/servers/{id}` | Update server |
| DELETE | `/api/mcp/servers/{id}` | Remove server |
| POST | `/api/mcp/servers/{id}/test` | Connect + list tools (health check) |
| GET | `/api/mcp/servers/{id}/tools` | List available tools |
| POST | `/api/mcp/servers/{id}/enable` | Toggle enabled |
| POST | `/api/mcp/shutdown` | Kill all MCP child processes |

Existing `/api/tools/execute` approval gate is reused for MCP tools that require user approval (user configures per-server approval policy in the settings UI; default: auto-approve for media/file-gen native tools, ask for MCP tools).

### 6.6 Frontend

**Settings page — new section `sec-mcp`:**
- Server list (cards with name, transport badge, enabled toggle, test button, delete).
- "Add server" form: name, transport (STDIO/HTTP), command+args (STDIO) or URL+headers (HTTP), env vars (key-value editor, values password-masked), enabled checkbox.
- "Test connection" button → shows tool list on success.
- Settings persisted via `/api/mcp/servers` endpoints.

**Storage page — new section "MCP Servers":**
- Read-only list of saved servers with enable/disable toggle, "Edit in Settings" link, delete button.
- Mirrors the existing storage sections pattern (chats, agents, keys, etc.).

**Chat bubble — tool call cards:**
- Inline mini-card between message chunks: icon + tool name + status spinner → result preview (truncated).
- For media tools: reuses existing `renderGenInChat`-style rendering (image preview, file download link, audio player).

**`[[GEN]]` fallback path unchanged:** if model doesn't support tools, `parseGenTokens` / `processGenTokens` / `renderGenInChat` in `main.js` continue to work exactly as before.

### 6.7 `requirements.txt` additions

```
mcp>=1.0.0
cryptography>=42.0.0
```

---

## 7. Security

| Concern | Mitigation |
|---------|------------|
| MCP env vars on disk | Fernet-encrypted in `mcp_servers.json`; key in `mcp_key.key` (0600 permissions). |
| Tool execution sandbox | Native tools (media/file-gen) only write to `FILES_DIR` — no arbitrary FS. MCP tools execute in the MCP server's own process; AMT trusts the server boundary (user explicitly adds servers). |
| Approval gate | MCP tools default to approval-required unless user sets `auto_approve` per server in config. Reuses `/api/tools/execute` pattern. |
| Timeout | 30 s per MCP tool call. `asyncio.wait_for` with `TimeoutError` → error result. |
| Process cleanup | `atexit` + SIGTERM on sidecar stop. Orphaned MCP processes on crash: `mcp_key.key` and child PIDs logged; next startup reaps stale processes via `/proc` check (Linux) / `taskkill` (Windows). |
| Tool name collisions | `mcp__<server_id>__` prefix on all MCP tool names. Registry rejects duplicate names. |

---

## 8. Testing

| Test file | Coverage |
|-----------|----------|
| `tests/test_tool_registry.py` | Schema generation, native tool handlers (mocked media/filegen), execute dispatch, duplicate name rejection, MCP tool registration/unregistration. |
| `tests/test_mcp_manager.py` | Config CRUD + persistence, Fernet encryption round-trip, STDIO connect (mocked subprocess), HTTP connect (mocked httpx), tool listing, call_tool timeout, shutdown kills children, health check. |
| `tests/test_chat_tool_calls.py` | `call_ai_api()` with `toolCalling=true`: mock LLM returning `tool_calls`, verify registry execution + re-call loop + `tool` message appending. Mock LLM returning no tool_calls: verify fallback text path. |
| `tests/test_mcp_endpoints.py` | REST CRUD endpoints, test connection, enable/disable, shutdown. |
| Frontend: `tests/frontend/tool-cards.spec.js` (node) | Parse `tool_call_start`/`tool_call_result` WS events, render card DOM. |

---

## 9. Phasing

| Phase | Deliverable | Est. |
|-------|-------------|------|
| **P1: Tool Registry** | `tool_registry.py`, native tools, `call_ai_api()` tool-calling loop, `toolCalling` settings flag, WS tool events, frontend tool cards. `[[GEN]]` fallback intact. | ~1.5 d |
| **P2: MCP Manager** | `mcp_manager.py` (STDIO + HTTP), Fernet env encryption, REST endpoints, process cleanup (atexit + Electron hook). | ~1.5 d |
| **P3: MCP UI** | `sec-mcp` settings section, storage section, test-connection flow, enable/disable, delete. | ~1 d |
| **P4: Tests + Polish** | All test files, edge cases, doc updates, `requirements.txt`, PyInstaller spec update. | ~0.5 d |

Total: ~4.5 d. Phases are independent enough to ship P1 without P2/P3 if needed.

---

## 10. Builder Notes (Resolved During Review)

### B1. `call_ai_api()` tool-calling loop placement
The tool-calling loop goes **inside the existing `for attempt in range(max_attempts)` retry loop**, right after the successful `response.json()` parse (line ~1320). The loop must:
1. Check if `data["choices"][0]["message"]` has a `tool_calls` key.
2. If yes: execute each tool call via registry, append `{"role": "assistant", "tool_calls": [...]}` + `{"role": "tool", ...}` messages to `messages`, then re-POST to the same URL with updated messages (no `tools` field needed on re-call — some providers require it on every call, so include it).
3. The `finish_reason == "length"` continuation logic (line 1327) must NOT fire when `tool_calls` are present — check `finish_reason == "tool_calls"` first.
4. Max 5 tool-calling iterations. Each iteration uses a fresh `httpx.AsyncClient` (or reuses the same one from the outer `async with`).
5. If any tool call returns an error, the error string is appended as the `tool` result so the LLM can react to it.

### B2. `settings.toolCalling` flag
Add to the `Settings` pydantic model (line ~216): `toolCalling: bool = True`. When `True`, the `request_body` dict gets `"tools": registry.schemas()` appended. When `False`, skip tools entirely (existing `[[GEN]]` path). The flag is persisted in `settings.json` and exposed in the frontend settings UI.

### B3. `MEDIA_CAPABILITY` block conditional
When `toolCalling` is `True` AND the model supports tools, **omit** the `MEDIA_CAPABILITY` block from the system prompt (lines 1111-1200). The LLM will use native `tool_calls` instead of `[[GEN]]` tags. When `toolCalling` is `False`, include the block as-is. This prevents double-triggering (LLM emitting both tags and tool_calls).

### B4. WS streaming with tool calls
The `/ws/chat` endpoint (line ~3516) currently streams 4-char chunks from `call_ai_api()`'s return. With tool-calling, the WS handler needs to emit intermediate events. **Design:**
- `call_ai_api()` returns `{"text": str, "usage": dict, "tool_events": list[dict]}`. Each event is `{"type": "tool_call_start"|"tool_call_result", "tool": name, "args": obj?, "result": str?}`.
- WS handler iterates `tool_events` and sends each as a WS message before the final `done` event.
- REST `/api/chat` response includes `tool_events` in the JSON (frontend can show them on the next render).
- For streaming providers that return `tool_calls` in the final chunk (not streamed), the WS just waits for the complete response, emits tool events, then sends text chunks.

### B5. `generate_file` tool handler
`filegen.generate_file(filetype, content, title, lang)` returns `(bytes, filename)`. The tool handler must:
1. Call `generate_file()`.
2. Save bytes to `FILES_DIR` via `_save_media_b64(base64.b64encode(bytes).decode())` → `stored_name`.
3. Return JSON: `{"stored_name": stored_name, "filename": filename, "preview": preview_html(bytes, filetype)[:500]}`.
4. The LLM sees the JSON string; the frontend renders the file card using `stored_name` (same as `[[GEN:file]]` path).

### B6. `generate_image/video/audio` tool handlers
Each calls the corresponding `media.py` function with args from the LLM's `tool_call.arguments` (JSON-parsed). The media functions return a flat dict (with `b64` or `url`). Handler wraps: `{"type": "media", "kind": "image|video|audio", "data": result}`. Frontend renders the media inline (reuse `renderGenInChat`-style DOM).

### B7. MCP tool approval gate
Native media/file tools: **auto-approved** (they only write to `FILES_DIR`). MCP tools: approval depends on the server's `auto_approve` config field. When approval is needed, the tool result is `{"status": "pending_approval", "tool": name, "args": args}` and the WS emits a `tool_approval_required` event. Frontend shows an "Approve?" button; user clicks → POST `/api/tools/execute` with `approved: true` → backend re-executes and updates the WS. **Simplification for P1:** skip the approval UI; MCP tools are auto-approved if the server's `auto_approve` is true, otherwise the tool call is rejected with an error string. Full approval UX is P3 polish.

### B8. `mcp` SDK PyInstaller concerns
The `mcp` package (official SDK) has data files that PyInstaller can miss. Add to `setup.py` / PyInstaller spec:
```python
--collect-data mcp
--collect-all mcp
```
Test the build in P4.

### B9. `MCPManager` lifecycle
- On app startup (`main.py` `lifespan` or module import): load `mcp_servers.json`, decrypt env vars, but **do NOT auto-connect** servers. Connect lazily when the first tool call for that server arrives, or when the user clicks "Test" in settings.
- `shutdown()` is called via `atexit` and also explicitly from a new `/api/mcp/shutdown` endpoint (called by Electron `before-quit` before stopping the sidecar, to ensure clean process kill).
- Actually: Electron's `before-quit` → `stopSidecar()` sends SIGTERM to the Python process. Python's `atexit` fires on SIGTERM → `MCPManager.shutdown()` kills child processes. No explicit Electron hook needed beyond what's already there.

### B10. `mcp_servers.json` schema
```json
{
  "servers": [
    {
      "id": "fs",
      "name": "Filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-filesystem", "/home/user/projects"],
      "url": null,
      "headers": {},
      "env": {"API_KEY": "<fernet-encrypted>"},
      "enabled": true,
      "auto_approve": false
    }
  ]
}
```
`id` is a slug (used in tool name prefix). `env` values are Fernet-encrypted on disk; `url`/`command` are plaintext.

### B11. Tool name prefix collision
If a user adds two MCP servers both exposing a tool named `read_file`, the names become `mcp__fs1__read_file` and `mcp__fs2__read_file` — no collision. The `id` field guarantees uniqueness. Registry rejects duplicate `mcp__<id>__<tool>` names at registration time.

### B12. Frontend `sec-mcp` settings section
Add to the settings sub-nav in `home.html` (after `sec-media`, before `sec-voice`):
```html
<div class="sec-item" data-sec="sec-mcp" onclick="showSettingsPage('sec-mcp')">
  <span class="sec-icon">🔌</span><span>MCP</span>
</div>
```
In `main.js`, `showSettingsPage('sec-mcp')` loads `/api/mcp/servers`, renders the server list, shows the add/edit form. The form has: name, transport (radio: STDIO/HTTP), command+args (STDIO) or URL+headers (HTTP), env var key-value editor, enabled checkbox, auto_approve checkbox. "Test connection" button calls `/api/mcp/servers/{id}/test` and shows the tool list.

### B13. Storage page MCP section
In `renderStorageInteractive` (line ~3838 in `main.js`), add a new section:
```js
{ id: "mcp", title: "MCP Servers", icon: "🔌", items: mcpServers, itemActions: [edit, enable, disable, delete] }
```
Each item shows: name, transport badge, tool count, status (connected/disconnected). "Edit" navigates to `sec-mcp` settings with that server pre-selected. "Enable/Disable" toggles via `/api/mcp/servers/{id}/enable`. "Delete" removes via `/api/mcp/servers/{id}`.

### B14. What's left for the builder (open decisions)
- Fernet key rotation: out of scope, single key for now.
- MCP `auto_approve` granularity: per-server only in P1; per-tool is P3 polish.
- WS `tool_approval_required` event: deferred to P3. P1 auto-approves or rejects.
- PyInstaller `mcp` data files: verify in P4 build test.
- Windows process tree kill: use `taskkill /F /T /PID <pid>` in `MCPManager.shutdown()` on Windows.

---

## 12. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| LLM model doesn't support `tools` field and returns 400 | Medium | `toolCalling` flag in Settings; user can toggle off. Also: catch 400 on first tools call, log warning, retry without tools for that request. |
| MCP SDK `mcp` package PyInstaller issues | Low | Add `mcp` to PyInstaller hidden imports; test build in P4. |
| STDIO MCP server crashes mid-conversation | Low | `MCPManager.call_tool` catches process exit, returns error string; server marked `disconnected` in health check; user can reconnect. |
| Tool-calling loop runs out of context (5 iterations × large tool results) | Low | Max 5 iterations; tool results truncated to 4 KB each; LLM sees error if truncated. |
| `[[GEN]]` and native tools both fire (model emits tags even with tools) | Low | `MEDIA_CAPABILITY` block omitted when `toolCalling=true`. `[[GEN]]` parser still runs on final text as safety net; tokens are stripped from text. |
