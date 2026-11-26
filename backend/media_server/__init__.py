# backend/media_server/__init__.py
"""Media generation MCP server for AMT.

A standalone STDIO MCP server that exposes AMT's media generation tools
(image, video, audio, file) as MCP tools. Credentials are passed via
environment variables set by AMT's mcp_manager when launching the server.

Tools:
    generate_image  — generate an image from a text prompt
    generate_video  — generate a video from a text prompt (async, returns task_id)
    check_video     — poll a video task for completion
    generate_audio  — text-to-speech (TTS)
    transcribe      — speech-to-text (STT)
    generate_file   — create a document file (docx, xlsx, pptx, pdf, py, md, html, ...)

Transport: STDIO. Launched by AMT via the preset (command = python -m media_server).
Env vars (set by AMT):
    AMT_MEDIA_BASE_URL, AMT_MEDIA_API_KEY, AMT_MEDIA_MODEL
    AMT_IMAGE_BASE_URL, AMT_IMAGE_API_KEY, AMT_IMAGE_MODEL
    AMT_VIDEO_BASE_URL, AMT_VIDEO_API_KEY, AMT_VIDEO_MODEL
    AMT_AUDIO_BASE_URL, AMT_AUDIO_API_KEY, AMT_AUDIO_MODEL
    AMT_AUDIO_VOICE_ID
    AMT_PROXY
    AMT_FILES_DIR
"""
__version__ = "1.0.0"
