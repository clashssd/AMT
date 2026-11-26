# AMT Native Tool Calling + MCP Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native LLM tool-calling (OpenAI `tools`/`tool_calls`) with a unified Tool Registry and MCP server integration (STDIO + HTTP) to AMT, while preserving the `[[GEN]]` tag fallback for tool-incapable models.

**Architecture:** A new `ToolRegistry` module holds tool schemas and dispatches execution. A new `MCPManager` module manages external MCP server connections (subprocess STDIO or HTTP), encrypts env vars with Fernet, and exposes CRUD + lifecycle REST endpoints. `call_ai_api()` gains a post-response tool-calling loop that executes `tool_calls` via the registry and re-calls the LLM. The frontend gets a `sec-mcp` settings section, a storage-page MCP list, and inline tool-call cards in chat.

**Tech Stack:** Python 3.10+, FastAPI, httpx, `mcp` (official SDK), `cryptography` (Fernet), vanilla JS frontend, Electron shell.

**Spec:** `docs/superpowers/specs/2026-11-26-amt-tool-calling-mcp-design.md`

## Global Constraints

- LLM API is OpenAI-compatible; `tools` field is only sent when `settings.toolCalling` is `True`.
- `MEDIA_CAPABILITY` prompt block is omitted when `toolCalling=True` (prevents double-triggering with native tools).
- `[[GEN]]` tag parsing in the frontend is **never removed** — it's the fallback for non-tool models.
- MCP tool names are prefixed `mcp__<server_id>__<tool_name>` to avoid collisions.
- MCP tool calls have a 30-second timeout via `asyncio.wait_for`.
- Tool results are truncated to 4 KB before being appended to the LLM context.
- MCP env vars are Fernet-encrypted on disk; key lives in `mcp_key.key` alongside `mcp_servers.json`.
- Native media/file tools are auto-approved (they only write to `FILES_DIR`).
- MCP tools default to approval-required unless the server's `auto_approve` is `True`.
- PyInstaller: add `--collect-all mcp` to the spec (verify in P4).
- `MAX_TOOL_ITERATIONS = 5` (hard cap on the tool-calling loop).
- `TOOL_RESULT_MAX_BYTES = 4096` (truncation cap per tool result).

## Review Focus

1. **Model returns 400 on `tools` field** — a tool-incapable model or provider that rejects `tools` must not crash the chat; the code should log a warning and retry without tools for that request.
2. **MCP server subprocess exits mid-conversation** — `call_tool` must catch the process death, return an error string, and mark the server disconnected in health checks.
3. **Fernet key missing on first run** — `mcp_key.key` doesn't exist yet; `MCPManager.__init__` must generate it with 0600 permissions.
4. **Duplicate tool name registration** — two MCP servers exposing the same tool name must not overwrite each other; the registry rejects duplicates at registration time.
5. **Tool-calling loop exhausts context** — 5 iterations × large results; tool results must be truncated to 4 KB and the LLM must see a truncation notice.

---

### Task 1: Tool Registry Module

**Files:**
- Create: `backend/ai_engine/tool_registry.py`
- Create: `tests/test_tool_registry.py`

**Interfaces:**
- Consumes: `media.generate_image()`, `media.generate_video()`, `media.generate_audio()`, `filegen.generate_file()`, `filegen.preview_html()` from existing modules
- Produces:
  - `ToolDef` dataclass: `name: str, description: str, parameters: dict, handler: Callable, source: str`
  - `ToolRegistry` class with methods:
    - `register(tool: ToolDef) -> None`
    - `unregister_prefix(prefix: str) -> int` (returns count removed)
    - `schemas() -> list[dict]` (OpenAI format: `[{"type":"function","function":{"name","description","parameters"}}]`)
    - `async execute(name: str, args: dict) -> str` (returns JSON string; raises `ToolExecutionError`)
    - `has(name: str) -> bool`
  - `ToolExecutionError` exception
  - `register_native_tools(registry: ToolRegistry) -> None` (registers the 4 native tools)
  - `tool_registry` module-level singleton instance

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_registry.py
import pytest, json, asyncio

def test_tool_def_dataclass():
    from ai_engine.tool_registry import ToolDef
    t = ToolDef(name="x", description="d", parameters={}, handler=None, source="native")
    assert t.name == "x" and t.source == "native"

def test_register_and_schemas():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    reg.register(ToolDef(name="echo", description="echoes", parameters={"type":"object","properties":{"text":{"type":"string"}}}, handler=None, source="native"))
    schemas = reg.schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "echo"

def test_duplicate_name_rejected():
    from ai_engine.tool_registry import ToolRegistry, ToolDef, ToolExecutionError
    reg = ToolRegistry()
    reg.register(ToolDef(name="dup", description="a", parameters={}, handler=None, source="native"))
    with pytest.raises(ToolExecutionError):
        reg.register(ToolDef(name="dup", description="b", parameters={}, handler=None, source="native"))

def test_unregister_prefix():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    reg.register(ToolDef(name="mcp__fs__read", description="r", parameters={}, handler=None, source="mcp:fs"))
    reg.register(ToolDef(name="mcp__fs__write", description="w", parameters={}, handler=None, source="mcp:fs"))
    reg.register(ToolDef(name="native_tool", description="n", parameters={}, handler=None, source="native"))
    removed = reg.unregister_prefix("mcp__fs")
    assert removed == 2
    assert reg.has("native_tool")
    assert not reg.has("mcp__fs__read")

def test_execute_dispatch():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    async def echo_handler(text: str) -> str:
        return json.dumps({"echo": text})
    reg.register(ToolDef(name="echo", description="e", parameters={"type":"object","properties":{"text":{"type":"string"}}}, handler=echo_handler, source="native"))
    result = asyncio.run(reg.execute("echo", {"text": "hi"}))
    assert json.loads(result)["echo"] == "hi"

def test_execute_unknown_tool():
    from ai_engine.tool_registry import ToolRegistry, ToolExecutionError
    reg = ToolRegistry()
    with pytest.raises(ToolExecutionError):
        asyncio.run(reg.execute("nonexistent", {}))

def test_execute_handler_error():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    async def bad_handler(**kw) -> str:
        raise ValueError("boom")
    reg.register(ToolDef(name="bad", description="b", parameters={}, handler=bad_handler, source="native"))
    result = asyncio.run(reg.execute("bad", {}))
    assert "error" in result.lower() or "boom" in result

def test_register_native_tools():
    from ai_engine.tool_registry import ToolRegistry, register_native_tools
    reg = ToolRegistry()
    register_native_tools(reg)
    for name in ("generate_image", "generate_video", "generate_audio", "generate_file"):
        assert reg.has(name), f"missing native tool: {name}"
    schemas = reg.schemas()
    assert len(schemas) == 4
    for s in schemas:
        assert s["type"] == "function"
        assert s["function"]["parameters"]["type"] == "object"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_registry.py -v`
Expected: All tests FAIL with `ModuleNotFoundError` or `ImportError` for `ai_engine.tool_registry`.

- [ ] **Step 3: Implement `tool_registry.py`**

Create `backend/ai_engine/tool_registry.py`:

```python
# backend/ai_engine/tool_registry.py
from __future__ import annotations
import json, logging, os, traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# --- Tuning constants (from spec) ---
MAX_TOOL_ITERATIONS = 5
TOOL_RESULT_MAX_BYTES = 4096

class ToolExecutionError(Exception):
    pass

@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict      # JSON Schema (OpenAI function-calling format)
    handler: Optional[Callable]  # async fn(**kwargs) -> str (JSON-serializable)
    source: str = "native"  # "native" | "mcp:<server_id>"

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ToolExecutionError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def unregister_prefix(self, prefix: str) -> int:
        to_remove = [k for k in self._tools if k.startswith(prefix)]
        for k in to_remove:
            del self._tools[k]
        return len(to_remove)

    def schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    async def execute(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"Unknown tool: {name}")
        try:
            result = await tool.handler(**args)
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            if len(result) > TOOL_RESULT_MAX_BYTES:
                result = result[:TOOL_RESULT_MAX_BYTES] + "\n...[truncated]"
            return result
        except ToolExecutionError:
            raise
        except Exception as e:
            log.warning("Tool %s failed: %s\n%s", name, e, traceback.format_exc())
            return json.dumps({"error": str(e)}, ensure_ascii=False)


# --- Native tool handlers ---

def _files_dir() -> str:
    return os.environ.get("AMT_FILES_DIR", os.path.join(os.path.dirname(__file__), "..", "FILES_DIR"))

async def _handle_generate_image(prompt: str, size: str = "1:1", model: str = "", ref_image_b64: str = "") -> str:
    from ai_engine import media
    cfg = {"prompt": prompt, "size": size, "model": model, "ref_image_b64": ref_image_b64}
    result = media.generate_image(cfg)
    return json.dumps(result, ensure_ascii=False)

async def _handle_generate_video(prompt: str, aspect_ratio: str = "9:16", duration: int = 5, model: str = "") -> str:
    from ai_engine import media
    cfg = {"prompt": prompt, "aspect_ratio": aspect_ratio, "duration": duration, "model": model}
    result = media.generate_video(cfg)
    return json.dumps(result, ensure_ascii=False)

async def _handle_generate_audio(text: str, voice_id: str = "", model: str = "") -> str:
    from ai_engine import media
    cfg = {"prompt": text, "voice_id": voice_id, "model": model}
    result = media.generate_audio(cfg)
    return json.dumps(result, ensure_ascii=False)

async def _handle_generate_file(filetype: str, content: str, title: str = "", lang: str = "") -> str:
    from ai_engine import filegen
    import base64
    data, filename = filegen.generate_file(filetype, content, title, lang)
    b64 = base64.b64encode(data).decode()
    # Save to FILES_DIR via the same helper main.py uses
    files_dir = _files_dir()
    os.makedirs(files_dir, exist_ok=True)
    import uuid
    stored_name = f"{uuid.uuid4().hex[:12]}_{filename}"
    with open(os.path.join(files_dir, stored_name), "wb") as f:
        f.write(data)
    preview = ""
    try:
        preview = filegen.preview_html(data, filetype)[:500]
    except Exception:
        pass
    return json.dumps({"stored_name": stored_name, "filename": filename, "preview": preview}, ensure_ascii=False)


def register_native_tools(registry: ToolRegistry) -> None:
    registry.register(ToolDef(
        name="generate_image",
        description="Generate an image from a text prompt. Returns base64 data or URL.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for the image"},
                "size": {"type": "string", "description": "Aspect ratio, e.g. 1:1, 16:9", "default": "1:1"},
                "model": {"type": "string", "description": "Optional model override"},
                "ref_image_b64": {"type": "string", "description": "Optional reference image (base64) for style transfer"},
            },
            "required": ["prompt"],
        },
        handler=_handle_generate_image,
        source="native",
    ))
    registry.register(ToolDef(
        name="generate_video",
        description="Generate a video from a text prompt. Returns URL or task ID for async polling.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for the video"},
                "aspect_ratio": {"type": "string", "description": "e.g. 9:16, 16:9", "default": "9:16"},
                "duration": {"type": "integer", "description": "Duration in seconds", "default": 5},
                "model": {"type": "string", "description": "Optional model override"},
            },
            "required": ["prompt"],
        },
        handler=_handle_generate_video,
        source="native",
    ))
    registry.register(ToolDef(
        name="generate_audio",
        description="Generate audio (speech-to-text or text-to-speech) from input. Returns base64 data or URL.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to synthesize"},
                "voice_id": {"type": "string", "description": "Optional voice ID"},
                "model": {"type": "string", "description": "Optional model override"},
            },
            "required": ["text"],
        },
        handler=_handle_generate_audio,
        source="native",
    ))
    registry.register(ToolDef(
        name="generate_file",
        description="Generate a document file (docx, xlsx, pptx, pdf, py, md, html, json, csv, txt, code) from content. Returns stored file reference.",
        parameters={
            "type": "object",
            "properties": {
                "filetype": {"type": "string", "description": "File type: docx, xlsx, pptx, pdf, py, md, html, json, csv, txt, code"},
                "content": {"type": "string", "description": "The document content or structured data"},
                "title": {"type": "string", "description": "Document title"},
                "lang": {"type": "string", "description": "Language code (e.g. ru, en)"},
            },
            "required": ["filetype", "content"],
        },
        handler=_handle_generate_file,
        source="native",
    ))


# Module-level singleton
tool_registry = ToolRegistry()
register_native_tools(tool_registry)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tool_registry.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ai_engine/tool_registry.py tests/test_tool_registry.py
git commit -m "feat: add Tool Registry with native media/file tools"
```

---

### Task 2: `call_ai_api()` Tool-Calling Loop + Settings Flag

**Files:**
- Modify: `backend/main.py` (Settings model ~line 216, `call_ai_api()` ~lines 556-1544, request_body construction ~line 1244, MEDIA_CAPABILITY block ~lines 1111-1199)
- Create: `tests/test_chat_tool_calls.py`

**Interfaces:**
- Consumes: `tool_registry` singleton from `ai_engine/tool_registry.py` (Task 1)
- Produces:
  - `Settings.toolCalling: bool` (default `True`) — persisted in `settings.json`
  - `call_ai_api()` return type expanded: `{"text": str, "usage": dict, "tool_events": list[dict]}` where each event is `{"type": "tool_call_start"|"tool_call_result", "tool": str, "args": dict?, "result": str?}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_tool_calls.py
import pytest, json, httpx, asyncio
from unittest.mock import patch, AsyncMock

def test_settings_has_toolcalling_flag(tmp_backend):
    import main
    from main import Settings
    s = Settings(**tmp_backend["settings"])
    assert hasattr(s, "toolCalling")
    assert s.toolCalling is True

def test_request_body_includes_tools_when_enabled(tmp_backend, monkeypatch):
    import main
    captured = {}

    async def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json", {})
        resp = httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
        return resp

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    assert "tools" in captured["body"]
    assert len(captured["body"]["tools"]) >= 4  # native tools

def test_request_body_omits_tools_when_disabled(tmp_backend, monkeypatch):
    import main
    captured = {}

    async def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json", {})
        resp = httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
        return resp

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = False
    result = asyncio.run(main.call_ai_api("hi", [], settings))
    assert "tools" not in captured["body"]

def test_tool_calls_trigger_execution_loop(tmp_backend, monkeypatch):
    import main

    responses = iter([
        # First response: LLM wants to call a tool
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "a cat"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        # Second response: LLM gives final answer
        {
            "choices": [{"message": {"role": "assistant", "content": "Here is your cat image."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
    ])

    call_count = 0

    async def fake_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        data = next(responses)
        return httpx.Response(200, json=data)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    # Mock the native tool handler so it doesn't hit the network
    async def fake_image_handler(prompt, **kw):
        return json.dumps({"type": "media", "kind": "image", "data": {"b64": "fake_b64"}})

    import ai_engine.tool_registry as tr
    monkeypatch.setattr(tr.tool_registry.get("generate_image").handler, fake_image_handler, raising=False)
    # Re-register with the mock handler
    from ai_engine.tool_registry import ToolDef
    tr.tool_registry._tools["generate_image"] = ToolDef(
        name="generate_image", description="mock", parameters={},
        handler=fake_image_handler, source="native",
    )

    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("make a cat image", [], settings))

    assert call_count == 2  # two LLM calls (tool call + final)
    assert "tool_events" in result
    assert len(result["tool_events"]) >= 2  # start + result events
    assert result["text"] == "Here is your cat image."

def test_tool_call_error_appended(tmp_backend, monkeypatch):
    import main
    import ai_engine.tool_registry as tr

    responses = iter([
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "nonexistent_tool", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "Tool failed, sorry."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
    ])

    call_count = 0
    async def fake_post(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=next(responses))

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    settings = main.Settings(**tmp_backend["settings"])
    settings.toolCalling = True
    result = asyncio.run(main.call_ai_api("test error", [], settings))
    assert call_count == 2
    # The tool event should contain an error
    error_events = [e for e in result["tool_events"] if e["type"] == "tool_call_result" and "error" in e.get("result", "").lower()]
    assert len(error_events) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_tool_calls.py -v`
Expected: FAIL — `Settings` has no `toolCalling` attribute; `call_ai_api` doesn't handle tool_calls.

- [ ] **Step 3: Add `toolCalling` to Settings model and modify `call_ai_api()`**

In `backend/main.py`:

1. **Settings model (~line 216):** Add `toolCalling: bool = True` field to the pydantic `Settings` class.

2. **Import at top of `main.py`:** Add `from ai_engine.tool_registry import tool_registry` (after existing `ai_engine` imports).

3. **MEDIA_CAPABILITY block (~lines 1111-1199):** Wrap the block so it's only appended to the system prompt when `settings.toolCalling` is `False`:
```python
if not settings.toolCalling:
    combined_prompt += MEDIA_CAPABILITY
```

4. **Request body construction (~line 1244):** After building `request_body`, add:
```python
if settings.toolCalling:
    request_body["tools"] = tool_registry.schemas()
```

5. **Post-response tool-calling loop (~line 1320, after `data = response.json()` and extracting `text`):** Before the `finish_reason == "length"` continuation, insert:
```python
tool_events: list[dict] = []
msg = data["choices"][0]["message"]

if settings.toolCalling and msg.get("tool_calls"):
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Append the assistant message with tool_calls to history
        assistant_msg = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        for tc in msg["tool_calls"]:
            tc_name = tc["function"]["name"]
            try:
                tc_args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                tc_args = {}
            tool_events.append({"type": "tool_call_start", "tool": tc_name, "args": tc_args})

            try:
                tc_result = await tool_registry.execute(tc_name, tc_args)
            except Exception as e:
                tc_result = json.dumps({"error": str(e)}, ensure_ascii=False)

            tool_events.append({"type": "tool_call_result", "tool": tc_name, "result": tc_result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tc_result,
            })

        # Re-call LLM with updated messages
        resp2 = await client.post(f"{settings.effective_base_url}/chat/completions", json=request_body)
        if resp2.status_code == 400 and "tools" in resp2.text:
            log.warning("Provider rejected tools field, disabling for this request")
            request_body.pop("tools", None)
            resp2 = await client.post(f"{settings.effective_base_url}/chat/completions", json=request_body)
        data = resp2.json()
        msg = data["choices"][0]["message"]
        if not msg.get("tool_calls"):
            break

if not settings.toolCalling or not msg.get("tool_calls"):
    text = msg.get("content") or ""
else:
    text = msg.get("content") or ""
```

6. **Return value (~line 1544):** Change from `return {"text": text, "usage": usage}` to:
```python
return {"text": text, "usage": usage, "tool_events": tool_events}
```

7. **400 fallback:** When the first `tools`-enabled call returns 400 mentioning "tools", log a warning, remove `tools` from `request_body`, and retry without tools (one-shot fallback per request).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_tool_calls.py tests/test_tool_registry.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_chat_tool_calls.py
git commit -m "feat: add tool-calling loop to call_ai_api with toolCalling settings flag"
```

---

### Task 3: WS Chat Tool Events + REST `tool_events`

**Files:**
- Modify: `backend/main.py` (WS `/ws/chat` handler ~line 3516, REST `/api/chat` handler ~line 1572)

**Interfaces:**
- Consumes: `call_ai_api()` returning `{"text", "usage", "tool_events"}` (Task 2)
- Produces:
  - WS events: `{"type": "tool_call_start", "tool": ..., "args": ...}` and `{"type": "tool_call_result", "tool": ..., "result": ...}` sent before text chunks
  - REST `/api/chat` response includes `"tool_events": [...]` in the JSON body

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_tool_calls.py (append to existing file)

def test_ws_chat_emits_tool_events(tmp_backend, monkeypatch):
    import main, json

    # Mock call_ai_api to return tool events
    mock_result = {
        "text": "final answer",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "tool_events": [
            {"type": "tool_call_start", "tool": "generate_image", "args": {"prompt": "cat"}},
            {"type": "tool_call_result", "tool": "generate_image", "result": '{"type":"media"}'},
        ],
    }

    async def fake_ws_call_ai_api(*a, **kw):
        return mock_result

    monkeypatch.setattr(main, "call_ai_api", fake_ws_call_ai_api)

    from starlette.testclient import TestClient
    c = TestClient(main.app)
    with c.websocket_connect("/ws/chat") as ws:
        ws.send_json({
            "message": "make a cat",
            "history": [],
            "settings": tmp_backend["settings"],
            "agent_id": "",
            "extra_skills": "",
            "core_agents": [],
            "sysinteraction": False,
            "key_id": "",
            "systemPromptOverride": "",
            "attachments": [],
        })
        # Collect all messages until done
        messages = []
        while True:
            data = ws.receive_text()
            msg = json.loads(data)
            messages.append(msg)
            if msg.get("type") == "done":
                break

        # Verify tool events were sent before text chunks
        tool_event_types = [m for m in messages if m.get("type") in ("tool_call_start", "tool_call_result")]
        assert len(tool_event_types) == 2
        # Verify done event still last
        assert messages[-1]["type"] == "done"

def test_rest_chat_returns_tool_events(tmp_backend, monkeypatch):
    import main, json

    mock_result = {
        "text": "final answer",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "tool_events": [
            {"type": "tool_call_start", "tool": "generate_audio", "args": {"text": "hello"}},
            {"type": "tool_call_result", "tool": "generate_audio", "result": '{"type":"media"}'},
        ],
    }

    async def fake_call_ai_api(*a, **kw):
        return mock_result

    monkeypatch.setattr(main, "call_ai_api", fake_call_ai_api)

    from starlette.testclient import TestClient
    c = TestClient(main.app)
    resp = c.post("/api/chat", json={
        "message": "say hello",
        "history": [],
        "settings": tmp_backend["settings"],
        "agent_id": "",
        "extra_skills": "",
        "core_agents": [],
        "sysinteraction": False,
        "key_id": "",
        "systemPromptOverride": "",
        "attachments": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "tool_events" in data
    assert len(data["tool_events"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_tool_calls.py::test_ws_chat_emits_tool_events tests/test_chat_tool_calls.py::test_rest_chat_returns_tool_events -v`
Expected: FAIL — WS doesn't emit tool events; REST doesn't include `tool_events`.

- [ ] **Step 3: Modify WS and REST handlers**

In `backend/main.py`:

1. **WS `/ws/chat` handler (~line 3516):** After `call_ai_api()` returns, before streaming text chunks, iterate `result.get("tool_events", [])` and send each as a WS JSON message:
```python
for ev in result.get("tool_events", []):
    await ws.send_json(ev)  # {"type": "tool_call_start"|"tool_call_result", ...}
```

2. **REST `/api/chat` handler (~line 1572):** Include `tool_events` in the response:
```python
return {
    "response": result["text"],
    "usage": result["usage"],
    "tool_events": result.get("tool_events", []),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_tool_calls.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_chat_tool_calls.py
git commit -m "feat: emit tool-call events via WS and include in REST response"
```

---

### Task 4: MCP Manager — Config, Encryption, CRUD

**Files:**
- Create: `backend/ai_engine/mcp_manager.py`
- Modify: `tests/conftest.py` (add `AMT_MCP_SERVERS_FILE` and `AMT_MCP_KEY_FILE` env vars to `tmp_backend`)
- Create: `tests/test_mcp_manager.py`
- Modify: `requirements.txt` (add `mcp`, `cryptography`)

**Interfaces:**
- Consumes: `cryptography.fernet.Fernet` for env var encryption
- Produces:
  - `MCPServerConfig` dataclass: `id, name, transport, command, args, url, headers, env, enabled, auto_approve`
  - `MCPManager` class:
    - `__init__(data_dir: str)` — loads `mcp_servers.json`, generates/loads Fernet key
    - `list_servers() -> list[MCPServerConfig]`
    - `add_server(cfg: MCPServerConfig) -> None`
    - `update_server(cfg: MCPServerConfig) -> None`
    - `remove_server(server_id: str) -> None`
    - `set_enabled(server_id: str, enabled: bool) -> None`
    - `get_server(server_id: str) -> MCPServerConfig | None`
  - `mcp_manager` module-level singleton (initialized lazily)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_manager.py
import pytest, json, os

def test_mcp_server_config_dataclass():
    from ai_engine.mcp_manager import MCPServerConfig
    cfg = MCPServerConfig(
        id="fs", name="Filesystem", transport="stdio",
        command="npx", args=["@modelcontextprotocol/server-filesystem", "/tmp"],
        url=None, headers={}, env={"API_KEY": "secret123"},
        enabled=True, auto_approve=False,
    )
    assert cfg.id == "fs"
    assert cfg.transport == "stdio"
    assert cfg.env["API_KEY"] == "secret123"

def test_mcp_manager_crud(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(tmp_backend["data_dir"])

    cfg = MCPServerConfig(
        id="fs", name="Filesystem", transport="stdio",
        command="npx", args=["test"],
        url=None, headers={}, env={"KEY": "val"},
        enabled=True, auto_approve=False,
    )
    mgr.add_server(cfg)

    servers = mgr.list_servers()
    assert len(servers) == 1
    assert servers[0].id == "fs"

    cfg.name = "Updated"
    mgr.update_server(cfg)
    updated = mgr.get_server("fs")
    assert updated.name == "Updated"

    mgr.set_enabled("fs", False)
    assert mgr.get_server("fs").enabled is False

    mgr.remove_server("fs")
    assert mgr.list_servers() == []

def test_env_var_encryption_roundtrip(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(tmp_backend["data_dir"])

    cfg = MCPServerConfig(
        id="enc", name="EncTest", transport="http",
        command="", args=[],
        url="http://localhost:3000", headers={},
        env={"SECRET": "top_secret_value"},
        enabled=True, auto_approve=True,
    )
    mgr.add_server(cfg)

    # Read raw JSON from disk — env values must be encrypted (not plaintext)
    servers_file = os.path.join(tmp_backend["data_dir"], "mcp_servers.json")
    with open(servers_file) as f:
        raw = json.load(f)
    stored_env = raw["servers"][0]["env"]
    assert stored_env["SECRET"] != "top_secret_value"
    assert "top_secret_value" not in json.dumps(raw)

    # Fresh manager instance loads and decrypts correctly
    mgr2 = MCPManager(tmp_backend["data_dir"])
    loaded = mgr2.get_server("enc")
    assert loaded.env["SECRET"] == "top_secret_value"

def test_fernet_key_created_with_permissions(tmp_backend):
    from ai_engine.mcp_manager import MCPManager
    mgr = MCPManager(tmp_backend["data_dir"])
    key_file = os.path.join(tmp_backend["data_dir"], "mcp_key.key")
    assert os.path.exists(key_file)
    # On Linux/macOS check 0600; on Windows skip permission check
    import platform
    if platform.system() != "Windows":
        mode = oct(os.stat(key_file).st_mode & 0o777)
        assert mode in ("0o600", "0o400"), f"key file permissions: {mode}"

def test_add_server_rejects_duplicate_id(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(tmp_backend["data_dir"])
    cfg1 = MCPServerConfig(id="x", name="A", transport="stdio", command="c", args=[], url=None, headers={}, env={}, enabled=True, auto_approve=False)
    cfg2 = MCPServerConfig(id="x", name="B", transport="http", command="", args=[], url="http://x", headers={}, env={}, enabled=True, auto_approve=False)
    mgr.add_server(cfg1)
    with pytest.raises(Exception):
        mgr.add_server(cfg2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_manager.py -v`
Expected: All tests FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Add env vars to conftest and implement `mcp_manager.py`**

In `tests/conftest.py`, add to the `tmp_backend` fixture:
```python
os.environ["AMT_MCP_SERVERS_FILE"] = str(tmp_path / "mcp_servers.json")
os.environ["AMT_MCP_KEY_FILE"] = str(tmp_path / "mcp_key.key")
```

Create `backend/ai_engine/mcp_manager.py`:

```python
# backend/ai_engine/mcp_manager.py
from __future__ import annotations
import json, logging, os, stat, platform
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from cryptography.fernet import Fernet

log = logging.getLogger(__name__)

SERVERS_FILE = "mcp_servers.json"
KEY_FILE = "mcp_key.key"

@dataclass
class MCPServerConfig:
    id: str
    name: str
    transport: str        # "stdio" | "http"
    command: str = ""
    args: list = field(default_factory=list)
    url: str = ""
    headers: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)
    enabled: bool = True
    auto_approve: bool = False

class MCPManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.servers_file = os.environ.get("AMT_MCP_SERVERS_FILE", os.path.join(data_dir, SERVERS_FILE))
        self.key_file = os.environ.get("AMT_MCP_KEY_FILE", os.path.join(data_dir, KEY_FILE))
        self._fkey = self._load_or_create_key()
        self.servers: dict[str, MCPServerConfig] = {}
        self._load()

    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return f.read()
        key = Fernet.generate_key()
        fd = os.open(self.key_file, os.O_WRONLY | os.O_CREAT, stat.S_IRWXU)  # 0600
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key

    def _encrypt_env(self, env: dict) -> dict:
        if not env:
            return {}
        f = Fernet(self._fkey)
        return {k: f.encrypt(v.encode()).decode() for k, v in env.items()}

    def _decrypt_env(self, env: dict) -> dict:
        if not env:
            return {}
        f = Fernet(self._fkey)
        return {k: f.decrypt(v.encode()).decode() for k, v in env.items()}

    def _load(self) -> None:
        if not os.path.exists(self.servers_file):
            return
        with open(self.servers_file) as fh:
            data = json.load(fh)
        for entry in data.get("servers", []):
            entry["env"] = self._decrypt_env(entry.get("env", {}))
            cfg = MCPServerConfig(**entry)
            self.servers[cfg.id] = cfg

    def _persist(self) -> None:
        servers = []
        for cfg in self.servers.values():
            d = asdict(cfg)
            d["env"] = self._encrypt_env(d.get("env", {}))
            servers.append(d)
        with open(self.servers_file, "w") as f:
            json.dump({"servers": servers}, f, indent=2, ensure_ascii=False)

    def list_servers(self) -> list[MCPServerConfig]:
        return list(self.servers.values())

    def get_server(self, server_id: str) -> Optional[MCPServerConfig]:
        return self.servers.get(server_id)

    def add_server(self, cfg: MCPServerConfig) -> None:
        if cfg.id in self.servers:
            raise ValueError(f"Server with id '{cfg.id}' already exists")
        self.servers[cfg.id] = cfg
        self._persist()

    def update_server(self, cfg: MCPServerConfig) -> None:
        if cfg.id not in self.servers:
            raise ValueError(f"Server with id '{cfg.id}' not found")
        self.servers[cfg.id] = cfg
        self._persist()

    def remove_server(self, server_id: str) -> None:
        if server_id not in self.servers:
            raise ValueError(f"Server with id '{server_id}' not found")
        del self.servers[server_id]
        self._persist()

    def set_enabled(self, server_id: str, enabled: bool) -> None:
        cfg = self.servers.get(server_id)
        if cfg is None:
            raise ValueError(f"Server with id '{server_id}' not found")
        cfg.enabled = enabled
        self._persist()


# Module-level singleton (initialized lazily in main.py)
mcp_manager: Optional[MCPManager] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_manager.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Add dependencies to requirements.txt and commit**

In `requirements.txt`, add:
```
mcp>=1.0.0
cryptography>=42.0.0
```

```bash
git add backend/ai_engine/mcp_manager.py tests/test_mcp_manager.py tests/conftest.py requirements.txt
git commit -m "feat: add MCP Manager with Fernet-encrypted env vars and CRUD"
```

---

### Task 5: MCP Manager — Connection Lifecycle + Tool Calls

**Files:**
- Modify: `backend/ai_engine/mcp_manager.py` (add connection management methods)

**Interfaces:**
- Consumes: `mcp` SDK (`mcp.client.stdio.stdio_client`, `mcp.client.streamable_http.streamable_http_client`, `mcp.types`)
- Produces (on `MCPManager`):
  - `async connect(server_id: str) -> None`
  - `async disconnect(server_id: str) -> None`
  - `async list_tools(server_id: str) -> list[dict]` — returns `[{"name": ..., "description": ..., "inputSchema": ...}]`
  - `async call_tool(server_id: str, tool: str, args: dict) -> str` — returns JSON string; 30s timeout
  - `async health(server_id: str) -> dict` — `{"status": "connected"|"disconnected"|"error", "message": str}`
  - `shutdown() -> None` — kills all child processes

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_manager.py (append)

import pytest, asyncio, json
from unittest.mock import patch, AsyncMock, MagicMock

def test_connect_stdio_mocked(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    async def run():
        mgr = MCPManager(tmp_backend["data_dir"])
        cfg = MCPServerConfig(
            id="mock", name="Mock", transport="stdio",
            command="echo", args=["hello"],
            url="", headers={}, env={},
            enabled=True, auto_approve=False,
        )
        mgr.add_server(cfg)

        # Mock the mcp SDK's stdio_client
        mock_client = AsyncMock()
        mock_client._session = AsyncMock()
        mock_client._session.list_tools = AsyncMock(return_value={"tools": [
            {"name": "test_tool", "description": "a test", "inputSchema": {"type": "object", "properties": {}}}
        ]})

        with patch("ai_engine.mcp_manager._stdio_client", return_value=mock_client):
            await mgr.connect("mock")

        assert "mock" in mgr._clients

        tools = await mgr.list_tools("mock")
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

        await mgr.disconnect("mock")
        assert "mock" not in mgr._clients

    asyncio.run(run())

def test_call_tool_timeout(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    async def run():
        mgr = MCPManager(tmp_backend["data_dir"])
        cfg = MCPServerConfig(id="slow", name="Slow", transport="http", command="", args=[], url="http://slow", headers={}, env={}, enabled=True, auto_approve=False)
        mgr.add_server(cfg)

        # Simulate a connected client whose call_tool hangs
        import asyncio as aio
        async def hanging_call_tool(name, args):
            await aio.sleep(60)

        mock_client = AsyncMock()
        mock_client._session = AsyncMock()
        mock_client._session.call_tool = AsyncMock(side_effect=hanging_call_tool)
        mgr._clients["slow"] = mock_client

        result = await mgr.call_tool("slow", "hang_tool", {})
        assert "timed out" in result.lower() or "timeout" in result.lower()

    asyncio.run(run())

def test_shutdown_kills_children(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    async def run():
        mgr = MCPManager(tmp_backend["data_dir"])
        # Simulate a connected STDIO client with a process
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_client = AsyncMock()
        mock_client._proc = mock_proc
        mgr._clients["proc1"] = mock_client
        mgr._procs["proc1"] = mock_proc

        mgr.shutdown()

        # SIGTERM should have been sent (or terminate called)
        mock_proc.terminate.assert_called()

    asyncio.run(run())

def test_health_check(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    async def run():
        mgr = MCPManager(tmp_backend["data_dir"])
        cfg = MCPServerConfig(id="h", name="H", transport="stdio", command="echo", args=[], url="", headers={}, env={}, enabled=True, auto_approve=False)
        mgr.add_server(cfg)

        health = await mgr.health("h")
        assert health["status"] in ("disconnected", "error")  # not connected yet

    asyncio.run(run())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_manager.py -v`
Expected: New tests FAIL — connection methods don't exist yet.

- [ ] **Step 3: Implement connection lifecycle in `mcp_manager.py`**

Add to `MCPManager` class:

```python
import asyncio, signal, subprocess, sys, time
from typing import Any, Optional as _Opt

# MCP SDK imports (deferred to avoid import errors when mcp not installed)
# from mcp.client.stdio import stdio_client, StdioServerParameters
# from mcp.client.streamable_http import streamable_http_client
# from mcp import ClientSession, types as mcp_types

def _stdio_client(self, cfg: MCPServerConfig):
    """Import and return mcp stdio_client context manager for the given config."""
    from mcp.client.stdio import stdio_client, StdioServerParameters
    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args,
        env={**os.environ, **cfg.env},
    )
    return stdio_client(params)

def _http_client(self, cfg: MCPServerConfig):
    """Import and return mcp streamable_http_client context manager."""
    from mcp.client.streamable_http import streamable_http_client
    return streamable_http_client(cfg.url, headers=cfg.headers)

async def connect(self, server_id: str) -> None:
    cfg = self.servers.get(server_id)
    if cfg is None:
        raise ValueError(f"Server '{server_id}' not found")
    if server_id in self._clients:
        return  # already connected

    if cfg.transport == "stdio":
        cm = self._stdio_client(cfg)
        ctx = cm()
        read, write, session = await __aenter__(ctx)
        client_obj = type("_MCPClient", (), {
            "_session": session,
            "_read": read,
            "_write": write,
            "_ctx": ctx,
            "_proc": None,  # will be set if we can get it
        })()
        self._clients[server_id] = client_obj
    elif cfg.transport == "http":
        cm = self._http_client(cfg)
        ctx = cm()
        read, write, session = await __aenter__(ctx)
        client_obj = type("_MCPClient", (), {
            "_session": session,
            "_ctx": ctx,
        })()
        self._clients[server_id] = client_obj

    log.info("MCP server '%s' connected (%s)", server_id, cfg.transport)

async def disconnect(self, server_id: str) -> None:
    client_obj = self._clients.pop(server_id, None)
    if client_obj is None:
        return
    try:
        await __aexit__(client_obj._ctx, None, None, None)
    except Exception as e:
        log.warning("MCP disconnect '%s' error: %s", server_id, e)
    self._procs.pop(server_id, None)

async def list_tools(self, server_id: str) -> list[dict]:
    client_obj = self._clients.get(server_id)
    if client_obj is None:
        await self.connect(server_id)
        client_obj = self._clients[server_id]
    result = await client_obj._session.list_tools()
    return [
        {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema or {}}
        for t in result.tools
    ]

async def call_tool(self, server_id: str, tool: str, args: dict) -> str:
    client_obj = self._clients.get(server_id)
    if client_obj is None:
        await self.connect(server_id)
        client_obj = self._clients[server_id]

    try:
        result = await asyncio.wait_for(
            client_obj._session.call_tool(tool, args),
            timeout=30.0,
        )
        # MCP SDK returns a result object; extract text content
        if hasattr(result, "content") and result.content:
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
            return json.dumps({"result": "\n".join(parts)}, ensure_ascii=False)
        return json.dumps({"result": str(result)}, ensure_ascii=False)
    except asyncio.TimeoutError:
        return json.dumps({"error": "MCP tool call timed out after 30s"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

async def health(self, server_id: str) -> dict:
    if server_id in self._clients:
        return {"status": "connected", "message": "OK"}
    cfg = self.servers.get(server_id)
    if cfg is None:
        return {"status": "error", "message": "Server not found"}
    return {"status": "disconnected", "message": "Not connected"}

def shutdown(self) -> None:
    for sid in list(self._clients.keys()):
        client_obj = self._clients.pop(sid, None)
        if client_obj is None:
            continue
        proc = self._procs.pop(sid, None)
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                # Windows: also kill process tree
                if platform.system() == "Windows":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                   capture_output=True, timeout=5)
            except Exception as e:
                log.warning("MCP shutdown '%s' error: %s", sid, e)
        log.info("MCP server '%s' shut down", sid)

# Add to __init__:
self._clients: dict[str, Any] = {}
self._procs: dict[str, Any] = {}
```

Note: The `__aenter__`/`__aexit__` pattern above is a simplification. The actual implementation should use the mcp SDK's context manager protocol properly. The mcp SDK's `stdio_client()` and `streamable_http_client()` return async context managers that yield `(read, write, session)`. The implementation should store the context manager and session in a dataclass:

```python
@dataclass
class _MCPClient:
    session: Any
    ctx: Any
    proc: Any = None
```

Add `self._clients: dict[str, Any] = {}` and `self._procs: dict[str, Any] = {}` to `MCPManager.__init__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_manager.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ai_engine/mcp_manager.py tests/test_mcp_manager.py
git commit -m "feat: add MCP connection lifecycle, tool calls, and shutdown"
```

---

### Task 6: MCP REST Endpoints + atexit Cleanup

**Files:**
- Modify: `backend/main.py` (add MCP REST endpoints, atexit registration, MCP tool registration into tool_registry)

**Interfaces:**
- Consumes: `MCPManager` (Tasks 4-5), `tool_registry` (Task 1)
- Produces:
  - `GET /api/mcp/servers` → `list[dict]` (env masked)
  - `POST /api/mcp/servers` → add server
  - `PUT /api/mcp/servers/{id}` → update server
  - `DELETE /api/mcp/servers/{id}` → remove server
  - `POST /api/mcp/servers/{id}/test` → connect + list tools
  - `GET /api/mcp/servers/{id}/tools` → list tools
  - `POST /api/mcp/servers/{id}/enable` → toggle enabled
  - `POST /api/mcp/shutdown` → kill all MCP processes
  - MCP tools registered into `tool_registry` as `mcp__<server_id>__<tool>` when server is enabled and connected

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_endpoints.py
import pytest, json

def test_list_servers_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    # Pre-populate
    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(tmp_backend["data_dir"])
        main.mcp_manager = mgr
    cfg = MCPServerConfig(id="test1", name="Test", transport="stdio", command="echo", args=[], url="", headers={}, env={"KEY": "val"}, enabled=True, auto_approve=False)
    mgr.add_server(cfg)

    c = TestClient(main.app)
    resp = c.get("/api/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "test1"
    # env values must be masked
    assert data[0]["env"] == {} or data[0]["env"].get("KEY") in ("***", "[encrypted]", None)

def test_add_server_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(tmp_backend["data_dir"])
        main.mcp_manager = mgr

    c = TestClient(main.app)
    resp = c.post("/api/mcp/servers", json={
        "id": "new1",
        "name": "New Server",
        "transport": "http",
        "url": "http://localhost:9999",
        "env": {"API_KEY": "secret"},
        "enabled": True,
        "auto_approve": False,
    })
    assert resp.status_code == 200
    assert mgr.get_server("new1") is not None

def test_remove_server_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(tmp_backend["data_dir"])
        main.mcp_manager = mgr
    cfg = MCPServerConfig(id="to_del", name="Del", transport="stdio", command="echo", args=[], url="", headers={}, env={}, enabled=True, auto_approve=False)
    mgr.add_server(cfg)

    c = TestClient(main.app)
    resp = c.delete("/api/mcp/servers/to_del")
    assert resp.status_code == 200
    assert mgr.get_server("to_del") is None

def test_enable_disable_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(tmp_backend["data_dir"])
        main.mcp_manager = mgr
    cfg = MCPServerConfig(id="toggle", name="Toggle", transport="stdio", command="echo", args=[], url="", headers={}, env={}, enabled=True, auto_approve=False)
    mgr.add_server(cfg)

    c = TestClient(main.app)
    c.post("/api/mcp/servers/toggle/enable", json={"enabled": False})
    assert mgr.get_server("toggle").enabled is False
    c.post("/api/mcp/servers/toggle/enable", json={"enabled": True})
    assert mgr.get_server("toggle").enabled is True

def test_shutdown_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main

    c = TestClient(main.app)
    resp = c.post("/api/mcp/shutdown")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_endpoints.py -v`
Expected: All tests FAIL — endpoints don't exist.

- [ ] **Step 3: Implement MCP REST endpoints in `main.py`**

Add to `backend/main.py`:

1. **Initialize MCP manager at startup (~line 37, after `@app.on_event("startup")`):**
```python
import atexit
from ai_engine.mcp_manager import MCPManager, mcp_manager

@app.on_event("startup")
def init_mcp():
    global mcp_manager
    if mcp_manager is None:
        data_dir = os.environ.get("AMT_DATA_DIR", os.path.join(os.path.dirname(__file__), ".."))
        mcp_manager = MCPManager(data_dir)
        atexit.register(mcp_manager.shutdown)
```

2. **MCP REST endpoints (after existing `/api/tools/*` endpoints ~line 4888):**
```python
# --- MCP Server Management ---
from pydantic import BaseModel as _BM
from ai_engine.mcp_manager import MCPServerConfig

class MCPServerIn(_BM):
    id: str
    name: str
    transport: str  # "stdio" | "http"
    command: str = ""
    args: list = []
    url: str = ""
    headers: dict = {}
    env: dict = {}
    enabled: bool = True
    auto_approve: bool = False

@app.get("/api/mcp/servers")
async def mcp_list_servers():
    if mcp_manager is None:
        return []
    result = []
    for cfg in mcp_manager.list_servers():
        d = cfg.__dict__.copy()
        if d.get("env"):
            d["env"] = {k: "***" for k in d["env"]}  # mask
        result.append(d)
    return result

@app.post("/api/mcp/servers")
async def mcp_add_server(body: MCPServerIn):
    if mcp_manager is None:
        return {"error": "MCP manager not initialized"}
    cfg = MCPServerConfig(**body.model_dump())
    mcp_manager.add_server(cfg)
    # Register MCP tools into the registry
    _register_mcp_tools(cfg)
    return {"ok": True}

@app.put("/api/mcp/servers/{server_id}")
async def mcp_update_server(server_id: str, body: MCPServerIn):
    if mcp_manager is None:
        return {"error": "MCP manager not initialized"}
    cfg = mcp_manager.get_server(server_id)
    if cfg is None:
        return {"error": "Server not found"}, 404
    cfg.name = body.name
    cfg.transport = body.transport
    cfg.command = body.command
    cfg.args = body.args
    cfg.url = body.url
    cfg.headers = body.headers
    cfg.env = body.env
    cfg.auto_approve = body.auto_approve
    mcp_manager.update_server(cfg)
    _register_mcp_tools(cfg)
    return {"ok": True}

@app.delete("/api/mcp/servers/{server_id}")
async def mcp_remove_server(server_id: str):
    if mcp_manager is None:
        return {"error": "MCP manager not initialized"}
    mcp_manager.remove_server(server_id)
    tool_registry.unregister_prefix(f"mcp__{server_id}")
    return {"ok": True}

@app.post("/api/mcp/servers/{server_id}/test")
async def mcp_test_server(server_id: str):
    if mcp_manager is None:
        return {"error": "MCP manager not initialized"}
    try:
        await mcp_manager.connect(server_id)
        tools = await mcp_manager.list_tools(server_id)
        return {"status": "connected", "tools": tools}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/mcp/servers/{server_id}/tools")
async def mcp_list_tools(server_id: str):
    if mcp_manager is None:
        return []
    try:
        return await mcp_manager.list_tools(server_id)
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/mcp/servers/{server_id}/enable")
async def mcp_set_enabled(server_id: str, body: dict):
    if mcp_manager is None:
        return {"error": "MCP manager not initialized"}
    enabled = body.get("enabled", True)
    mcp_manager.set_enabled(server_id, enabled)
    cfg = mcp_manager.get_server(server_id)
    if enabled:
        _register_mcp_tools(cfg)
    else:
        tool_registry.unregister_prefix(f"mcp__{server_id}")
    return {"ok": True}

@app.post("/api/mcp/shutdown")
async def mcp_shutdown():
    if mcp_manager is not None:
        mcp_manager.shutdown()
    return {"ok": True}
```

3. **MCP tool registration is lazy** — MCP tools are registered into `tool_registry` at the time `call_ai_api()` builds the request body, not at server-add time. This is because listing tools requires an async MCP connection. The registration happens once per server (cached in the registry); when a server is removed or disabled, its tools are unregistered via `unregister_prefix`.

In `call_ai_api()` (Task 2's loop), before building `request_body["tools"]`, add:
```python
if settings.toolCalling:
    # Register MCP tools from enabled servers (lazy, cached)
    if mcp_manager:
        for cfg in mcp_manager.list_servers():
            if not cfg.enabled:
                continue
            prefix = f"mcp__{cfg.id}"
            if any(k.startswith(prefix) for k in tool_registry._tools):
                continue  # already registered
            try:
                await mcp_manager.connect(cfg.id)
                mcp_tools = await mcp_manager.list_tools(cfg.id)
                for t in mcp_tools:
                    tool_name = f"mcp__{cfg.id}__{t['name']}"
                    if tool_registry.has(tool_name):
                        continue
                    sid = cfg.id
                    auto_approve = cfg.auto_approve
                    srv_cfg = cfg

                    async def mcp_exec(specific_tool=t["name"], sid=sid, auto=auto_approve, srv=srv_cfg, **tool_args):
                        if not auto:
                            return json.dumps({"error": f"MCP tool '{specific_tool}' requires approval (auto_approve=False on server '{srv.id}')"})
                        return await mcp_manager.call_tool(sid, specific_tool, tool_args)

                    tool_registry.register(ToolDef(
                        name=tool_name,
                        description=t.get("description", f"MCP tool {t['name']} from {cfg.name}"),
                        parameters=t.get("inputSchema", {"type": "object", "properties": {}}),
                        handler=mcp_exec,
                        source=f"mcp:{cfg.id}",
                    ))
            except Exception as e:
                log.warning("Failed to register MCP tools for '%s': %s", cfg.id, e)
    request_body["tools"] = tool_registry.schemas()
```

In the DELETE and enable/disable endpoints, call `tool_registry.unregister_prefix(f"mcp__{server_id}")` to clean up stale registrations.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mcp_endpoints.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_mcp_endpoints.py
git commit -m "feat: add MCP REST endpoints, atexit cleanup, and MCP tool registration"
```

---

### Task 7: Frontend — MCP Settings Section + Storage Section

**Files:**
- Modify: `frontend/home.html` (add `sec-mcp` settings section, add MCP storage section)
- Modify: `frontend/js/main.js` (add `showSettingsPage('sec-mcp')` handler, MCP storage section rendering)
- Create: `frontend/js/mcp.js` (MCP settings UI logic — server list, add/edit form, test connection)

**Interfaces:**
- Consumes: `/api/mcp/servers` REST endpoints (Task 6)
- Produces:
  - Settings page section `sec-mcp` with server list + add/edit form
  - Storage page section "MCP Servers" with enable/disable/delete/edit actions
  - `mcp.js` exports: `renderMcpSettings()`, `renderMcpStorage()`

- [ ] **Step 1: Add HTML sections to `home.html`**

In the settings sub-nav (after `sec-media`), add:
```html
<div class="sec-item" data-sec="sec-mcp" onclick="showSettingsPage('sec-mcp')">
  <span class="sec-icon">🔌</span><span>MCP</span>
</div>
```

Add the `sec-mcp` section div (after `sec-media` section):
```html
<div class="sec" id="sec-mcp" style="display:none">
  <h2>🔌 MCP Servers</h2>
  <div id="mcp-server-list"><!-- rendered by mcp.js --></div>
  <button id="mcp-add-btn" onclick="mcpShowAddForm()">+ Add MCP Server</button>
  <div id="mcp-add-form" style="display:none">
    <!-- form fields rendered by mcp.js -->
  </div>
</div>
```

In the storage page, add a new section to the storage grid:
```html
<div class="storage-card" id="storage-mcp">
  <div class="storage-card-header">🔌 MCP Servers</div>
  <div id="mcp-storage-list"><!-- rendered by mcp.js --></div>
</div>
```

- [ ] **Step 2: Create `frontend/js/mcp.js`**

```javascript
// frontend/js/mcp.js
async function renderMcpSettings() {
  const list = document.getElementById('mcp-server-list');
  const resp = await fetch('/api/mcp/servers');
  const servers = await resp.json();
  list.innerHTML = '';
  for (const s of servers) {
    const card = document.createElement('div');
    card.className = 'mcp-server-card';
    card.innerHTML = `
      <div class="mcp-card-header">
        <span class="mcp-card-name">${s.name}</span>
        <span class="mcp-badge">${s.transport}</span>
        <label class="mcp-enable-toggle">
          <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="mcpToggle('${s.id}', this.checked)">
        </label>
      </div>
      <div class="mcp-card-body">
        ${s.transport === 'stdio' ? `<code>${s.command} ${s.args.join(' ')}</code>` : `<code>${s.url}</code>`}
      </div>
      <div class="mcp-card-actions">
        <button onclick="mcpTest('${s.id}')">Test</button>
        <button onclick="mcpEdit('${s.id}')">Edit</button>
        <button onclick="mcpDelete('${s.id}')">Delete</button>
      </div>
    `;
    list.appendChild(card);
  }
}

async function mcpToggle(id, enabled) {
  await fetch(`/api/mcp/servers/${id}/enable`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled}),
  });
  renderMcpSettings();
}

async function mcpTest(id) {
  const resp = await fetch(`/api/mcp/servers/${id}/test`, {method: 'POST'});
  const data = await resp.json();
  if (data.status === 'connected') {
    alert(`Connected! ${data.tools.length} tool(s) available:\n` + data.tools.map(t => `• ${t.name}: ${t.description || ''}`).join('\n'));
  } else {
    alert(`Error: ${data.message || data.status}`);
  }
}

async function mcpDelete(id) {
  if (!confirm('Delete this MCP server?')) return;
  await fetch(`/api/mcp/servers/${id}`, {method: 'DELETE'});
  renderMcpSettings();
}

async function mcpShowAddForm() {
  const form = document.getElementById('mcp-add-form');
  form.style.display = 'block';
  form.innerHTML = `
    <h3>Add MCP Server</h3>
    <input id="mcp-name" placeholder="Name" value="">
    <input id="mcp-id" placeholder="ID (slug, e.g. fs)" value="">
    <div class="mcp-transport-radios">
      <label><input type="radio" name="mcp-transport" value="stdio" checked> STDIO</label>
      <label><input type="radio" name="mcp-transport" value="http"> HTTP</label>
    </div>
    <div id="mcp-stdio-fields">
      <input id="mcp-command" placeholder="Command (e.g. npx)" value="">
      <input id="mcp-args" placeholder="Args (space-separated)" value="">
    </div>
    <div id="mcp-http-fields" style="display:none">
      <input id="mcp-url" placeholder="URL (e.g. http://localhost:3000/mcp)" value="">
      <input id="mcp-headers" placeholder="Headers (JSON, optional)" value="{}">
    </div>
    <div id="mcp-env-fields">
      <h4>Env Vars</h4>
      <div id="mcp-env-list"></div>
      <button type="button" onclick="mcpAddEnvRow()">+ Add Env Var</button>
    </div>
    <label><input type="checkbox" id="mcp-enabled" checked> Enabled</label>
    <label><input type="checkbox" id="mcp-auto-approve"> Auto-approve tool calls</label>
    <button onclick="mcpSubmit()">Save</button>
    <button onclick="mcpShowAddForm(); document.getElementById('mcp-add-form').style.display='none'">Cancel</button>
  `;
  // Toggle stdio/http fields
  form.querySelectorAll('input[name="mcp-transport"]').forEach(r => {
    r.addEventListener('change', () => {
      const isStdio = form.querySelector('input[name="mcp-transport"]:checked').value === 'stdio';
      document.getElementById('mcp-stdio-fields').style.display = isStdio ? 'block' : 'none';
      document.getElementById('mcp-http-fields').style.display = isStdio ? 'none' : 'block';
    });
  });
}

function mcpAddEnvRow() {
  const list = document.getElementById('mcp-env-list');
  const row = document.createElement('div');
  row.className = 'mcp-env-row';
  row.innerHTML = `<input placeholder="KEY" class="mcp-env-key"><input placeholder="value" type="password" class="mcp-env-val">`;
  list.appendChild(row);
}

async function mcpSubmit() {
  const transport = document.querySelector('input[name="mcp-transport"]:checked').value;
  const body = {
    id: document.getElementById('mcp-id').value.trim(),
    name: document.getElementById('mcp-name').value.trim(),
    transport,
    enabled: document.getElementById('mcp-enabled').checked,
    auto_approve: document.getElementById('mcp-auto-approve').checked,
  };
  if (transport === 'stdio') {
    body.command = document.getElementById('mcp-command').value.trim();
    body.args = document.getElementById('mcp-args').value.split(' ').filter(Boolean);
  } else {
    body.url = document.getElementById('mcp-url').value.trim();
    try { body.headers = JSON.parse(document.getElementById('mcp-headers').value || '{}'); } catch { body.headers = {}; }
  }
  body.env = {};
  document.querySelectorAll('.mcp-env-row').forEach(row => {
    const k = row.querySelector('.mcp-env-key').value;
    const v = row.querySelector('.mcp-env-val').value;
    if (k) body.env[k] = v;
  });
  const resp = await fetch('/api/mcp/servers', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (resp.ok) {
    document.getElementById('mcp-add-form').style.display = 'none';
    renderMcpSettings();
  } else {
    const err = await resp.json();
    alert('Error: ' + (err.error || JSON.stringify(err)));
  }
}

// Storage page
async function renderMcpStorage() {
  const list = document.getElementById('mcp-storage-list');
  if (!list) return;
  const resp = await fetch('/api/mcp/servers');
  const servers = await resp.json();
  list.innerHTML = '';
  for (const s of servers) {
    const row = document.createElement('div');
    row.className = 'storage-item';
    row.innerHTML = `
      <span>${s.name}</span>
      <span class="badge">${s.transport}</span>
      <button onclick="mcpToggle('${s.id}', ${!s.enabled})">${s.enabled ? 'Disable' : 'Enable'}</button>
      <button onclick="showSettingsPage('sec-mcp')">Edit</button>
      <button onclick="mcpDelete('${s.id}')">Delete</button>
    `;
    list.appendChild(row);
  }
}
```

- [ ] **Step 3: Wire `mcp.js` into `main.js`**

In `frontend/js/main.js`:

1. Add `<script src="mcp.js"></script>` to `home.html` before the closing `</body>` tag (after `main.js`).

2. In `showSettingsPage(secId)` (~line 3153), add case for `sec-mcp`:
```javascript
if (secId === 'sec-mcp') {
  renderMcpSettings();
}
```

3. In the storage page render function (~line 3838, `renderStorageInteractive`), add MCP section:
```javascript
// MCP Servers section
const mcpSection = {
  id: 'mcp',
  title: 'MCP Servers',
  icon: '🔌',
  load: renderMcpStorage,
};
```

- [ ] **Step 4: Add CSS for MCP cards**

Add minimal CSS to `frontend/home.html` or a theme file:
```css
.mcp-server-card { /* card styling consistent with existing storage cards */ }
.mcp-card-header { display: flex; align-items: center; gap: 8px; }
.mcp-badge { font-size: 0.75em; padding: 2px 6px; border-radius: 4px; background: var(--accent-dim); }
.mcp-env-row { display: flex; gap: 8px; margin: 4px 0; }
.mcp-env-row input { flex: 1; }
```

- [ ] **Step 5: Commit**

```bash
git add frontend/home.html frontend/js/main.js frontend/js/mcp.js
git commit -m "feat: add MCP settings section and storage page"
```

---

### Task 8: Frontend — Tool-Call Cards in Chat + WS Event Handling

**Files:**
- Modify: `frontend/js/main.js` (WS event handling for `tool_call_start`/`tool_call_result`, tool-call card rendering)

**Interfaces:**
- Consumes: WS events `{"type": "tool_call_start", "tool": ..., "args": ...}` and `{"type": "tool_call_result", "tool": ..., "result": ...}` (Task 3)
- Produces: Inline tool-call cards in the chat bubble between message chunks

- [ ] **Step 1: Write a frontend test**

```javascript
// tests/frontend/tool-cards.spec.js
const { JSDOM } = require('jsdom');

function test_tool_call_start_renders_card() {
  const dom = new JSDOM('<div id="chat-messages"></div>');
  const doc = dom.window.document;

  // Simulate what streamViaWebSocket would do on tool_call_start
  const hostEl = doc.getElementById('chat-messages');
  const card = doc.createElement('div');
  card.className = 'tool-call-card';
  card.dataset.tool = 'generate_image';
  card.innerHTML = `<span class="tool-icon">🔧</span> Calling generate_image… <span class="tool-spinner"></span>`;
  hostEl.appendChild(card);

  // Assert card exists and has the right structure
  const cards = doc.querySelectorAll('.tool-call-card');
  console.assert(cards.length === 1, 'Expected 1 tool-call card');
  console.assert(cards[0].dataset.tool === 'generate_image', 'Wrong tool name');
  console.log('PASS: tool_call_start renders card');
}

function test_tool_call_result_updates_card() {
  const dom = new JSDOM('<div id="chat-messages"><div class="tool-call-card" data-tool="generate_image">🔧 Calling generate_image…</div></div>');
  const doc = dom.window.document;

  const card = doc.querySelector('.tool-call-card');
  card.innerHTML = `<span class="tool-icon">✅</span> generate_image returned 2 KB`;
  card.classList.add('done');

  console.assert(card.classList.contains('done'), 'Card should have done class');
  console.log('PASS: tool_call_result updates card');
}

test_tool_call_start_renders_card();
test_tool_call_result_updates_card();
console.log('All frontend tool-card tests passed');
```

- [ ] **Step 2: Run the test**

Run: `node tests/frontend/tool-cards.spec.js`
Expected: PASS (this is a structural test, not a full DOM test).

- [ ] **Step 3: Modify `streamViaWebSocket()` in `main.js`**

In `streamViaWebSocket()` (~line 1765), add handling for tool events:

```javascript
// In the WS onmessage handler, before the "chunk" case:
case "tool_call_start": {
  const card = document.createElement('div');
  card.className = 'tool-call-card running';
  card.dataset.tool = data.tool;
  card.dataset.callId = data.callId || '';
  card.innerHTML = `<span class="tool-icon">🔧</span> ${data.tool}… <span class="tool-spinner"></span>`;
  assistantEl.appendChild(card);
  break;
}
case "tool_call_result": {
  const card = assistantEl.querySelector(`.tool-call-card[data-tool="${data.tool}"].running`);
  if (card) {
    const preview = typeof data.result === 'string' ? data.result.slice(0, 200) : JSON.stringify(data.result).slice(0, 200);
    card.classList.remove('running');
    card.classList.add('done');
    card.innerHTML = `<span class="tool-icon">✅</span> ${data.tool} → ${preview}`;
    // For media tools, render the media inline
    if (data.tool.startsWith('generate_')) {
      renderGenInChat({ kind: data.tool.replace('generate_', ''), prompt: '', result: data.result }, assistantEl);
    }
  }
  break;
}
```

- [ ] **Step 4: Add CSS for tool-call cards**

```css
.tool-call-card {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin: 4px 0;
  border-radius: 6px;
  background: var(--surface-dim);
  font-size: 0.85em;
  opacity: 0.9;
}
.tool-call-card.running .tool-spinner {
  width: 12px; height: 12px;
  border: 2px solid var(--accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.tool-call-card.done { opacity: 0.7; }
@keyframes spin { to { transform: rotate(360deg); } }
```

- [ ] **Step 5: Commit**

```bash
git add frontend/js/main.js frontend/home.html tests/frontend/tool-cards.spec.js
git commit -m "feat: add tool-call cards to chat with WS event handling"
```

---

### Task 9: Final Verification + PyInstaller Spec

**Files:**
- Modify: `requirements.txt` (verify `mcp`, `cryptography` are listed)
- Modify: PyInstaller spec file (add `--collect-all mcp`)
- Run: full test suite

**Interfaces:**
- Consumes: All previous tasks
- Produces: Verified build, passing tests

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 2: Verify requirements.txt**

Confirm `mcp>=1.0.0` and `cryptography>=42.0.0` are present.

- [ ] **Step 3: Update PyInstaller spec**

Find the PyInstaller spec file (`.spec` file or `setup.py` build config). Add:
```python
hiddenimports=['mcp'],
collect_all=['mcp'],
```
Or in the spec file:
```python
a = Analysis(
    ...
    collect_all=['mcp'],
    ...
)
```

- [ ] **Step 4: Run frontend tests**

Run: `node tests/frontend/tool-cards.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt *.spec setup.py tests/frontend/tool-cards.spec.js
git commit -m "chore: verify deps, update PyInstaller spec for mcp package"
```
