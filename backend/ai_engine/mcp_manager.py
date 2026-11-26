# backend/ai_engine/mcp_manager.py
from __future__ import annotations
import json, logging, os, stat, platform
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from cryptography.fernet import Fernet

log = logging.getLogger(__name__)

SERVERS_FILE = "mcp_servers.json"
KEY_FILE = "mcp_key.key"

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


# Module-level singleton (initialized lazily in main.py)
mcp_manager: Optional[MCPManager] = None
