# AMT Chat

> **Русский:** [README.md](README.md) · **History:** [docs/CHANGELOG.md](docs/CHANGELOG.md) · **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · **Contributing:** [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

**Local AI assistant** — chat with any OpenAI-compatible or local model, generate media/files, agent/skill/persona system, quality orchestrator, long-term memory, safe tools, built-in media player, and extensible plugin system.

Runs **fully locally**: backend — FastAPI (Python), frontend — vanilla JS (no frameworks), shell — Electron. API key and all data stay **on your machine only**.

---

## Features

### Chat & Models

- **Any model** — OpenAI-compatible API (OpenAI, Anthropic, Gemini, local via Ollama/LM Studio) or local. Base URL + key + model. Multi-key with auto-switching on 429 (priority or round-robin).
- **Markdown responses** — rendered in chat.
- **Paste images/screenshots/files** — Ctrl+V, content goes into AI context.
- **Voice chat** — STT + TTS via any provider (Vosk locally or cloud).

### Voice Control

- **Full voice cycle:** wake-word ("Astra" or any phrase) → recording with VAD auto-stop on silence → STT → LLM → TTS + chat.
- **Wake-word** — local Vosk via WebSocket (backend, offline, no API key).
- **STT** — local Vosk (auto-download ~50 MB model on first run) or cloud.
- **TTS** — browser `speechSynthesis` (free) or cloud.
- **Echo protection:** microphone auto-mutes during AI speech.
- **Statuses:** off / listening / recording / processing / responding / speaking.

### Agents, Skills, Personas

- **Agents** — role + system prompt + model/temperature + skill set. Core (Web Agent, Deep Analyst, No Filters) created automatically; custom via UI or `agents.json`/JSONL import.
- **Skills** — reusable instructions, attach to agent or chat separately.
- **Personas** — ready profile (API key + model + agents + skills + orchestrator), created in UI or JSONL import.

### Quality Orchestrator

- **Context control** — history compression when model window overflows.
- **Role drift detection** — tracks model deviation from assigned role.
- **Smart saving** — auto-save chat at message threshold.
- **Monitoring** — latency/errors/average over 100 requests.

### Memory

- **Long-term facts** across chats, auto-injected into system prompt.
- **Limit and cleanup** in "Settings → Memory".

### Media Generation

- **`[[GEN:image|…]]`** — image generation (works with ANY provider via OpenAI-compatible endpoints).
- **`[[GEN:video|…]]`** — video generation (5-min timeout, retry on network error).
- **`[[GEN:audio|…]]`** — audio generation.
- **`[[GEN:file|…]]`** — file generation (xlsx/docx/pptx). AI sees data, not "binary file".
- **Auto-detect Agnes** by `base_url` — enables Agnes-specific parameters.

### Safe Tools (Tool-Calling)

- **Read/write files, create folders, list directories, run commands** — only in selected "working folder" (project).
- **Write/commands require confirmation** (auto-approve off by default).
- **Commands — only from whitelist.**
- **All actions logged.**

### Native Tool-Calling

- When `toolCalling` enabled (on by default), model receives JSON tool schemas and emits `tool_calls`; backend executes via `ToolRegistry` and returns results to model (up to 5 iterations).
- **Built-in tools:** image/video/audio/file generation (`generate_image`, `generate_video`, `generate_audio`, `generate_file`).
- **`[[GEN]]` tokens** — fallback for providers without tool-calling support.

### MCP Servers

- **Connect external MCP servers** (STDIO processes or HTTP endpoints).
- Their tools (`mcp__<server>__<tool>`) automatically appear in available model tools.
- **Server env vars encrypted with Fernet** (`mcp_key.key`).
- **MCP tools require confirmation by default** (`auto_approve=False`).
- **Management:** "Settings → MCP Servers" + "Storage".
- **Built-in presets:**
  - **RAG** — knowledge base (folder indexing, semantic BM25 search, no heavy deps)
  - **media** — media generation
  - **writer** — file generation
  - **coding** — read-only project diagnostics

### Slash Commands

- **15 commands** (`/rag`, `/agent`, `/jailbreak`, `/gen`, `/nav_*`, `/help`, etc.) — one-request overlay, combine with `+`, context discarded after execution.
- Registry in `backend/command_registry.json`, parser in `command_engine.py`.

### Structured Logs

- **JSONL in `backend/logs/`** with trace_id correlation.
- **"Structure" dashboard:** 4 widgets + filterable table with auto-refresh.

### Hotkeys

- **12 available** (navigation, agent toggle, quick generation), configurable in "Settings → Hotkeys".

### Media Player

- **YouTube/Twitch embeds**, direct `.mp4`/`.m3u8`, photos, audio — play in chat/player.
- **Fullscreen**, filters (brightness/contrast/detail/noise/enhance).
- **Sites blocking iframes** (X-Frame-Options) — open in built-in frameless browser.
- **`[[SCREENSHOT:url]]`** — real page screenshot via Electron `capturePage`, not og:image.

### Extensions

- **Folders in `extensions/`** with `manifest.json` (+ optional `index.js`, `backend.py`) — no recompile.
- Management: "Help → Extensions" (enable/disable/add/refresh).

### Storage

- **View and export** all data (agents/skills/keys/themes/extensions/chat).

### Themes

- **30 built-in themes + editor** (gradient, font, background, UI language RU/EN).
- **Theme editor** with group preview (colors, surfaces, fields and controls).

### Logs

- **Event dashboard** for API/orchestrator/tools with filters.

### Desktop

- **Electron + built-in Python backend** (sidecar, PyInstaller).
- **NSIS installer** for Windows.

---

## Quick Install (No Build)

One file — ready to go. Download `AMT Chat Setup 1.1.3.exe` from [GitHub Releases](https://github.com/clashssd/AMT/releases) and run the installer. No need to install Python, Node.js, or other dependencies — all included.

After install: **Settings → Connection** — enter API key, start chat.

> **Windows SmartScreen** will show "publisher couldn't be verified" — this is normal: AMT Chat isn't signed with a paid code-signing cert. Click "More info" → "Run anyway". Or run the portable copy `AMT Chat 1.1.3 portable (win-unpacked).exe` — it doesn't go through NSIS, so SmartScreen won't block it.

---

## Build from Source

### One Step (Recommended)

```powershell
git clone https://github.com/clashssd/AMT.git
cd AMT
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_and_build.ps1
```

The `bootstrap_and_build.ps1` script, without your involvement:

1. Checks if **Python 3.12+** and **Node.js** are installed; installs missing ones via `winget`.
2. Creates local environment `backend/.venv` and installs Python dependencies.
3. Installs Node dependencies.
4. Builds ready `AMT Chat.exe` (portable) and `AMT Chat Setup <version>.exe` (NSIS installer).
5. Applies icon patch to ready `.exe` (workaround for known electron-builder 25.1.8 bug).

Result (~5–10 minutes):

- `release\win-unpacked\AMT Chat.exe` — portable copy, run immediately.
- `release\AMT Chat Setup <version>.exe` — classic installer.

### Manual Build (Dev / CI)

```bash
python setup.py        # creates backend/.venv + installs deps
node setup.js          # npm install
npm run build:all      # PyInstaller -> dist/, then electron-builder -> release/
node scripts/patch_exe_icon.js   # icon bug workaround
```

See `docs/BUILD.md`, `docs/SETUP.md`.

---

## Quick Start (Dev, Browser)

Backend serves frontend via `StaticFiles`:

```bash
python -m venv backend/.venv
backend\.venv\Scripts\pip install -r requirements.txt pyinstaller
cd backend && ..\.venv\Scripts\uvicorn main:app --port 8000
```

Open `http://127.0.0.1:8000`. Enable API key in "Settings → Connection".

> **Backend tests:** `backend\.venv\Scripts\python.exe -m pytest tests/`

## Desktop (Electron)

```bash
npm install            # installs electron + electron-builder
npm start              # launches Electron: starts Python backend, opens window
```

Electron finds `backend/.venv/Scripts/python.exe` (or use `AMT_PYTHON`). Backend starts on `127.0.0.1:8000`, frontend loads from this URL.

Window is frameless: custom titlebar drawn in HTML follows active app theme; native Windows title bar not shown.

---

## Project Structure

```
main.js               Electron main process (frameless-window, sidecar, IPC)
electron/             sidecar.js, ipc.js, preload.js, secrets.js
backend/              FastAPI backend
  main.py             API entry points + StaticFiles serving;
                      entrypoint with AMT_BACKEND_MODE (rag|media|writer|coding)
  stt_local.py        local Vosk-STT: wake-word, batch recognition
  ai_engine/          agents.py, orchestrator.py, memory.py, media.py,
                      tools.py, web_scraper.py, keymanager.py,
                      extensions.py, filegen.py, sysinteraction.py,
                      tool_registry.py, mcp_manager.py, desktop_tools.py,
                      browser_cdp.py, coding_tools.py, async_utils.py
  command_engine.py   slash-command parsing and execution
  logging_structured.py  JSONL logs with trace_id
  coding_mcp_server.py   coding-MCP (read-only project diagnostics)
  rag_server/         local knowledge base (index + BM25 search)
  media_server/       media generation as MCP server
  writer_server/      file generation as MCP server
  agents.json         seed agent/skill core (created on startup)
  keys.json           your API keys (empty template, not committed)
  settings.json       orchestrator config
  mcp_servers.json    external MCP servers
frontend/             HTML/JS/CSS (vanilla, no frameworks)
  home.html           main UI (SPA)
  js/                 main.js and helper modules
                      voice.js (voice: state machine, wake-word, VAD, STT, TTS)
  css/                style.css, tokens.css, components-v2.css,
                      commands.css, voice.css, motion-v2.css
  assets/             icons, images
  themes.json         30 built-in themes
extensions/           extension folders (example: extensions/example)
docs/                 CHANGELOG.md, ARCHITECTURE.md, BUILD.md,
                      EXTENSIONS.md, SECURITY.md, SETUP.md, CONTRIBUTING.md,
                      COMMANDS_SYSTEM_DETAILED.md
tests/                pytest (backend) + node (frontend modules)
scripts/              build.js, bootstrap_and_build.ps1, patch scripts
```

Full description — `docs/ARCHITECTURE.md`.

---

## Extensions

Create folder `extensions/name/` with `manifest.json`, optionally `backend.py` (Python, `init(ctx)`) and `index.js` (frontend, `init(ctx)` + `ctx.ui.registerPage`). Restart app or click "Refresh list".

See `docs/EXTENSIONS.md` and in-app: "Help → How to Write" (full guide with templates).

---

## Agents, Skills, Personas

Full guide — in-app: "Help → How to Write" and "Settings → Docs — examples and reference" (copyable examples).

- **Agent** = role + system prompt + (opt.) model/temperature/skills. Created in UI ("Settings → Agents/Skills") or import `{"agents":[…]}` / JSONL.
- **Skill** = ready instruction. Same — `{"skills":[…]}`.
- **Persona** = profile (key + model + agents + skills + orchestrator). Created in UI ("Settings → Persona") or JSONL import.

## Slash Commands

See `docs/COMMANDS_SYSTEM_DETAILED.md`. 15 commands, parser in `command_engine.py`, registry in `command_registry.json`. Combine with `+`, context discarded after execution.

## Security

See `docs/SECURITY.md`. AI executes nothing without permission: write/commands require confirmation, commands — only from whitelist, files — only in allowed directories (project). All actions logged. API keys stored locally (encrypted `SecureStore` on frontend, `secrets.bin` on Electron); `backend/keys.json` — empty template, not committed. MCP server env vars encrypted with Fernet (`mcp_key.key`).

---

## Tests

```bash
npm test               # pytest + node (all)
# or separately:
backend\.venv\Scripts\python.exe -m pytest tests/
node tests/run_js_tests.js
```

---

## License

See `LICENSE` file (MIT). Extensions, keys, and data you add are licensed by you.

---

## Documentation

- **[docs/CHANGELOG.md](docs/CHANGELOG.md)** — version history from 1.0.0 to 1.1.3.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — components, processes, directory tree, lifecycle.
- **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** — how to build, test, contribute.
- **[docs/BUILD.md](docs/BUILD.md)** — detailed build (PyInstaller, electron-builder, NSIS).
- **[docs/SETUP.md](docs/SETUP.md)** — dependency setup, environment.
- **[docs/EXTENSIONS.md](docs/EXTENSIONS.md)** — extension system, `manifest.json`, `init(ctx)`.
- **[docs/SECURITY.md](docs/SECURITY.md)** — security model: key encryption, whitelists, audit.
- **[docs/COMMANDS_SYSTEM_DETAILED.md](docs/COMMANDS_SYSTEM_DETAILED.md)** — slash-command architecture, registry, parser.
- **[docs/BRAND.md](docs/BRAND.md)** — design tokens (5 colors, font, shape, motif).
