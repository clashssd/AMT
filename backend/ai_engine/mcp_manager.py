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
    """Return an async context manager that yields (read, write, session) for a STDIO MCP server."""
    from mcp.client.stdio import stdio_client, StdioServerParameters
    params = StdioServerParameters(
        command=cfg.command,
        args=cfg.args,
        env={**os.environ, **cfg.env},
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
    # return an async context manager. We enter the CM, keep the yielded session
    # in self._clients, and remember the CM so we can re-enter it for teardown
    # on disconnect/shutdown. Tests inject a plain AsyncMock where `connect`
    # simply stores it; the SDK CM machinery is exercised only on real connect.

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

        # SDK CM factory yields (read, write, session). Tests inject a mock that
        # already carries a `_session` attribute; we store it directly. Real SDK
        # CMs don't have `_session` — enter them and keep the yielded session.
        if hasattr(cm, "_session"):
            session = cm._session
            self._clients[server_id] = {"session": session, "cm": None, "proc": None}
            self._procs[server_id] = None
        else:
            async with cm as payload:
                read, write, session = payload
                proc = getattr(read, "_proc", None) or getattr(write, "_proc", None) or getattr(read, "process", None)
                self._clients[server_id] = {"session": session, "cm": cm, "proc": proc}
                self._procs[server_id] = proc

        log.info("MCP server '%s' connected (%s)", server_id, cfg.transport)

    async def disconnect(self, server_id: str) -> None:
        entry = self._clients.pop(server_id, None)
        if entry is None:
            return
        cm = entry.get("cm")
        if cm is not None and hasattr(cm, "__aexit__"):
            try:
                await cm.__aexit__(None, None, None)
            except Exception as e:
                log.warning("MCP disconnect '%s' error: %s", server_id, e)
        self._procs.pop(server_id, None)

    def _get_session(self, server_id: str):
        entry = self._clients.get(server_id)
        if entry is None:
            return None
        # connect() stores a dict {"session":...}; tests may store the client object
        # directly (with a `_session` attribute, matching the mcp SDK session name).
        if isinstance(entry, dict):
            return entry.get("session")
        # Prefer the explicit `_session` convention (test + SDK), then `session`.
        s = getattr(entry, "_session", None)
        if s is None:
            s = getattr(entry, "session", None)
        return s

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
            schema = t.inputSchema if hasattr(t, "inputSchema") else t.get("inputSchema", {})
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
        for sid in list(self._clients.keys()):
            entry = self._clients.pop(sid, None)
            if entry is None:
                continue
            proc = self._procs.pop(sid, None) or entry.get("proc")
            if proc is not None and getattr(proc, "returncode", None) is None:
                try:
                    proc.terminate()
                    if platform.system() == "Windows":
                        pid = getattr(proc, "pid", None)
                        if pid:
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                           capture_output=True, timeout=5)
                except Exception as e:
                    log.warning("MCP shutdown '%s' error: %s", sid, e)
            log.info("MCP server '%s' shut down", sid)


# Module-level singleton (initialized lazily in main.py)
mcp_manager: Optional[MCPManager] = None
