"""AMT Coding MCP server (amt-coding).

Standalone STDIO MCP server exposing read-only/diagnostic coding tools for an
AMT project root.  It intentionally avoids high-risk operations such as file
writes, git commits/pushes, and raw command execution.  Those operations are
available through AMT's native coding tool loop and approval bridge instead.

Expected launch command:
    python backend/coding_mcp_server.py

Environment:
    AMT_CODING_ROOT  default project root for the server.
"""

import asyncio
import json
import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

try:
    from ai_engine.coding_tools import CodingToolset, ProjectContext
except Exception:
    sys.path.append(os.path.dirname(__file__))
    from ai_engine.coding_tools import CodingToolset, ProjectContext


DEFAULT_DENY_GLOBS = [".env", "*.key", "keys.json", "secrets*"]


def _project_context() -> ProjectContext:
    root = os.environ.get("AMT_CODING_ROOT", os.path.expanduser("~"))
    return ProjectContext(
        root=root,
        allow_write=False,
        allow_commands=True,
        allow_git_commit=False,
        deny_globs=DEFAULT_DENY_GLOBS,
    )


def _toolset() -> CodingToolset:
    return CodingToolset(_project_context(), approval=None, on_request=None)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


mcp = MCPServer(
    name="amt-coding",
    description="AMT advanced coding MCP server: read-only project diagnostics and safe test execution.",
    instructions=(
        "Use this server to inspect an AMT project: list files, read files, search text, "
        "inspect git state, and run supported test runners. High-risk changes are not "
        "exposed through this MCP server."
    ),
)


@mcp.tool(description="Get the project root and capabilities of this amt-coding server.")
def project_doctor() -> str:
    context = _project_context()
    return _json_result(
        {
            "ok": True,
            "root": context.root,
            "allow_write": context.allow_write,
            "allow_commands": context.allow_commands,
            "allow_git_commit": context.allow_git_commit,
            "deny_globs": context.deny_globs,
        }
    )


@mcp.tool(description="Read a UTF-8 text file inside the project root.")
def fs_read(path: str, offset: int = 0, limit: int | None = None) -> str:
    result = _toolset().fs_read(path, offset=offset, limit=limit)
    return _json_result(result)


@mcp.tool(description="List files and directories inside the project root.")
def fs_list(path: str = ".", depth: int = 1) -> str:
    result = _toolset().fs_list(path, depth=depth)
    return _json_result(result)


@mcp.tool(description="Search for text inside project files.")
def fs_search(query: str, path: str = ".", file_pattern: str | None = None) -> str:
    result = _toolset().fs_search(query, path=path, file_pattern=file_pattern)
    return _json_result(result)


@mcp.tool(description="Run `git status` in the project root.")
def git_status() -> str:
    return _json_result(_toolset().git_status())


@mcp.tool(description="Run `git diff` in the project root.")
def git_diff(staged: bool = False) -> str:
    return _json_result(_toolset().git_diff(staged=staged))


@mcp.tool(description="Run `git log --oneline` in the project root.")
def git_log(n: int = 20) -> str:
    return _json_result(_toolset().git_log(n=n))


@mcp.tool(description="List git branches in the project root.")
def git_branch() -> str:
    return _json_result(_toolset().git_branch())


@mcp.tool(description="Run the project's supported test runner (pytest or node --test).")
def run_tests(extra_args: list[str] | None = None) -> str:
    return _json_result(_toolset().run_tests(extra_args=extra_args))


@mcp.tool(description="Sequential reasoning helper: record and return a structured chain of thoughts.")
def sequential_thinking(steps: list[str] | None = None, question: str = "") -> str:
    payload = {"ok": True, "question": question, "steps": steps or []}
    if steps:
        payload["next_action"] = "Use the recorded steps to plan file reads, edits, or commands."
    return _json_result(payload)


@mcp.tool(description="Best-effort symbol extraction for supported source files inside the project root.")
def list_symbols(path: str = ".", depth: int = 1) -> str:
    context = _project_context()
    result = {"ok": True, "symbols": []}
    exts = {".py": ("def ", "class "), ".js": ("function ", "const ", "class "), ".ts": ("function ", "class "), ".go": ("func ", "type ")}
    for root, _dirs, files in os.walk(context.root):
        rel_root = os.path.relpath(root, context.root)
        for fname in files:
            ext = os.path.splitext(fname)[1]
            markers = exts.get(ext)
            if not markers:
                continue
            file_path = os.path.join(root, fname)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        for marker in markers:
                            if line.startswith(marker):
                                result["symbols"].append({
                                    "path": os.path.join(rel_root, fname) if rel_root != "." else fname,
                                    "line": line_no,
                                    "text": line.strip(),
                                })
                                break
            except Exception:
                continue
    return _json_result(result)


@mcp.tool(description="Read local documentation and context files from the project root when present.")
def read_context_docs(names: list[str] | None = None) -> str:
    context = _project_context()
    requested = names or ["README.md", "CONTRIBUTING.md", "AGENTS.md", "docs/ARCHITECTURE.md"]
    out = {"ok": True, "docs": []}
    for name in requested:
        target = os.path.join(context.root, name)
        if os.path.isfile(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    out["docs"].append({"path": name, "content": f.read()[:20000]})
            except Exception as e:
                out["docs"].append({"path": name, "error": str(e)})
    return _json_result(out)


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
