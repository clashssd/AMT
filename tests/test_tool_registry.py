# tests/test_tool_registry.py
import pytest, json, asyncio


def test_tool_def_dataclass():
    from ai_engine.tool_registry import ToolDef
    t = ToolDef(name="x", description="d", parameters={}, handler=None, source="native")
    assert t.name == "x" and t.source == "native"


def test_register_and_schemas():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    reg.register(ToolDef(name="echo", description="echoes", parameters={"type": "object", "properties": {"text": {"type": "string"}}}, handler=None, source="native"))
    schemas = reg.schemas()
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "echo"


def test_duplicate_name_rejected():
    from ai_engine.tool_registry import ToolRegistry, ToolDef, ToolExecutionError
    reg = ToolRegistry()
    reg.register(ToolDef(name="dup", description="a", parameters={}, handler=None, source="native"))
    with pytest.raises(ToolExecutionError):
        reg.register(ToolDef(name="dup", description="b", parameters={}, handler=None, source="native"))


def test_unregister_prefix():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()
    reg.register(ToolDef(name="mcp__fs__read", description="r", parameters={}, handler=None, source="mcp:fs"))
    reg.register(ToolDef(name="mcp__fs__write", description="w", parameters={}, handler=None, source="mcp:fs"))
    reg.register(ToolDef(name="native_tool", description="n", parameters={}, handler=None, source="native"))
    removed = reg.unregister_prefix("mcp__fs")
    assert removed == 2
    assert reg.has("native_tool")
    assert not reg.has("mcp__fs__read")


def test_execute_dispatch():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()

    async def echo_handler(text: str) -> str:
        return json.dumps({"echo": text})

    reg.register(ToolDef(name="echo", description="e", parameters={"type": "object", "properties": {"text": {"type": "string"}}}, handler=echo_handler, source="native"))
    result = asyncio.run(reg.execute("echo", {"text": "hi"}))
    assert json.loads(result)["echo"] == "hi"


def test_execute_unknown_tool():
    from ai_engine.tool_registry import ToolRegistry, ToolExecutionError
    reg = ToolRegistry()
    with pytest.raises(ToolExecutionError):
        asyncio.run(reg.execute("nonexistent", {}))


def test_execute_handler_error():
    from ai_engine.tool_registry import ToolRegistry, ToolDef
    reg = ToolRegistry()

    async def bad_handler(**kw) -> str:
        raise ValueError("boom")

    reg.register(ToolDef(name="bad", description="b", parameters={}, handler=bad_handler, source="native"))
    result = asyncio.run(reg.execute("bad", {}))
    assert "error" in result.lower() or "boom" in result


def test_register_native_tools():
    from ai_engine.tool_registry import ToolRegistry, register_native_tools
    reg = ToolRegistry()
    register_native_tools(reg)
    for name in ("generate_image", "generate_video", "generate_audio", "generate_file"):
        assert reg.has(name), f"missing native tool: {name}"
    schemas = reg.schemas()
    assert len(schemas) == 4
    for s in schemas:
        assert s["type"] == "function"
        assert s["function"]["parameters"]["type"] == "object"
