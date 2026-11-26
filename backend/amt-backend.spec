# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec для AMT backend sidecar (one-dir, быстрее старт чем one-file).
# Собирает FastAPI-бэкенд + ai_engine в каталог dist/backend/amt-backend/.
# Точка входа: backend/main.py (внутри стартует uvicorn на порту из env PORT).
# Frontend + extensions включаются через datas (self-contained бинарник).

import os

block_cipher = None

# Путь до frontend/ и extensions/ относительно backend/
_BACKEND_DIR = os.path.dirname(os.path.abspath(SPEC))
_FRONTEND = os.path.join(_BACKEND_DIR, "..", "frontend")
_EXTENSIONS = os.path.join(_BACKEND_DIR, "..", "extensions")
# Явный distpath: dist/amt-backend (root project). PyInstaller'овский COLLECT
# игнорирует distpath в этом бандле, поэтому бандл реально лежит в root dist/.
# electron-builder выводим в release/ (не в dist/), чтобы не коллизировать.
_DIST = os.path.join(_BACKEND_DIR, "..", "dist")

# Vosk native DLLs (libvosk.dll + runtime deps) — must be bundled
# because PyInstaller's C-extension analysis doesn't always pick them up
# from the venv site-packages.
_VOSK_PKG = os.path.join(
    _BACKEND_DIR, ".venv", "Lib", "site-packages", "vosk"
)

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        # Vosk native DLLs — bundle into _internal/ root so the runtime can find them.
        # PyInstaller binaries format: (abs_source, relative_dest_dir)
        (os.path.join(_VOSK_PKG, _dll), 'vosk')
        for _dll in ["libvosk.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"]
        if os.path.exists(os.path.join(_VOSK_PKG, _dll))
    ],
    datas=[
        # Фронтенд (HTML/CSS/JS) -> _internal/frontend
        (_FRONTEND, os.path.join('frontend')),
        # Расширения (manifest + js + py) -> _internal/extensions
        (_EXTENSIONS, os.path.join('extensions')),
        # Реестр slash-команд -> _internal/command_registry.json
        (os.path.join(_BACKEND_DIR, 'command_registry.json'), '.'),
    ],
    hiddenimports=[
        # uvicorn + httpx ASGI-сервер
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # локальные модули
        'ai_engine', 'ai_engine.memory', 'ai_engine.orchestrator', 'ai_engine.agents',
        'ai_engine.keymanager', 'ai_engine.tools', 'ai_engine.filegen',
        'ai_engine.media', 'ai_engine.extensions', 'ai_engine.sysinteraction',
        'ai_engine.desktop_tools',
        'stt_local', 'vosk',
        # COM/async isolation + browser CDP automation (5-layer resilience fixes)
        'ai_engine.async_utils',
        'ai_engine.browser_cdp',
        # Playwright (CDP connect_over_cdp) — lazy-imported in browser_cdp.py,
        # so PyInstaller static analysis misses it; bundle it explicitly.
        'playwright',
        'playwright.sync_api',
        'playwright._impl',
        'playwright.async_api',
        # тяжёлые генераторы файлов
        'docx', 'openpyxl', 'pptx', 'reportlab', 'markdown', 'pygments',
        # UI Automation (Windows UIA — динамический импорт в desktop_tools.py)
        'comtypes', 'comtypes.client', 'comtypes.server',
        'comtypes._comobject', 'comtypes._enum', 'comtypes._generate',
        'comtypes._util', 'comtypes.automation',
        # MCP (Task 6: mcp_manager.py lazy-imports mcp.client.stdio/streamable_http;
        # the package ships JSON schemas + data files, so use collect_all below)
        'mcp', 'mcp.client', 'mcp.client.stdio', 'mcp.client.streamable_http',
        'mcp.server', 'mcp.shared', 'mcp.server.mcpserver',
        # Локальные tool-calling модули (Task 1, 6)
        'ai_engine.tool_registry', 'ai_engine.mcp_manager',
        # Локальный RAG MCP-сервер (backend/rag_server). Dev: запуск как
        # `python -m rag_server` (loose source). Packaged: бандлер
        # amt-backend.exe в режиме RAG (env AMT_BACKEND_MODE=rag) импортирует
        # rag_server из PYZ-архива (hiddenimports ниже), поэтому `from
        # rag_server.server import main` в entrypoint main.py работает без
        # loose-файлов. Бандлится вместе с backend'ом.
        'rag_server', 'rag_server.server', 'rag_server.engine', 'rag_server.parsers',
    ],
    collect_all=['mcp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='amt-backend',
    debug=False,
    strip=False,
    upx=False,
    console=True,  # остаёмся с консолью для логов/отладки
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='amt-backend',
    **{"distpath": _DIST, "workpath": os.path.join(_DIST, ".pybuild"), "specpath": _BACKEND_DIR},
)
