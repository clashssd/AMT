# backend/ai_engine/mcp_manager.py
from __future__ import annotations
import asyncio, json, logging, os, stat, platform, subprocess
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from cryptography.fernet import Fernet

log = logging.getLogger(__name__)

SERVERS_FILE = "mcp_servers.json"
KEY_FILE = "mcp_key.key"
MCP_TOOL_TIMEOUT = 30.0


def _stdio_client(cfg: MCPServerConfig):
    """Return an async context manager that yields (read, write, session) for a STDIO MCP server.

    Sets `cwd` to the command's directory when the command is a path to an
    executable. This is required for frozen PyInstaller onedir apps (e.g. the
    AMT sidecar `amt-backend.exe` launched in RAG mode): the bootloader
    resolves its `_internal/` resources relative to the process working
    directory, so a wrong cwd makes the child fail to find its bundled
    modules and exit immediately — which surfaces on the client side as
    "Connection closed".
    """
    from mcp.client.stdio import stdio_client, StdioServerParameters
    cwd = None
    if cfg.command:
        # Only treat as a path when it looks like an absolute file path (not a
        # bare interpreter like "python" / "npx" / "uv").
        candidate = os.path.expandvars(cfg.command)
        if os.path.isabs(candidate) or os.path.sep in candidate:
            d = os.path.dirname(candidate)
            if d and os.path.isdir(d):
                cwd = d
    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args,
        env={**os.environ, **cfg.env},
        cwd=cwd,
    )
    return stdio_client(params)


def _http_client(cfg: MCPServerConfig):
    """Return an async context manager that yields (read, write, session) for an HTTP MCP server."""
    from mcp.client.streamable_http import streamable_http_client
    return streamable_http_client(cfg.url, headers=cfg.headers)

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


@dataclass
class _SessionHolder:
    """Holds an open MCP session + the async CMs that keep it alive."""
    session: Any = None
    cm_outer: Any = None   # client CM (stdio/http) — must be exited last
    cm_inner: Any = None   # ClientSession CM (mcp v2) — exit before outer
    proc: Any = None       # subprocess handle, if discoverable


def _find_proc(read, write):
    """Best-effort discovery of the underlying subprocess handle."""
    for cand in (read, write):
        if cand is None:
            continue
        for attr in ("_proc", "process", "transport"):
            v = getattr(cand, attr, None)
            if v is not None and hasattr(v, "pid"):
                return v
    return None


async def _teardown(holder: _SessionHolder) -> None:
    """Close CMs in reverse order (inner session first, then outer client).

    anyio task groups can't always be exited from a different task than they
    were entered in (we scheduled teardown off the connect task); that error is
    benign because the subprocess is terminated separately. Downgrade it to
    debug; log everything else as a warning.
    """
    async def _close(cm, label):
        ex = getattr(cm, "__aexit__", None)
        if ex is None:
            return
        try:
            result = ex(None, None, None)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            msg = str(e)
            if "different task" in msg or "cancel scope" in msg:
                log.debug("MCP %s teardown skipped (cross-task anyio scope): %s", label, msg)
            else:
                log.warning("MCP %s teardown error: %s", label, msg)

    await _close(holder.cm_inner, "inner")
    await _close(holder.cm_outer, "outer")
    proc = holder.proc
    if proc is not None and getattr(proc, "returncode", None) is None:
        try:
            proc.terminate()
            if platform.system() == "Windows" and getattr(proc, "pid", None):
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, timeout=5)
        except Exception as e:
            log.warning("MCP proc teardown error: %s", e)

class MCPManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.servers_file = os.environ.get("AMT_MCP_SERVERS_FILE", os.path.join(data_dir, SERVERS_FILE))
        self.key_file = os.environ.get("AMT_MCP_KEY_FILE", os.path.join(data_dir, KEY_FILE))
        self._fkey = self._load_or_create_key()
        self.servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, Any] = {}   # server_id -> _MCPClient
        self._procs: dict[str, Any] = {}      # server_id -> asyncio.subprocess.Process (STDIO)
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

    # ---- Connection lifecycle ----
    #
    # The mcp SDK's stdio_client()/streamable_http_client() are *factories* that
    # return an async context manager. In mcp v2 they yield a 2-tuple
    # (read_stream, write_stream); the ClientSession is a *second* async CM that
    # must be entered to start its JSON-RPC dispatcher task group. Both CMs
    # must stay open for the session to work. We enter both, store them in a
    # _SessionHolder, and exit them in reverse on disconnect/shutdown.
    #
    # Tests inject a mock CM that already carries a `_session` attribute; we
    # store it directly with no CM to exit.

    async def connect(self, server_id: str) -> None:
        cfg = self.servers.get(server_id)
        if cfg is None:
            raise ValueError(f"Server '{server_id}' not found")
        if server_id in self._clients:
            return  # already connected

        if cfg.transport == "stdio":
            cm = _stdio_client(cfg)  # may be patched (test) to return an AsyncMock
        elif cfg.transport == "http":
            cm = _http_client(cfg)
        else:
            raise ValueError(f"Unknown transport: {cfg.transport}")

        # Fast-path: test mock CM already carries a `_session`. No CM to hold open.
        if hasattr(cm, "_session"):
            self._clients[server_id] = _SessionHolder(session=cm._session,
                                                       cm_outer=None, cm_inner=None, proc=None)
            self._procs[server_id] = None
            log.info("MCP server '%s' connected (%s, mock)", server_id, cfg.transport)
            return

        # Real SDK path. Manually ENTER the async CMs (not via `async with`) so
        # they stay open until disconnect/shutdown calls __aexit__. stdio_client()
        # and ClientSession() are both async context managers.
        outer_cm = cm
        holder = _SessionHolder(cm_outer=outer_cm)
        payload = await outer_cm.__aenter__()

        if hasattr(payload, "call_tool") and hasattr(payload, "list_tools"):
            # A ready session was yielded (v1 3-tuple w/ session, or a mock).
            holder.session = payload
            holder.proc = None
            self._clients[server_id] = holder
            self._procs[server_id] = None
            log.info("MCP server '%s' connected (%s, ready session)", server_id, cfg.transport)
            return
        try:
            read, write, _maybe = payload  # v1 3-tuple
            holder.session = _maybe if _maybe is not None else None
            holder.proc = _find_proc(read, write)
            if holder.session is None:
                raise RuntimeError("3-tuple CM yielded no session")
            self._clients[server_id] = holder
            self._procs[server_id] = holder.proc
            log.info("MCP server '%s' connected (%s, v1)", server_id, cfg.transport)
            return
        except (TypeError, ValueError):
            read, write = payload  # v2 2-tuple
            from mcp import ClientSession
            inner_cm = ClientSession(read, write)
            holder.cm_inner = inner_cm
            holder.proc = _find_proc(read, write)
            s = await inner_cm.__aenter__()
            try:
                await s.initialize()
            except Exception:
                pass  # some builds auto-init on first RPC
            holder.session = s

        self._clients[server_id] = holder
        self._procs[server_id] = holder.proc
        log.info("MCP server '%s' connected (%s)", server_id, cfg.transport)

    async def disconnect(self, server_id: str) -> None:
        holder = self._clients.pop(server_id, None)
        if holder is None:
            return
        await _teardown(holder)
        self._procs.pop(server_id, None)

    def _get_session(self, server_id: str):
        holder = self._clients.get(server_id)
        if holder is None:
            return None
        # New _SessionHolder carries `.session`. Legacy test objects (AsyncMock
        # with `._session`) carry `_session`. `_SessionHolder` has no `_session`,
        # so check the holder attribute first, then the legacy convention.
        if isinstance(holder, _SessionHolder):
            return holder.session
        s = getattr(holder, "_session", None)
        if s is None:
            s = getattr(holder, "session", None)
        return s

    @staticmethod
    def _proc_of(holder):
        """Return the subprocess handle for a stored client (holder or legacy)."""
        if isinstance(holder, _SessionHolder):
            return holder.proc
        return getattr(holder, "_proc", None) or getattr(holder, "proc", None)

    async def list_tools(self, server_id: str) -> list[dict]:
        session = self._get_session(server_id)
        if session is None:
            await self.connect(server_id)
            session = self._get_session(server_id)
        if session is None:
            return []
        result = await session.list_tools()
        # MCP SDK returns an object with .tools; tests may return a plain dict.
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result
        else:
            tools = getattr(result, "tools", [])
        out = []
        for t in tools:
            name = t.name if hasattr(t, "name") else t.get("name", "")
            desc = t.description if hasattr(t, "description") else t.get("description", "")
            # mcp v1 exposes `inputSchema` (camelCase); mcp v2 exposes
            # `input_schema` (snake_case). Accept both, plus plain dicts.
            schema = None
            for attr in ("inputSchema", "input_schema"):
                schema = getattr(t, attr, None)
                if schema is not None:
                    break
            if schema is None and isinstance(t, dict):
                schema = t.get("inputSchema") or t.get("input_schema") or {}
            out.append({"name": name, "description": desc or "", "inputSchema": schema or {}})
        return out

    async def call_tool(self, server_id: str, tool: str, args: dict) -> str:
        session = self._get_session(server_id)
        if session is None:
            await self.connect(server_id)
            session = self._get_session(server_id)
        if session is None:
            return json.dumps({"error": f"MCP server '{server_id}' not connected"}, ensure_ascii=False)

        try:
            result = await asyncio.wait_for(
                session.call_tool(tool, args),
                timeout=MCP_TOOL_TIMEOUT,
            )
            if hasattr(result, "content") and result.content:
                parts = [b.text for b in result.content if hasattr(b, "text")]
                return json.dumps({"result": "\n".join(parts)}, ensure_ascii=False)
            return json.dumps({"result": str(result)}, ensure_ascii=False)
        except asyncio.TimeoutError:
            return json.dumps({"error": f"MCP tool call timed out after {int(MCP_TOOL_TIMEOUT)}s"}, ensure_ascii=False)
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
        """Tear down all open sessions. Sync-safe (atexit): terminates the
        subprocess and schedules CM teardown on the running loop if one exists,
        otherwise closes streams inline (best effort)."""
        for sid in list(self._clients.keys()):
            holder = self._clients.pop(sid, None)
            self._procs.pop(sid, None)
            if holder is None:
                continue
            proc = self._proc_of(holder)
            if proc is not None and getattr(proc, "returncode", None) is None:
                try:
                    proc.terminate()
                    if platform.system() == "Windows" and getattr(proc, "pid", None):
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                       capture_output=True, timeout=5)
                except Exception as e:
                    log.warning("MCP shutdown '%s' proc error: %s", sid, e)
            # Schedule async CM teardown if a loop is running; else inline-close.
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._teardown_holder(sid, holder))
            except RuntimeError:
                # No loop (atexit on a sync thread). Close streams best-effort.
                self._teardown_nowait(holder)
            log.info("MCP server '%s' shut down", sid)

    @staticmethod
    def _as_holder(stored) -> _SessionHolder:
        """Coerce a stored client (new holder or legacy mock) into a holder so
        teardown can read its CMs/proc uniformly."""
        if isinstance(stored, _SessionHolder):
            return stored
        return _SessionHolder(
            session=getattr(stored, "_session", None),
            cm_outer=None,
            cm_inner=None,
            proc=getattr(stored, "_proc", None),
        )

    async def _teardown_holder(self, sid: str, holder: _SessionHolder) -> None:
        try:
            await _teardown(self._as_holder(holder))
        except Exception as e:
            log.warning("MCP async teardown '%s' error: %s", sid, e)

    def _teardown_nowait(self, holder: _SessionHolder) -> None:
        h = self._as_holder(holder)
        for cm in (h.cm_inner, h.cm_outer):
            # Without a running loop we can't await async CM exits; the
            # subprocess was already terminated, so just drop references.
            del cm


# Module-level singleton (initialized lazily in main.py)
mcp_manager: Optional[MCPManager] = None
