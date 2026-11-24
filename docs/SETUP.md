# AMT Chat — Setup Guide

## Prerequisites

| Tool | Minimum | Check |
|------|---------|-------|
| Python | 3.12+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

## Step 1: Python backend

```bash
python setup.py
```

This creates `backend/.venv` and installs `requirements.txt` into it.

## Step 2: Node / Electron

```bash
node setup.js
```

This checks Node version and runs `npm install`.

## Step 3: Build (optional — for NSIS installer)

```bash
npm run build:py      # PyInstaller → dist/amt-backend/
npm run build:win     # electron-builder → release/AMT Chat Setup X.Y.Z.exe
```

## Dev mode (no build needed)

```bash
# Terminal 1 — backend
cd backend && .venv\Scripts\python.exe -m uvicorn main:app --port 8000

# Terminal 2 — frontend (browser)
# open http://127.0.0.1:8000

# Or full Electron app:
npm start
```

## Running tests

```bash
npm test              # pytest + node (all)
# or individually:
venv\Scripts\python.exe -m pytest tests/
node tests/run_js_tests.js
```

## Project layout

```
backend/          FastAPI backend + ai_engine/
frontend/         HTML/JS/CSS (vanilla)
electron/         main-process: sidecar.js, ipc.js, preload.js
main.js           Electron entry point
extensions/       extension folders
docs/             BUILD.md, SETUP.md, SECURITY.md, EXTENSIONS.md
tests/            pytest (backend) + node (frontend)
setup.py          Python setup script
setup.js          Node setup script
```
