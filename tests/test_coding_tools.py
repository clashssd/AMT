import subprocess
import sys
import os
import pytest


def _git(args, cwd):
    result = subprocess.run([sys.executable, "-m", "pip", "show", "git"], capture_output=True, text=True)
    return result


def test_project_context_resolves_root_and_blocks_traversal(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.txt").write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    ctx = ProjectContext(root=str(root), allow_write=False, allow_commands=False, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    # fs_read inside root works
    ok = toolset.fs_read("src/a.txt")
    assert ok["ok"] is True
    assert ok["content"] == "ok"

    # fs_read outside root fails
    bad = toolset.fs_read("../outside.txt")
    assert bad["ok"] is False
    assert "denied" in bad["error"].lower() or "outside" in bad["error"].lower()

    # fs_write is blocked when allow_write=False
    write_bad = toolset.fs_write("src/b.txt", "hello")
    assert write_bad["ok"] is False
    assert "write" in write_bad["error"].lower()


def test_project_context_allows_write_and_list(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)

    ctx = ProjectContext(root=str(root), allow_write=True, allow_commands=False, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    res = toolset.fs_write("src/new.txt", "content here")
    assert res["ok"] is True
    assert (root / "src" / "new.txt").read_text(encoding="utf-8") == "content here"

    listing = toolset.fs_list("src", depth=1)
    assert listing["ok"] is True
    assert any("new.txt" in item for item in listing["entries"])


def test_project_context_search_finds_text(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (root / "b.txt").write_text("find me here", encoding="utf-8")

    ctx = ProjectContext(root=str(root), allow_write=False, allow_commands=False, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    found = toolset.fs_search("find me")
    assert found["ok"] is True
    assert any("b.txt" in line for line in found["matches"])


def test_run_command_rejects_shell_metacharacters(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    ctx = ProjectContext(root=str(tmp_path), allow_write=False, allow_commands=True, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    # Semicolon in argument
    bad = toolset.run_command(["git", "status; rm -rf /"])
    assert bad["ok"] is False
    assert "unsafe" in bad["error"].lower() or "metachar" in bad["error"].lower()

    # Pipe in argument
    bad2 = toolset.run_command(["ls | rm -rf /"])
    assert bad2["ok"] is False


def test_run_command_allows_git_status(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    # Create a git repo for the test
    result = subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("git not available for testing")

    ctx = ProjectContext(root=str(tmp_path), allow_write=False, allow_commands=True, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    ok = toolset.run_command(["git", "status"])
    assert ok["ok"] is True
    assert "working" in ok["output"].lower() or "branch" in ok["output"].lower()


def test_git_status_and_log(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"})

    ctx = ProjectContext(root=str(tmp_path), allow_write=False, allow_commands=True, allow_git_commit=True, deny_globs=[])
    toolset = CodingToolset(ctx)

    status = toolset.git_status()
    assert status["ok"] is True
    assert "working" in status["output"].lower() or "branch" in status["output"].lower()

    log = toolset.git_log(n=5)
    assert log["ok"] is True
    assert "initial" in log["output"].lower()


def test_coding_approval_gate_can_deny_write(tmp_path):
    import asyncio
    from ai_engine.coding_tools import ProjectContext, CodingToolset
    from ai_engine.permissions import ApprovalGate

    root = tmp_path / "repo"
    root.mkdir()
    context = ProjectContext(root=str(root), allow_write=True, allow_commands=False, allow_git_commit=False, deny_globs=[])
    gate = ApprovalGate([{"action": "edit", "resource": "*", "effect": "deny"}])
    toolset = CodingToolset(context, approval=gate)

    result = asyncio.run(toolset._approval("edit", "a.txt", {"path": "a.txt"}, "write a.txt"))

    assert result["approved"] is False
    assert result["decision"] == "deny"


def test_git_commit_requires_permission(tmp_path):
    from ai_engine.coding_tools import ProjectContext, CodingToolset

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, text=True)
    (tmp_path / "new.txt").write_text("data", encoding="utf-8")
    subprocess.run(["git", "add", "new.txt"], cwd=tmp_path, capture_output=True, text=True)

    ctx = ProjectContext(root=str(tmp_path), allow_write=False, allow_commands=True, allow_git_commit=False, deny_globs=[])
    toolset = CodingToolset(ctx)

    result = toolset.git_commit(paths=["new.txt"], message="add new file")
    assert result["ok"] is False
    assert "commit" in result["error"].lower() or "permission" in result["error"].lower()
