"""Project-scoped coding tool handlers for AMT Chat.

This module owns the pure logic for file/git/command operations that the
coding chat profile uses.  It is deliberately independent of the global
ToolSandbox so that each coding chat can operate against its own project
root without mutating global allowed_dirs.

All paths are validated against the per-request ProjectContext.  Commands are
executed with shell=False and an allowlist of safe executables.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional


# --- Safe command allowlist ---------------------------------------------------
# Only these executable names may be run via run_command().
_ALLOWED_COMMANDS = {
    "git", "python", "python3", "pytest", "node", "npm", "npx", "pnpm", "yarn",
    "ruff", "eslint", "prettier", "tsc", "cargo", "go", "dotnet", "make", "cmake",
    "shell", "powershell", "bash", "cmd",
}

# Patterns that indicate shell metacharacters in a single argv element.
_SHELL_METACHAR_RE = re.compile(r"[;&|`$()]|>{1,2}")


@dataclass
class ProjectContext:
    """Per-request project isolation boundary.

    - ``root`` is resolved to an absolute path and used as the sandbox root.
    - ``allow_write`` gates file writes.
    - ``allow_commands`` gates shell execution.
    - ``allow_git_commit`` gates git commit operations.
    - ``deny_globs`` is a list of fnmatch patterns (relative to root) that are
      always denied regardless of allow flags.
    """
    root: str
    allow_write: bool = False
    allow_commands: bool = False
    allow_git_commit: bool = False
    deny_globs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = os.path.realpath(self.root)
        if not os.path.isdir(self.root):
            raise ValueError(f"Project root does not exist or is not a directory: {self.root}")


def _is_denied_by_globs(rel_path: str, deny_globs: list[str]) -> bool:
    """Return True if rel_path matches any deny_glob pattern."""
    if not deny_globs:
        return False
    norm = rel_path.replace("\\", "/")
    for pattern in deny_globs:
        pattern_norm = pattern.replace("\\", "/")
        # Match the full relative path against the pattern (fnmatch is recursive).
        if fnmatch.fnmatch(norm, pattern_norm):
            return True
        # Also allow patterns like "*.env" to match at any depth by stripping
        # the directory portion for single-segment patterns.
        if "/" not in pattern_norm and fnmatch.fnmatch(os.path.basename(norm), pattern_norm):
            return True
    return False


class CodingToolset:
    """Project-scoped coding tools.

    All methods return a dict with at minimum ``ok`` (bool) and either
    ``content``/``entries``/``matches``/``output`` or ``error``.
    """

    def __init__(self, context: ProjectContext, approval: Any = None, on_request: Any = None) -> None:
        self.ctx = context
        self.approval = approval  # Optional ApprovalGate for permission checks.
        self.on_request = on_request

    # --- internal helpers -----------------------------------------------------

    async def _approval(self, action: str, resource: str, args: dict | None = None, preview: str = "") -> dict:
        """Return an approval decision for a coding tool action.

        When no ApprovalGate is configured the action is allowed automatically.
        """
        if not self.approval:
            return {"approved": True, "decision": "allow", "action": action, "resource": resource}
        return await self.approval.require(action, resource, args, preview, on_request=self.on_request)

    def _resolve_path(self, rel_path: str) -> tuple[Optional[str], Optional[str]]:
        """Resolve a relative path inside the project root.

        Returns (absolute_path, None) on success, (None, error_message) on denial.
        """
        if not rel_path or rel_path.strip() == "":
            rel_path = "."
        # Normalize backslashes for Windows.
        rel_norm = rel_path.replace("\\", "/").strip("/")
        # Reject absolute paths or paths with drive letters.
        if os.path.isabs(rel_norm) or re.match(r"^[A-Za-z]:", rel_norm):
            return None, "Path must be relative to project root"

        candidate = os.path.join(self.ctx.root, rel_norm)
        real = os.path.realpath(candidate)
        root_real = self.ctx.root

        # Case-insensitive containment check on Windows.
        if os.name == "nt":
            contained = real.lower().startswith(root_real.lower())
        else:
            contained = real.startswith(root_real)

        if not contained:
            return None, "Path denied: outside project root"

        # Also reject if the normalized relative path contains `..` segments.
        norm_rel = os.path.normpath(rel_norm)
        if norm_rel.startswith("..") or "/../" in norm_rel or norm_rel == "..":
            return None, "Path denied: outside project root"

        # Deny globs
        rel_for_globs = os.path.relpath(real, root_real)
        if _is_denied_by_globs(rel_for_globs, self.ctx.deny_globs):
            return None, "Path denied by deny_globs policy"

        return real, None

    # --- fs tools -------------------------------------------------------------

    def fs_read(self, path: str, offset: int = 0, limit: Optional[int] = None) -> dict:
        """Read a file inside the project root.

        Returns {"ok": True, "content": str} or {"ok": False, "error": str}.
        """
        real, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        if not os.path.isfile(real):
            return {"ok": False, "error": f"File not found: {path}"}
        try:
            with open(real, "r", encoding="utf-8") as f:
                if limit is not None and offset > 0:
                    lines = f.readlines()
                    selected = lines[offset:offset + limit]
                    content = "".join(selected)
                elif limit is not None:
                    f.seek(0)
                    content = f.read(limit)
                else:
                    content = f.read()
            return {"ok": True, "content": content}
        except Exception as e:
            return {"ok": False, "error": f"Read failed: {e}"}

    def fs_list(self, path: str = ".", depth: int = 1) -> dict:
        """List directory entries inside the project root.

        Returns {"ok": True, "entries": [str, ...]} where each entry is a
        relative path.  ``depth`` controls recursion (1 = immediate children).
        """
        real, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        if not os.path.isdir(real):
            return {"ok": False, "error": f"Not a directory: {path}"}
        entries: list[str] = []
        max_depth = max(1, int(depth))
        for current_dir, dirnames, filenames in os.walk(real):
            cur_rel = os.path.relpath(current_dir, self.ctx.root)
            # Depth relative to the starting directory `real`.
            if cur_rel == ".":
                cur_depth = 0
            else:
                # Number of path components below `real`.
                rel_from_start = os.path.relpath(current_dir, real)
                cur_depth = 0 if rel_from_start == "." else rel_from_start.count(os.sep) + 1
            if cur_depth >= max_depth:
                dirnames[:] = []
                continue
            for fn in filenames:
                rel = os.path.normpath(os.path.join(cur_rel, fn)) if cur_rel != "." else fn
                entries.append(rel)
            for dn in dirnames:
                rel_d = os.path.normpath(os.path.join(cur_rel, dn)) if cur_rel != "." else dn
                entries.append(rel_d + "/")
        return {"ok": True, "entries": sorted(entries)}

    def fs_search(self, query: str, path: str = ".", file_pattern: Optional[str] = None) -> dict:
        """Search for a text query in files under the project root.

        Returns {"ok": True, "matches": [str, ...]} where each match is
        ``relative_path:line_number:line_content``.
        """
        real, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        # If path is the project root itself, it always exists; if it's a
        # subdirectory, ensure it exists before walking.
        if not os.path.isdir(real) and not os.path.isfile(real):
            return {"ok": False, "error": f"Path not found: {path}"}
        # Ensure parent directory of root-relative path exists (in case the
        # caller passed a relative path whose parent was just created).
        parent = os.path.dirname(real)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

        matches: list[str] = []
        max_results = 200
        query_norm = query.lower()

        def _search_file(file_path: str) -> None:
            nonlocal max_results
            if len(matches) >= max_results:
                return
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if query_norm in line.lower():
                            rel = os.path.relpath(file_path, self.ctx.root)
                            matches.append(f"{rel}:{lineno}:{line.rstrip()}")
                            if len(matches) >= max_results:
                                break
            except Exception:
                pass

        if os.path.isfile(real):
            if not file_pattern or fnmatch.fnmatch(os.path.basename(real), file_pattern):
                _search_file(real)
        else:
            for current_dir, dirnames, filenames in os.walk(real):
                # Skip common noise directories.
                dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".venv"}]
                for fn in filenames:
                    if file_pattern and not fnmatch.fnmatch(fn, file_pattern):
                        continue
                    _search_file(os.path.join(current_dir, fn))
                    if len(matches) >= max_results:
                        break
                if len(matches) >= max_results:
                    break

        return {"ok": True, "matches": matches}

    def fs_write(self, path: str, content: str) -> dict:
        """Write a file inside the project root.

        Requires ``ctx.allow_write``.  Returns {"ok": True} or {"ok": False, "error": str}.
        """
        if not self.ctx.allow_write:
            return {"ok": False, "error": "Write operations are not enabled for this project context"}
        real, err = self._resolve_path(path)
        if err:
            return {"ok": False, "error": err}
        # Ensure parent directories exist.
        parent = os.path.dirname(real)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        try:
            with open(real, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "path": os.path.relpath(real, self.ctx.root)}
        except Exception as e:
            return {"ok": False, "error": f"Write failed: {e}"}

    def fs_apply_patch(self, patch_content: str) -> dict:
        """Apply a unified diff patch to files in the project root.

        This is a placeholder that will use ``git apply`` when available.
        """
        if not self.ctx.allow_write:
            return {"ok": False, "error": "Write operations are not enabled for this project context"}
        # Write the patch to a temp file and use git apply.
        import tempfile
        import os as _os
        patch_file = _os.path.join(self.ctx.root, ".amt_patch.diff")
        try:
            with open(patch_file, "w", encoding="utf-8") as f:
                f.write(patch_content)
            result = self.run_command(["git", "apply", "--check", ".amt_patch.diff"], timeout=30)
            if not result.get("ok"):
                return {"ok": False, "error": f"Patch check failed: {result.get('error') or result.get('output')}"}
            apply_result = self.run_command(["git", "apply", ".amt_patch.diff"], timeout=30)
            _os.unlink(patch_file)
            if apply_result.get("ok"):
                return {"ok": True, "output": apply_result.get("output", "")}
            return {"ok": False, "error": f"Patch apply failed: {apply_result.get('error') or apply_result.get('output')}"}
        except Exception as e:
            return {"ok": False, "error": f"Patch failed: {e}"}

    # --- command tools --------------------------------------------------------

    def run_command(self, argv: list[str], timeout: int = 120) -> dict:
        """Run a command inside the project root.

        ``argv`` must be a list of strings.  The first element is the executable
        name (must be in the allowlist).  Shell metacharacters in any element
        are rejected.  Returns {"ok": True, "output": str} or {"ok": False, "error": str}.
        """
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        if not argv:
            return {"ok": False, "error": "argv must not be empty"}

        exe = os.path.basename(argv[0]).lower()
        # On Windows, allow .exe/.bat/.cmd extensions.
        if exe not in _ALLOWED_COMMANDS:
            # Strip common extensions for matching.
            exe_stripped = exe
            for ext in (".exe", ".bat", ".cmd", ".sh"):
                if exe_stripped.endswith(ext):
                    exe_stripped = exe_stripped[: -len(ext)]
                    break
            if exe_stripped not in _ALLOWED_COMMANDS:
                return {"ok": False, "error": f"Command not allowed: {argv[0]}"}

        # Check for shell metacharacters in any argv element.
        for i, elem in enumerate(argv):
            if _SHELL_METACHAR_RE.search(elem):
                return {"ok": False, "error": f"Unsafe metacharacters in argv[{i}]: {elem!r}"}

        try:
            result = subprocess.run(
                argv,
                cwd=self.ctx.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                # Inherit environment but ensure PATH is available.
            )
            output = result.stdout or result.stderr or ""
            if len(output) > 64 * 1024:
                output = output[: 64 * 1024] + "\n… [truncated]"
            return {
                "ok": result.returncode == 0,
                "output": output,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"ok": False, "error": f"Command failed: {e}"}

    # --- git tools ------------------------------------------------------------

    def git_status(self) -> dict:
        """Run ``git status`` in the project root."""
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        return self.run_command(["git", "status"], timeout=30)

    def git_diff(self, staged: bool = False) -> dict:
        """Run ``git diff`` (working tree or staged)."""
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
        return self.run_command(cmd, timeout=30)

    def git_log(self, n: int = 20) -> dict:
        """Run ``git log --oneline -n <n>``."""
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        cmd = ["git", "log", "--oneline", "-n", str(max(1, int(n)))]
        return self.run_command(cmd, timeout=30)

    def git_add(self, paths: list[str]) -> dict:
        """Stage files for commit.  Requires write permission."""
        if not self.ctx.allow_write:
            return {"ok": False, "error": "Write operations are not enabled for this project context"}
        if not paths:
            return {"ok": False, "error": "No paths specified for git add"}
        # Validate each path is inside the project root.
        for p in paths:
            _, err = self._resolve_path(p)
            if err:
                return {"ok": False, "error": f"git add path denied: {err}"}
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        cmd = ["git", "add", "--"] + paths
        return self.run_command(cmd, timeout=30)

    def git_commit(self, paths: list[str], message: str) -> dict:
        """Stage and commit files.  Requires allow_git_commit and allow_commands."""
        if not self.ctx.allow_git_commit:
            return {"ok": False, "error": "Git commit is not enabled for this project context"}
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        if not message.strip():
            return {"ok": False, "error": "Commit message must not be empty"}

        # Add paths first.
        if paths:
            add_result = self.git_add(paths)
            if not add_result.get("ok"):
                return add_result

        # Commit with explicit author to avoid git config issues.
        import os as _os
        env = _os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "AMT Chat")
        env.setdefault("GIT_AUTHOR_EMAIL", "amt@local")
        env.setdefault("GIT_COMMITTER_NAME", "AMT Chat")
        env.setdefault("GIT_COMMITTER_EMAIL", "amt@local")

        cmd = ["git", "commit", "-m", message]
        if paths:
            cmd = ["git", "commit", "-m", message, "--"] + paths
        try:
            result = subprocess.run(
                cmd,
                cwd=self.ctx.root,
                capture_output=True,
                text=True,
                timeout=60,
                shell=False,
                env=env,
            )
            output = result.stdout or result.stderr or ""
            return {
                "ok": result.returncode == 0,
                "output": output,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "git commit timed out"}
        except Exception as e:
            return {"ok": False, "error": f"git commit failed: {e}"}

    def git_branch(self) -> dict:
        """List branches (``git branch -a``)."""
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        return self.run_command(["git", "branch", "-a"], timeout=30)

    def git_push(self, remote: str = "origin", branch: str = "") -> dict:
        """Push to a remote.  Requires allow_git_commit and allow_commands.

        This is a high-risk operation; callers should route through the
        approval gate before invoking.
        """
        if not self.ctx.allow_git_commit:
            return {"ok": False, "error": "Git commit/push is not enabled for this project context"}
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}
        cmd = ["git", "push"]
        if remote:
            cmd.append(remote)
        if branch:
            cmd.append(branch)
        return self.run_command(cmd, timeout=120)

    def run_tests(self, extra_args: Optional[list[str]] = None) -> dict:
        """Run the most likely test runner for the project.

        Detects pytest for Python projects and ``node --test`` for Node
        projects.  This is intended for explicit ``/code_test`` commands,
        not for arbitrary shell execution.
        """
        if not self.ctx.allow_commands:
            return {"ok": False, "error": "Command execution is not enabled for this project context"}

        root = self.ctx.root
        if os.path.isfile(os.path.join(root, "package.json")):
            cmd = ["node", "--test"]
        elif (
            os.path.isfile(os.path.join(root, "pyproject.toml"))
            or os.path.isfile(os.path.join(root, "setup.py"))
            or os.path.isfile(os.path.join(root, "requirements.txt"))
            or os.path.isdir(os.path.join(root, "tests"))
        ):
            cmd = ["pytest", "-q"]
        else:
            return {"ok": False, "error": "No supported test runner found (package.json or pytest project)"}

        if extra_args:
            cmd.extend(str(a) for a in extra_args)
        return self.run_command(cmd, timeout=300)
