"""Tests for MCP REST endpoints + atexit + lazy MCP tool registration.

Task 6 from docs/superpowers/plans/2026-11-26-amt-tool-calling-mcp.md
"""
import pytest, json, os


def test_list_servers_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(str(tmp_backend["tmp"]))
        main.mcp_manager = mgr
    cfg = MCPServerConfig(
        id="test1", name="Test", transport="stdio",
        command="echo", args=[], url="", headers={},
        env={"KEY": "val"}, enabled=True, auto_approve=False,
    )
    mgr.add_server(cfg)

    c = TestClient(main.app)
    resp = c.get("/api/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "test1"
    # env values must be masked
    assert data[0]["env"] == {} or data[0]["env"].get("KEY") in ("***", "[encrypted]", None)


def test_add_server_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(str(tmp_backend["tmp"]))
        main.mcp_manager = mgr

    c = TestClient(main.app)
    resp = c.post("/api/mcp/servers", json={
        "id": "new1",
        "name": "New Server",
        "transport": "http",
        "url": "http://localhost:9999",
        "env": {"API_KEY": "secret"},
        "enabled": True,
        "auto_approve": False,
    })
    assert resp.status_code == 200
    assert mgr.get_server("new1") is not None


def test_remove_server_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(str(tmp_backend["tmp"]))
        main.mcp_manager = mgr
    cfg = MCPServerConfig(
        id="to_del", name="Del", transport="stdio",
        command="echo", args=[], url="", headers={},
        env={}, enabled=True, auto_approve=False,
    )
    mgr.add_server(cfg)

    c = TestClient(main.app)
    resp = c.delete("/api/mcp/servers/to_del")
    assert resp.status_code == 200
    assert mgr.get_server("to_del") is None


def test_enable_disable_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main
    from ai_engine.mcp_manager import MCPManager, MCPServerConfig

    mgr = main.mcp_manager
    if mgr is None:
        mgr = MCPManager(str(tmp_backend["tmp"]))
        main.mcp_manager = mgr
    cfg = MCPServerConfig(
        id="toggle", name="Toggle", transport="stdio",
        command="echo", args=[], url="", headers={},
        env={}, enabled=True, auto_approve=False,
    )
    mgr.add_server(cfg)

    c = TestClient(main.app)
    c.post("/api/mcp/servers/toggle/enable", json={"enabled": False})
    assert mgr.get_server("toggle").enabled is False
    c.post("/api/mcp/servers/toggle/enable", json={"enabled": True})
    assert mgr.get_server("toggle").enabled is True


def test_shutdown_endpoint(tmp_backend):
    from starlette.testclient import TestClient
    import main

    c = TestClient(main.app)
    resp = c.post("/api/mcp/shutdown")
    assert resp.status_code == 200
