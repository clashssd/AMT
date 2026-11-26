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

