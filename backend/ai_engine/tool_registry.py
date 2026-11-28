# backend/ai_engine/tool_registry.py
from __future__ import annotations
import json, logging, os, traceback
from dataclasses import dataclass
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

    def schemas_for_profile(self, profile) -> list[dict]:
        coding_tools = {"fs_read", "fs_list", "fs_search", "fs_write", "fs_apply_patch", "run_command", "git_status", "git_diff", "git_log", "git_add", "git_commit", "git_branch", "git_push"}
        media_tools = {"generate_image", "generate_video", "generate_audio", "generate_file"}
        result = []
        for name, tool in self._tools.items():
            if profile.chat_mode == "coding":
                if name in coding_tools or tool.source.startswith("mcp:"):
                    result.append(self._schema_for(tool))
            else:
                if name not in coding_tools:
                    result.append(self._schema_for(tool))
        return result

    def _schema_for(self, tool: ToolDef) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

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


def _media_cfg(kind: str) -> dict:
    """Ключ/адрес/модель/прокси для kind из глобальных настроек (main.server_settings).

    Точная логика как в main._media_cfg(): image→imageKey/imageBaseUrl/imageModel,
    video→video*, audio→audio* (+STT-модель в приоритете), иначе глобальный.
    Инструменты tool-calling не имеют своего ключа, поэтому читаем из настроек."""
    import sys
    ss = None
    try:
        import main  # локальный импорт, чтобы не тянуть цикл на уровне модуля
        ss = main.server_settings
    except Exception:
        mod = sys.modules.get("main")
        ss = getattr(mod, "server_settings", None) if mod else None

    base = key = model = proxy = ""
    if ss is not None:
        proxy = (getattr(ss, "proxyUrl", "") or "").strip() or (getattr(ss, "httpsProxy", "") or "").strip()
        if kind == "image":
            base = getattr(ss, "imageBaseUrl", "") or getattr(ss, "baseUrl", "")
            key = getattr(ss, "imageKey", "") or getattr(ss, "apiKey", "")
            model = getattr(ss, "imageModel", "") or getattr(ss, "model", "")
        elif kind == "video":
            base = getattr(ss, "videoBaseUrl", "") or getattr(ss, "baseUrl", "")
            key = getattr(ss, "videoKey", "") or getattr(ss, "apiKey", "")
            model = getattr(ss, "videoModel", "") or getattr(ss, "model", "")
        elif kind == "audio":
            base = getattr(ss, "audioBaseUrl", "") or getattr(ss, "baseUrl", "")
            key = getattr(ss, "audioKey", "") or getattr(ss, "apiKey", "")
            stt_model = (getattr(ss, "sttModel", "") or "").strip()
            model = stt_model or getattr(ss, "audioModel", "") or getattr(ss, "model", "")
        else:
            base = getattr(ss, "baseUrl", "")
            key = getattr(ss, "apiKey", "")
            model = getattr(ss, "model", "")

    # Анти-«no_key»: если ключ пуст, возможно пользователь ввёл/сохранил его в UI,
    # но серверный процесс его ещё не увидел (load_persisted_settings() выполняется
    # один раз при импорте). Перечитываем сохранённые настройки с диска — только
    # когда ключ пуст, чтобы НЕ затирать актуальный в-памяти ключ сессии.
    if not (key or "").strip():
        try:
            import main as _main
            _main.load_persisted_settings()
            _ss2 = _main.server_settings
            if _ss2 is not None:
                if kind == "image":
                    key = getattr(_ss2, "imageKey", "") or getattr(_ss2, "apiKey", "")
                    base = base or getattr(_ss2, "imageBaseUrl", "")
                    model = model or getattr(_ss2, "imageModel", "")
                elif kind == "video":
                    key = getattr(_ss2, "videoKey", "") or getattr(_ss2, "apiKey", "")
                    base = base or getattr(_ss2, "videoBaseUrl", "")
                    model = model or getattr(_ss2, "videoModel", "")
                elif kind == "audio":
                    key = getattr(_ss2, "audioKey", "") or getattr(_ss2, "apiKey", "")
                    _stt = (getattr(_ss2, "sttModel", "") or "").strip()
                    model = model or (_stt or getattr(_ss2, "audioModel", "") or getattr(_ss2, "model", ""))
                    base = base or getattr(_ss2, "audioBaseUrl", "")
                else:
                    key = key or getattr(_ss2, "apiKey", "")
                    base = base or getattr(_ss2, "baseUrl", "")
                    model = model or getattr(_ss2, "model", "")
        except Exception:
            pass  # reload не обязан ломать вызов; остаётся no_key, как раньше

    return {"base": base, "key": key, "model": model, "proxy": proxy}


async def _handle_generate_image(prompt: str, size: str = "1:1", model: str = "", ref_image_b64: str = "") -> str:
    """Генерация картинки (tool-calling). Ключ/адрес — из настроек; вызываем
    media.generate_image/generate_image_ref с ИМЕННЫМИ аргументами (не dict!)."""
    from ai_engine import media
    cfg = _media_cfg("image")
    if ref_image_b64:
        result = media.generate_image_ref(cfg["base"], cfg["key"], model or cfg["model"],
                                          prompt, size or "1024x1024", ref_image_b64, cfg["proxy"])
    else:
        result = media.generate_image(cfg["base"], cfg["key"], model or cfg["model"],
                                      prompt, size or "1024x1024", cfg["proxy"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_generate_video(prompt: str, aspect_ratio: str = "9:16", duration: int = 5, model: str = "") -> str:
    from ai_engine import media
    cfg = _media_cfg("video")
    result = media.generate_video(cfg["base"], cfg["key"], model or cfg["model"],
                                  prompt, str(duration), aspect_ratio, cfg["proxy"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_generate_audio(text: str, voice_id: str = "", model: str = "") -> str:
    from ai_engine import media
    cfg = _media_cfg("audio")
    result = media.generate_audio(cfg["base"], cfg["key"], model or cfg["model"],
                                  text, voice_id, cfg["proxy"])
    return json.dumps(result, ensure_ascii=False)


async def _handle_generate_file(filetype: str, content: str, title: str = "", lang: str = "") -> str:
    from ai_engine import filegen
    import base64
    import uuid
    data, filename = filegen.generate_file(filetype, content, title, lang)
    files_dir = _files_dir()
    os.makedirs(files_dir, exist_ok=True)
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
