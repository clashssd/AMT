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

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Фронтенд (HTML/CSS/JS) -> _internal/frontend
        (_FRONTEND, os.path.join('frontend')),
        # Расширения (manifest + js + py) -> _internal/extensions
        (_EXTENSIONS, os.path.join('extensions')),
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
        # тяжёлые генераторы файлов
        'docx', 'openpyxl', 'pptx', 'reportlab', 'markdown', 'pygments',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'PIL.Image'],
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
