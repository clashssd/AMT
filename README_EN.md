# AMT Chat

![icon](frontend/assets/icon.svg)

> **РУССКИЙ:** [README.md](README.md)
>
> A local (desktop) AI assistant: chat with any OpenAI-compatible or local
model, media and file generation, an **agents / skills / personas** system,
a quality **orchestrator**, long-term **memory**, safe **tools**
(files/commands), a built-in **media player**, and an extensible
**plugin system**. Runs entirely locally: FastAPI (Python) backend,
vanilla JS frontend (no frameworks), Electron shell. Your API key and
all data stay on your machine.

## Philosophy

- **Your data stays yours.** AMT does not collect, store or send your chats,
  API keys, or generated files anywhere. Everything lives locally on your
  machine. Closing the app = closing access to your data.
- **Open source, forever.** Code, docs, and all build tooling are published
  under the MIT license. Forks, modifications, and reinterpretations are
  welcome — the project is open to any developer.
- **Easy to read and understand.** No frameworks, no layers of abstraction,
  no magical dependencies. Frontend is vanilla JS, backend is FastAPI in
  plain Python. Anyone who can follow the code at a "I understand what's
  happening here" level can safely modify the project for their own use.
- **Extend any part.** Extensions (folders in `extensions/`), agents,
  skills, personas, media providers, tools — everything extends without
  recompilation. Drop in your own `backend.py` / `index.js` and it plugs
  into the app.
- **Safe storage by default.** Writes/commands require confirmation,
  commands only from a whitelist, files only inside the project working
  folder. API keys are encrypted in the local `SecureStore`. Everything the
  app does is logged — and visible in "Help → Logs".

## About the Project

AMT is a desktop chat client that **you** control. There is no cloud, no
account, no telemetry: only your API key (or a local model) and your local
files. This is not "another AI chat" — it is a construction kit in which
you assemble agents, skills, and extensions for your own tasks and keep
them in your own repository.

> This is the **first official release (1.0.0)**. Full feature list and
> how everything works — in `README.md#features` and in-app:
> "Help → About", "Help → How to write", "Help → Updates" (v1.0.0).

## Features

- **Chat** — any OpenAI-compatible API or local model (Base URL + key +
  model). Multi-key with auto-failover on 429 (by priority or round-robin).
  Markdown responses. Paste images/screenshots/files (Ctrl+V) — content
  goes into the AI context. Voice chat: STT + TTS via any provider.
- **Voice control** — full voice loop: wake-word ("Астра" or any phrase) ->
   VAD recording with auto-stop on silence -> STT -> LLM -> TTS + chat. The
   wake-word is detected by a local Vosk over WebSocket (backend, offline,
   no API key); STT is local Vosk or any OpenAI-compatible cloud; TTS is
   browser `speechSynthesis` (free) or cloud. The mic is auto-muted while the
   AI speaks (echo protection). A mic button sits in the composer menu
   (states: off / listening / recording / processing / responding / speaking).
   Settings: "Settings -> Voice" (wake-word, silence timer, sensitivity) and
   "Settings -> Providers" (STT/TTS, keys, URLs). All API keys are stored
   encrypted in `secrets.bin` (Electron safeStorage/DPAPI), never in
   `settings.json`.
- **Agents** — role + system prompt + model/temperature + skill set.
  Core agents (Web Agent, Deep Analyst, No Filters) are auto-created;
  custom agents via UI or import from `agents.json`/JSONL.
- **Skills** — reusable instructions, attach to an agent or use in chat
  independently.
- **Personas** — ready-made profile (API key + model + agents + skills +
  orchestrator), created in UI or imported via JSONL (one session per line).
- **Orchestrator** — context management (history compression when the model
  window overflows), role-drift control, smart chat auto-save by message
  threshold, monitoring (latency/errors/avg over 100 requests).
  Configured in "Settings → Orchestrator".
- **Memory** — long-term facts across chats, automatically injected into
  the system prompt; limit and clearing in "Settings → Memory".
- **Media generation** — `[[GEN:image|…]]`, `[[GEN:video|…]]`,
  `[[GEN:audio|…]]`, `[[GEN:file|…]]` — the AI inserts a ready element
  (image/video/audio/file) directly into the message; works with ANY
  provider via OpenAI-compatible endpoints, not just OpenAI. Files
  (xlsx/docx/pptx): the backend opens the real file, the AI sees the data,
  not a "binary file".
- **Safe tools (tool-calling)** — file read/write, folder creation,
  directory listing, command execution — only within the selected
  "working folder" (project). Write/commands require confirmation
  (auto-approve off by default); commands only from a whitelist.
  Everything is logged.
- **Native tool-calling** — when `toolCalling` is enabled (on by
   default), the model receives JSON tool schemas and emits `tool_calls`
   itself; the backend executes them via the `ToolRegistry` and returns
   results to the model (up to 5 iterations). Built-in tools: image /
   video / audio / file generation (`generate_image`, `generate_video`,
   `generate_audio`, `generate_file`). `[[GEN]]` tags are kept as a
   fallback for providers that don't support tool-calling.
- **MCP servers** — connect external MCP servers (STDIO processes or
   HTTP endpoints). Their tools (prefix `mcp__<server>__<tool>`) are
   automatically available to the model. Server env vars are encrypted
   with Fernet (`mcp_key.key`); MCP tools require confirmation by
   default (`auto_approve=False`). Manage: "Settings → MCP servers" +
   "Storage".
- **Media player** — YouTube/Twitch embeds, direct `.mp4`/`.m3u8`,
  photos, audio — plays in chat/player, fullscreen, filters
  (brightness/contrast/detail/noise/enhance). Sites that block iframes
  (X-Frame-Options) open in a built-in frameless browser.
  `[[SCREENSHOT:url]]` — real page screenshot via Electron `capturePage`,
  not og:image.
- **Extensions** — folders in `extensions/` with `manifest.json`
  (+ optional `index.js`, `backend.py`) — no app recompile needed.
  Manage: "Help → Extensions" (enable/disable/add/refresh list).
- **Storage** — view and export all data (agents/skills/keys/themes/
  extensions/chat).
- **Logs** — event dashboard for API/orchestrator/tools with filters.
- **Themes** — presets + custom (gradient), font and background,
  UI language (RU/EN).
- **Desktop** — Electron + bundled Python backend (sidecar, PyInstaller),
  NSIS installer for Windows.

##  Quick install (no build required)

**One file — and you're done.** Run `AMT Chat Setup 1.0.8.exe` from the
`release/` folder and follow the installer wizard. No need to install
Python, Node.js, or any other dependencies — everything is bundled in the
installer.

```
release/AMT Chat Setup 1.0.8.exe
```

After installation: **Settings → Connection** — enter your API key, start
chatting.

> Pre-built ZIP: `release/AMT-Chat-Setup-1.0.8.zip` (~175 MB). Extract and
> run `AMT Chat Setup 1.0.8.exe` — installation completes in ~2 minutes.

## How to install (for end users, no manual dependencies)

**Recommended — one command.** No need to download a large .exe or
manually install Python/Node — just clone the source and run one script;
it sets up everything else and builds the ready-to-use app:

```powershell
git clone https://github.com/clashssd/AMT.git
cd AMT
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_and_build.ps1
```

The `bootstrap_and_build.ps1` script, automatically, without your input:
1. Checks if **Python 3.12+** and **Node.js** are installed; installs any
   missing via `winget` (standard Windows 10/11 package manager, already
   present on the system; on very old/minimal setups without winget —
   install them manually, see `docs/SETUP.md`).
2. Creates a local `backend/.venv` and installs Python dependencies.
3. Installs Node dependencies.
4. Builds `AMT Chat.exe` (portable) and `AMT Chat Setup <version>.exe`
   (NSIS installer) — this is the installer you can run as a regular
   Windows application.
5. Applies the icon patch to the built `.exe` (workaround for a known
   electron-builder 25.1.8 bug that silently skips custom icons on this
   stack).

Result (after ~5-10 minutes):
- `release\win-unpacked\AMT Chat.exe` — portable copy, run directly,
  no install needed.
- `release\AMT Chat Setup <version>.exe` — classic installer; run it and
  the app installs as a regular Windows application (desktop shortcut,
  "Uninstall" entry in "Settings → Apps").

> Why not "just download the ready .exe from the release": the installer
> is ~130 MB — this exceeds GitHub's hard limit for a single file in a
> normal `git push` (~100 MB), so the `.exe` is **not committed** to the
> repo (see `.gitignore`). If you have a ready `AMT Chat Setup.exe` from
> the developer (e.g. passed as a file), just run it — it's the same app
> built by the same pipeline.

### For developers / CI (rebuild from scratch without the script)

If you need to build manually, without `bootstrap_and_build.ps1`:

```bash
python setup.py        # creates backend/.venv + installs dependencies
node setup.js          # npm install
npm run build:all      # PyInstaller -> dist/, then electron-builder -> release/
node scripts/patch_exe_icon.js   # icon bug workaround (see above)
```

See `docs/BUILD.md`, `docs/SETUP.md` for details.

## Project structure

```
main.js               Electron main process (frameless window, sidecar, IPC)
electron/             sidecar.js, ipc.js, preload.js
backend/              FastAPI backend
  main.py             API entry points + StaticFiles frontend serving
  ai_engine/          agents.py, orchestrator.py, memory.py, media.py,
                      tools.py, web_scraper.py, keymanager.py,
                       extensions.py, filegen.py, sysinteraction.py,
                       tool_registry.py, mcp_manager.py,
                       desktop_tools.py, browser_cdp.py, async_utils.py
  agents.json         seed agents/skills core (created on startup)
  keys.json           your API keys (empty template, not committed)
  settings.json       orchestrator config
  mcp_servers.json  external MCP servers (created on add)
  changelog.json      version history (shown in "Help → Updates")
frontend/             HTML/JS/CSS (vanilla, no frameworks)
  home.html           main UI (SPA)
  js/                 main.js and helper modules
  css/style.css       styles
  assets/icon.svg     app icon (source), favicon.ico (generated)
extensions/           extension folders (example: extensions/example)
docs/                 EXTENSIONS.md, BUILD.md, SECURITY.md, SETUP.md
tests/                pytest (backend) + node (frontend modules)
```

## Quick start (dev, in browser)

The backend serves the frontend via `StaticFiles`, so all you need is:

```bash
# Python 3.12+ and Node.js installed
python -m venv backend/.venv
backend/.venv\Scripts\pip install -r requirements.txt pyinstaller
cd backend && ..\.venv\Scripts\uvicorn main:app --port 8000
```

Open `http://127.0.0.1:8000`. Enable your API key in "Settings →
Connection".

> Backend tests: `backend\.venv\Scripts\python.exe -m pytest tests/`.

## Desktop (Electron)

```bash
npm install            # installs electron + electron-builder
npm start              # launches Electron: starts Python backend, opens window
```

Electron finds `backend/.venv/Scripts/python.exe` (or use `AMT_PYTHON`).
The backend starts on `127.0.0.1:8000`, the frontend loads from this URL —
all `fetch` calls work without changes.

The window is frameless: a custom titlebar (drag, min/max/close buttons)
is drawn in HTML and follows the active app theme; the native grey
Windows titlebar is not shown.

## Build (distribution)

See `docs/BUILD.md` and `docs/SETUP.md`. Quick reference:

```bash
npm run build:py       # PyInstaller: backend -> dist/amt-backend/ (sidecar bundle)
npm run build:win      # electron-builder: NSIS installer -> release/
# or all at once:
npm run build:all      # node scripts/build.js all
```

Result: `release/AMT Chat Setup <version>.exe` (version from `package.json`).
electron-builder copies `dist/amt-backend/` into `extraResources`,
uses `frontend/assets/favicon.ico` (generated from
`frontend/assets/icon.svg`) as the exe/installer icon.

## Extensions

See `docs/EXTENSIONS.md` and in-app: "Help → How to write" (full guide
with templates) and "Help → Extensions" (management hub). Quick: create
a folder `extensions/name/` with `manifest.json`, optionally `backend.py`
(Python, `init(ctx)`) and `index.js` (frontend, `init(ctx)` +
`ctx.ui.registerPage`). Restart the app or click "Refresh list".

## Agents, skills, orchestrator, personas

Full guide with templates and setup methods (UI / JSON/JSONL import) —
in-app: "Help → How to write" and "Settings → Docs — examples and reference"
(copyable examples). Quick:

- Agent = role + system prompt + (opt.) model/temperature/skills. Created
  in UI ("Settings → Agents/Skills") or imported via `{"agents":[…]}` / JSONL.
- Skill = ready instruction. Same — `{"skills":[…]}`.
- Persona = profile (key + model + agents + skills + orchestrator). Created
  in UI ("Settings → Persona") or imported via JSONL (one per line).
- Orchestrator — configured in UI ("Settings → Orchestrator"), not an
  importable "file" — parameters (`enabled`, `auto_mode`,
  `role_drift_check`, `monitor_latency`, `auto_save_threshold`,
  `keep_full_context`).

## Security

See `docs/SECURITY.md`. The AI executes nothing without permission:
writes/commands require confirmation, commands only from a whitelist,
files only in allowed directories (project). Every action is logged.
API keys stored locally (encrypted `SecureStore` on the frontend);
`backend/keys.json` is an empty template and not committed.

## Tests

```bash
npm test               # pytest + node (all)
# or individually:
backend\.venv\Scripts\python.exe -m pytest tests/
node tests/run_js_tests.js
```

## License

See `LICENSE` (MIT). Extensions, keys, and data you add yourself are
licensed by you.
