# backend/media_server/server.py
"""STDIO MCP server exposing AMT's media generation tools.

Tools (auto-registered into AMT's Tool Registry as mcp__media__<tool>):
    generate_image    — image from text prompt (+quality/style, quoted-text preserved language-neutral)
    generate_image_ref— image-to-image / edit from a reference image
    analyze_image     — vision: describe / OCR / extract structure from an image
    generate_video    — video from text prompt (async task; +quality/size, Agnes model)
    generate_video_example — video-to-video from a reference clip
    check_video       — poll a video task (status + progress)
    generate_audio    — text-to-speech (+voice settings: speed/stability/style/similarity)
    clone_voice       — voice cloning from an audio sample
    list_voices       — list available voices
    transcribe        — speech-to-text (STT)

    (File generation moved to the dedicated Writer MCP server: mcp__writer__*.)

Transport: STDIO. Launched by AMT via the preset (command = python -m media_server).
Credentials are read from a JSON file (AMT_MEDIA_CREDS_FILE env, or default
path under the backend dir) that AMT's main process updates with the current
image/video/audio keys before each tool-call session.
"""
from __future__ import annotations
import os, json, asyncio, logging, base64

# The MCP server speaks JSON-RPC over stdout — logging must go to stderr.
logging.basicConfig(level=logging.INFO, stream=os.sys.stderr)
log = logging.getLogger("media_server")

# Credentials file: AMT writes the current image/video/audio keys here before
# launching the media server. The server reads it at connect time.
_CREDS_FILE = os.environ.get(
    "AMT_MEDIA_CREDS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media_creds.json"),
)
_FILES_DIR = os.environ.get(
    "AMT_FILES_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "FILES_DIR"),
)

# Cache creds so we don't re-read on every tool call
_creds: dict = {}

def _load_creds() -> dict:
    """Load credentials from the JSON file. Returns {} if missing."""
    global _creds
    try:
        if os.path.exists(_CREDS_FILE):
            with open(_CREDS_FILE) as f:
                _creds = json.load(f)
    except Exception as e:
        log.warning("media_server: failed to load creds file %s: %s", _CREDS_FILE, e)
        _creds = {}
    return _creds


def _json(result: dict) -> str:
    """MCP tools return JSON strings (single text block in the result)."""
    return json.dumps(result, ensure_ascii=False, indent=2)


def _resolve(kind: str, model_override: str = "") -> tuple[str, str, str, str]:
    """Resolve credentials for a media kind: (base_url, api_key, model, proxy).

    Per-kind creds first, then global, then empty. model_override wins if set.
    """
    c = _load_creds()
    # Per-kind: image_base, image_key, image_model / video_base / audio_base
    b = c.get(f"{kind}_base_url", "") or c.get("base_url", "")
    k = c.get(f"{kind}_api_key", "") or c.get("api_key", "")
    m = model_override or c.get(f"{kind}_model", "") or c.get("model", "")
    proxy = c.get("proxy", "")
    return b, k, m, proxy


def _resolve_path(kind: str, default_path: str) -> str:
    """Return the user-configured API path for a media kind, falling back to default.

    The user can override the API path in AMT's «Медиа-ключи» settings page.
    When set, the tool uses that path instead of the hardcoded default.
    """
    c = _load_creds()
    key_map = {
        "image": "media_path_text",       # text → image
        "video": "media_path_video",
        "audio": "media_path_voice",      # TTS + STT
    }
    user_path = c.get(key_map.get(kind, ""), "").strip()
    return user_path if user_path else default_path


def build_server():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer(
        "AMT-Media",
        description="AMT media generation server — image, video, audio, file tools.",
        instructions=(
            "Generate media (images, videos, audio) and files. Credentials are "
            "configured by AMT via environment variables. If a tool returns "
            "'no_key' or 'no_base_url', the user has not configured the "
            "appropriate API key/URL — inform them to set it in AMT's "
            "settings or key store. Video generation is async: call "
            "generate_video to create a task, then poll with check_video."
        ),
    )

    def _preserve_quoted_text(prompt: str) -> str:
        """Language-neutral prompt helper: if the user quoted exact text in the
        prompt, append it verbatim as an explicit rendering target. No language,
        spelling, or typography assumptions are baked in — the model owns how to
        render text in any language; this just preserves the user's quoted words.
        """
        import re
        prompt = prompt or ""
        # Match text between any opening quote (straight/curly, ASCII or unicode)
        # and a matching closing quote. ASCII-only char classes keep the source
        # encoding-robust; \uXXXX escapes are interpreted by `re` in patterns.
        open_q = "[\"\u201c\u00ab\u0060]"
        close_q = "[\"\u201d\u00bb\u0060]"
        inner = "([^\"\u201c\u00ab\u201d\u00bb\u0060]{1,60})"
        pat = re.compile(open_q + inner + close_q)
        quoted = pat.findall(prompt)
        if not quoted:
            return prompt
        return prompt + " (render this exact text: " + " / ".join(quoted[:4]) + ")"

    @mcp.tool(description=(
        "Generate an image from a text prompt. Returns base64 image data or a URL. "
        "Works with any OpenAI-compatible /images/generations endpoint. "
        "Uses the image-specific API key/URL/model/path from AMT's media settings. "
        "Supports quality/style; preserves user-quoted text verbatim (any language)."
    ))
    def generate_image(prompt: str, size: str = "1024x1024", model: str = "",
                       ref_image_b64: str = "", quality: str = "", style: str = "") -> str:
        import httpx
        # Preserve user-quoted text verbatim (language-neutral)
        eff_prompt = _preserve_quoted_text(prompt)
        base_url, api_key, m, proxy = _resolve("image", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No image API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No image Base URL configured"})
        # User-configured path override from media settings
        api_path = _resolve_path("image", "images/generations")
        edit_path = _resolve_path("image", "images/edits") if ref_image_b64 else ""
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            if ref_image_b64:
                # image-to-image: use /images/edits (multipart)
                raw = base64.b64decode(ref_image_b64)
                import urllib3, io
                from urllib3.filepost import encode_multipart_formdata
                fields = {"model": m, "prompt": eff_prompt, "size": size}
                if quality:
                    fields["quality"] = quality
                if style:
                    fields["style"] = style
                files = {"image[]": ("ref.png", raw, "image/png")}
                body, content_type = encode_multipart_formdata(
                    {**files, **{k: (k, v) for k, v in fields.items()}})
                r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                           headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
                           content=body)
            else:
                jbody = {"model": m, "prompt": eff_prompt, "n": 1, "size": size}
                if quality:
                    jbody["quality"] = quality
                if style:
                    jbody["style"] = style
                r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                           headers={"Authorization": f"Bearer {api_key}"},
                           json=jbody)
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        data = r.json()
        item = (data.get("data") or [{}])[0] if isinstance(data.get("data"), list) else {}
        b64 = item.get("b64_json", "")
        url = item.get("url", "")
        if b64:
            return _json({"ok": True, "mime": "image/png", "b64": b64})
        if url:
            return _json({"ok": True, "mime": "image/png", "url": url})
        return _json({"ok": False, "code": "error", "error": "No image data received"})

    @mcp.tool(description=(
        "Generate a video from a text prompt. Returns a task_id for async polling. "
        "Use check_video to poll for completion. "
        "Uses the video-specific API key/URL/model/path from AMT's media settings."
    ))
    def generate_video(prompt: str, duration: int = 5, aspect_ratio: str = "9:16",
                       model: str = "", quality: str = "", size: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("video", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No video API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No video Base URL configured"})
        api_path = _resolve_path("video", "v1/videos/text2video")
        _body = {"prompt": prompt, "duration": str(duration), "aspect_ratio": aspect_ratio, "model": m}
        if quality:
            _body["quality"] = quality
        if size:
            _body["size"] = size
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                       headers={"Authorization": f"Bearer {api_key}"},
                       json=_body)
        if r.status_code in (200, 201, 202):
            d = r.json()
            task_id = d.get("task_id") or (d.get("data") or {}).get("task_id") or ""
            return _json({"ok": True, "task_id": task_id, "note": "Video task created. Poll with check_video."})
        return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})

    @mcp.tool(description=(
        "Check the status of a video generation task. Returns status (queued/processing/completed/failed) "
        "and the video URL when completed. Uses the video-specific settings from AMT's media config."
    ))
    def check_video(task_id: str, model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("video", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No video API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No video Base URL configured"})
        api_path = _resolve_path("video", "v1/videos/text2video")
        kwargs = {"timeout": 30.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            r = c.get(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}/{task_id}",
                      headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code >= 400:
            return _json({"ok": False, "status": "error", "error": f"{r.status_code} {r.text[:200]}"})
        d = r.json()
        data = d.get("data") or d
        status = data.get("task_status") or data.get("status", "")
        progress = data.get("progress", "")
        out = {"ok": status in ("succeed", "completed"), "status": status}
        if progress:
            out["progress"] = progress
        if status in ("succeed", "completed"):
            url = (data.get("task_result") or [{}])[0].get("url", "") if isinstance(data.get("task_result"), list) else data.get("url", "")
            out["url"] = url
        return _json(out)

    @mcp.tool(description=(
        "Text-to-speech: generate audio from text. Returns base64 audio data. "
        "Works with OpenAI-compatible /v1/audio/speech or ElevenLabs. "
        "Uses the audio-specific API key/URL/model/voice/path from AMT's media settings."
    ))
    def generate_audio(text: str, voice_id: str = "", model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("audio", model)
        c = _load_creds()
        vid = voice_id or c.get("audio_voice_id", "")
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No audio API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No audio Base URL configured"})
        api_path = _resolve_path("audio", "v1/audio/speech")
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        is_eleven = "elevenlabs.io" in (base_url or "")
        with httpx.Client(**kwargs) as c:
            if is_eleven:
                vid = vid or "21m00Tcm4TlvDq8ikT7d"
                r = c.post(f"{base_url.rstrip('/')}/v1/text-to-speech/{vid}",
                           headers={"xi-api-key": api_key},
                           json={"text": text, "model_id": m or "eleven_multilingual_v2"})
            else:
                r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                           headers={"Authorization": f"Bearer {api_key}"},
                           json={"model": m, "voice": vid, "input": text})
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        return _json({"ok": True, "mime": "audio/mpeg", "b64": base64.b64encode(r.content).decode("ascii"), "voice_id": vid})

    @mcp.tool(description=(
        "Speech-to-text: transcribe audio to text. Accepts base64-encoded audio. "
        "Works with OpenAI-compatible /v1/audio/transcriptions. "
        "Uses the audio-specific API key/URL/model from AMT's media settings."
    ))
    def transcribe(audio_b64: str, mime: str = "audio/webm", model: str = "") -> str:
        import httpx, io
        base_url, api_key, m, proxy = _resolve("audio", model)
        m = m or "whisper-1"
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No STT API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No STT Base URL configured"})
        if not audio_b64:
            return _json({"ok": False, "code": "no_audio", "error": "Empty audio"})
        raw = base64.b64decode(audio_b64)
        ext = {"audio/wav": "wav", "audio/mp3": "mp3", "audio/mpeg": "mp3",
               "audio/ogg": "ogg", "audio/webm": "webm", "audio/flac": "flac"}.get(mime, "webm")
        fname = f"audio.{ext}"
        api_path = _resolve_path("audio", "v1/audio/transcriptions")
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            api_base = base_url.rstrip("/")
            if api_base.endswith("/v1"):
                api_base = api_base[:-len("/v1")]
            fields = {"model": m}
            files = {"file": (fname, io.BytesIO(raw), mime)}
            r = c.post(f"{api_base}/{api_path.lstrip('/')}",
                       headers={"Authorization": f"Bearer {api_key}"},
                       files=files, data=fields)
        if r.status_code >= 400:
            return _json({"ok": False, "code": "error", "error": f"{r.status_code} {r.text[:200]}"})
        try:
            j = r.json()
            return _json({"ok": True, "text": (j.get("text") or "").strip()})
        except Exception:
            return _json({"ok": True, "text": r.text.strip()})

    # ----- advanced image: image-to-image / edit -----
    @mcp.tool(description=(
        "Generate or edit an image from a reference image (image-to-image). "
        "Sends the reference + prompt to /images/edits (multipart). "
        "Uses the image-specific API key/URL/model/path from AMT's media settings."
    ))
    def generate_image_ref(prompt: str, ref_image_b64: str, size: str = "1024x1024",
                          model: str = "", quality: str = "") -> str:
        if not ref_image_b64:
            return _json({"ok": False, "code": "no_ref_image", "error": "ref_image_b64 is required"})
        # Reuse generate_image's ref path (it already handles multipart edits).
        return generate_image(prompt=prompt, size=size, model=model, ref_image_b64=ref_image_b64,
                              quality=quality)

    # ----- advanced image: vision analysis -----
    @mcp.tool(description=(
        "Analyze an image with a vision model: describe it, extract/OCR text, or "
        "extract structure. Returns the model's analysis. Uses the image-specific "
        "API key/URL/model from AMT's media settings."
    ))
    def analyze_image(image_b64: str, task: str = "describe", mime: str = "image/png",
                      model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("image", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No image API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No image Base URL configured"})
        if not image_b64:
            return _json({"ok": False, "code": "no_image", "error": "image_b64 is required"})
        task = task or "describe"
        prompts = {
            "describe": "Describe this image in detail.",
            "ocr": "Extract all visible text from this image. Return it verbatim, preserving language.",
            "structure": "Describe the visual structure/layout of this image (objects, regions, relationships).",
        }
        instr = prompts.get(task, task)
        api_path = _resolve_path("image", "chat/completions")
        kwargs = {"timeout": 120.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            r = c.post(
                f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": m, "messages": [
                    {"role": "user", "content": [
                        {"type": "text", "text": instr},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    ]}
                ]})
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        try:
            j = r.json()
            text = (j.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return _json({"ok": True, "task": task, "analysis": (text or "").strip()})
        except Exception:
            return _json({"ok": True, "task": task, "analysis": r.text.strip()[:2000]})

    # ----- advanced video: video-to-video from an example clip -----
    @mcp.tool(description=(
        "Generate a video from a text prompt + a reference example clip (video-to-video). "
        "Sends the example to /v1/videos/video2video (multipart). Returns a task_id to poll "
        "with check_video. Uses the video-specific settings from AMT's media config."
    ))
    def generate_video_example(prompt: str, example_b64: str, duration: int = 5,
                               aspect_ratio: str = "9:16", model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("video", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No video API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No video Base URL configured"})
        if not example_b64:
            return _json({"ok": False, "code": "no_example", "error": "example_b64 is required"})
        api_path = _resolve_path("video", "v1/videos/video2video")
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        with httpx.Client(**kwargs) as c:
            raw = base64.b64decode(example_b64)
            import urllib3, io
            from urllib3.filepost import encode_multipart_formdata
            files = {"video": ("example.mp4", raw, "video/mp4")}
            fields = {"prompt": prompt, "duration": str(duration), "aspect_ratio": aspect_ratio}
            if m:
                fields["model"] = m
            body, content_type = encode_multipart_formdata(
                {**files, **{k: (k, v) for k, v in fields.items()}})
            r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                       headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
                       content=body)
        if r.status_code in (200, 201, 202):
            d = r.json()
            task_id = d.get("task_id") or (d.get("data") or {}).get("task_id") or ""
            return _json({"ok": True, "task_id": task_id, "note": "Video-to-video task created. Poll with check_video."})
        return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})

    # ----- advanced audio: TTS with voice settings -----
    @mcp.tool(description=(
        "Text-to-speech with advanced voice settings. speed (0.7-1.2), stability/style "
        "(0-1), similarity (speaker boost), output_format (mp3/pcm/wav/ogg/flac). "
        "Works with OpenAI-compatible /v1/audio/speech or ElevenLabs. "
        "Uses the audio-specific API key/URL/model/voice/path from AMT's media settings."
    ))
    def generate_audio_advanced(text: str, voice_id: str = "", model: str = "",
                                speed: float = 0.0, stability: float = 0.0,
                                style: float = 0.0, similarity: float = 0.0,
                                output_format: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("audio", model)
        c = _load_creds()
        vid = voice_id or c.get("audio_voice_id", "")
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No audio API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No audio Base URL configured"})
        vs = {}
        if speed:
            vs["speed"] = speed
        if stability:
            vs["stability"] = stability
        if style:
            vs["style"] = style
        if similarity:
            vs["similarity"] = similarity
        api_path = _resolve_path("audio", "v1/audio/speech")
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        is_eleven = "elevenlabs.io" in (base_url or "")
        with httpx.Client(**kwargs) as c:
            if is_eleven:
                vid = vid or "21m00Tcm4TlvDq8ikT7d"
                body = {"text": text, "model_id": m or "eleven_multilingual_v2"}
                el_vs = {}
                if vs.get("speed"):
                    el_vs["speed"] = vs["speed"]
                if vs.get("stability"):
                    el_vs["stability"] = vs["stability"]
                if vs.get("style"):
                    el_vs["style"] = vs["style"]
                if vs.get("similarity"):
                    el_vs["use_speaker_boost"] = bool(vs["similarity"])
                if el_vs:
                    body["voice_settings"] = el_vs
                if output_format:
                    body["output_format"] = output_format
                r = c.post(f"{base_url.rstrip('/')}/v1/text-to-speech/{vid}",
                            headers={"xi-api-key": api_key}, json=body)
            else:
                body = {"model": m, "voice": vid, "input": text}
                if vs.get("speed"):
                    body["speed"] = vs["speed"]
                if output_format:
                    body["response_format"] = output_format
                r = c.post(f"{base_url.rstrip('/')}/{api_path.lstrip('/')}",
                           headers={"Authorization": f"Bearer {api_key}"}, json=body)
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        return _json({"ok": True, "mime": "audio/mpeg", "voice_id": vid,
                      "settings": vs,
                      "b64": base64.b64encode(r.content).decode("ascii")})

    # ----- voice clone + list -----
    @mcp.tool(description=(
        "Clone a voice from an audio sample (base64). Returns the new voice_id. "
        "Works with ElevenLabs (/v1/voices/add) or OpenAI-compatible (/v1/voices). "
        "Uses the audio-specific API key/URL from AMT's media settings."
    ))
    def clone_voice(audio_b64: str, name: str = "", model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("audio", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No audio API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No audio Base URL configured"})
        if not audio_b64:
            return _json({"ok": False, "code": "no_audio", "error": "audio_b64 is required"})
        kwargs = {"timeout": 300.0}
        if proxy:
            kwargs["proxy"] = proxy
        is_eleven = "elevenlabs.io" in (base_url or "")
        with httpx.Client(**kwargs) as c:
            if is_eleven:
                r = c.post(f"{base_url.rstrip('/')}/v1/voices/add",
                           headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                           json={"name": name or "Cloned voice", "files": [audio_b64],
                                 "description": "Instant clone"})
            else:
                r = c.post(f"{base_url.rstrip('/')}/v1/voices",
                           headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                           json={"name": name or "Cloned voice", "audio": audio_b64, "type": "clone"})
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        d = r.json()
        return _json({"ok": True, "voice_id": d.get("id", ""), "name": d.get("name", name)})

    @mcp.tool(description=(
        "List available voices for the audio provider. Works with ElevenLabs (/v1/voices) "
        "or OpenAI-compatible (/v1/voices). Uses the audio-specific settings from AMT's media config."
    ))
    def list_voices(model: str = "") -> str:
        import httpx
        base_url, api_key, m, proxy = _resolve("audio", model)
        if not api_key:
            return _json({"ok": False, "code": "no_key", "error": "No audio API key configured"})
        if not base_url:
            return _json({"ok": False, "code": "no_base_url", "error": "No audio Base URL configured"})
        kwargs = {"timeout": 30.0}
        if proxy:
            kwargs["proxy"] = proxy
        is_eleven = "elevenlabs.io" in (base_url or "")
        with httpx.Client(**kwargs) as c:
            if is_eleven:
                r = c.get(f"{base_url.rstrip('/')}/v1/voices", headers={"xi-api-key": api_key})
            else:
                api_base = base_url.rstrip("/")
                if api_base.endswith("/v1"):
                    api_base = api_base[:-len("/v1")]
                r = c.get(f"{api_base}/v1/voices", headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code >= 400:
            return _json({"ok": False, "code": "unsupported", "error": f"{r.status_code} {r.text[:200]}"})
        d = r.json()
        voices = d.get("voices", d if isinstance(d, list) else [])
        return _json({"ok": True, "voices": voices})

    return mcp


def main() -> None:
    mcp = build_server()
    log.info("AMT-Media server starting")
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
