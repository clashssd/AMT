# tests/test_mcp_manager.py
import pytest, json, os

def test_mcp_server_config_dataclass():
    from ai_engine.mcp_manager import MCPServerConfig
    cfg = MCPServerConfig(
        id="fs", name="Filesystem", transport="stdio",
        command="npx", args=["@modelcontextprotocol/server-filesystem", "/tmp"],
        url="", headers={}, env={"API_KEY": "secret123"},
        enabled=True, auto_approve=False,
    )
    assert cfg.id == "fs"
    assert cfg.transport == "stdio"
    assert cfg.env["API_KEY"] == "secret123"

def test_mcp_manager_crud(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(str(tmp_backend["tmp"]))

    cfg = MCPServerConfig(
        id="fs", name="Filesystem", transport="stdio",
        command="npx", args=["test"],
        url="", headers={}, env={"KEY": "val"},
        enabled=True, auto_approve=False,
    )
    mgr.add_server(cfg)

    servers = mgr.list_servers()
    assert len(servers) == 1
    assert servers[0].id == "fs"

    cfg.name = "Updated"
    mgr.update_server(cfg)
    updated = mgr.get_server("fs")
    assert updated.name == "Updated"

    mgr.set_enabled("fs", False)
    assert mgr.get_server("fs").enabled is False

    mgr.remove_server("fs")
    assert mgr.list_servers() == []

def test_env_var_encryption_roundtrip(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(str(tmp_backend["tmp"]))

    cfg = MCPServerConfig(
        id="enc", name="EncTest", transport="http",
        command="", args=[],
        url="http://localhost:3000", headers={},
        env={"SECRET": "top_secret_value"},
        enabled=True, auto_approve=True,
    )
    mgr.add_server(cfg)

    # Read raw JSON from disk — env values must be encrypted (not plaintext)
    servers_file = os.path.join(tmp_backend["tmp"], "mcp_servers.json")
    with open(servers_file) as f:
        raw = json.load(f)
    stored_env = raw["servers"][0]["env"]
    assert stored_env["SECRET"] != "top_secret_value"
    assert "top_secret_value" not in json.dumps(raw)

    # Fresh manager instance loads and decrypts correctly
    mgr2 = MCPManager(str(tmp_backend["tmp"]))
    loaded = mgr2.get_server("enc")
    assert loaded.env["SECRET"] == "top_secret_value"

def test_fernet_key_created_with_permissions(tmp_backend):
    from ai_engine.mcp_manager import MCPManager
    mgr = MCPManager(str(tmp_backend["tmp"]))
    key_file = os.path.join(tmp_backend["tmp"], "mcp_key.key")
    assert os.path.exists(key_file)
    # On Linux/macOS check 0600; on Windows skip permission check
    import platform
    if platform.system() != "Windows":
        mode = oct(os.stat(key_file).st_mode & 0o777)
        assert mode in ("0o600", "0o400"), f"key file permissions: {mode}"

def test_add_server_rejects_duplicate_id(tmp_backend):
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig
    mgr = MCPManager(str(tmp_backend["tmp"]))
    cfg1 = MCPServerConfig(id="x", name="A", transport="stdio", command="c", args=[], url="", headers={}, env={}, enabled=True, auto_approve=False)
    cfg2 = MCPServerConfig(id="x", name="B", transport="http", command="", args=[], url="http://x", headers={}, env={}, enabled=True, auto_approve=False)
    mgr.add_server(cfg1)
    with pytest.raises(Exception):
        mgr.add_server(cfg2)
