"""True coding orchestrator for AMT Chat.

This module implements a small planner/coder/reviewer hierarchy over the
project-scoped coding toolset. It is intentionally separate from the legacy
context/monitoring Orchestrator and stores its own runs.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .coding_tools import CodingToolset, ProjectContext
from .permissions import ApprovalGate


_LLM_CALL = Callable[[str, Dict[str, Any]], Awaitable[str]]


def _parse_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@dataclass
class CodingOrchestrator:
    root: str
    storage_path: Optional[str] = None
    default_policy: List[Dict[str, str]] = field(default_factory=list)
    max_rounds: int = 3
    deny_globs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.context = ProjectContext(
            root=self.root,
            allow_write=True,
            allow_commands=True,
            allow_git_commit=False,
            deny_globs=self.deny_globs or [".env", "*.key", "keys.json", "secrets*"],
        )

    def _load_runs(self) -> Dict[str, Any]:
        if not self.storage_path or not os.path.exists(self.storage_path):
            return {"coding_orchestrator_runs": []}
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data.setdefault("coding_orchestrator_runs", [])
        return data

    def _save_runs(self, data: Dict[str, Any]) -> None:
        if not self.storage_path:
            return
        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _append_run(self, run: Dict[str, Any]) -> None:
        data = self._load_runs()
        data["coding_orchestrator_runs"].append(run)
        self._save_runs(data)

    def _update_run(self, run: Dict[str, Any]) -> None:
        data = self._load_runs()
        for idx, existing in enumerate(data["coding_orchestrator_runs"]):
            if existing.get("id") == run.get("id"):
                data["coding_orchestrator_runs"][idx] = run
                break
        else:
            data["coding_orchestrator_runs"].append(run)
        self._save_runs(data)

    def _child_prompt(self, role: str, goal: str, context: Dict[str, Any]) -> str:
        base = {
            "planner": (
                "You are the planner. Break the goal into 1-3 short coding tasks for the coder. "
                "Internal task titles and reasoning must be in English. User-facing task titles and acceptance "
                "criteria should be in the user's language when they will read them. "
                "Return JSON: {\"tasks\":[{\"id\",\"title\",\"files\",\"steps\",\"acceptance\"}]}."
            ),
            "coder": (
                "You are the coder. Implement only the requested task inside the project root. "
                "Internal reasoning, file contents, and command arguments must be in English where applicable. "
                "Return JSON: {\"summary\",\"files\":[{\"path\",\"action\",\"content\"}],\"commands\":[]}. "
                "The user-facing summary should be in the user's language."
            ),
            "reviewer": (
                "You are the reviewer. Review the coder's changes and report issues in English. "
                "Return JSON: {\"approved\":true|false,\"issues\":[]}. "
                "If approved=true, add a brief user-facing summary in the user's language under 'user_summary' when possible."
            ),
        }
        prompt = (
            f"[ROLE: {role}] {base.get(role, '')}\n"
            f"Goal: {goal}\n"
            f"Context: {json.dumps(context, ensure_ascii=False)}"
        )
        return prompt

    async def _run_role(self, run: Dict[str, Any], role: str, goal: str, context: Dict[str, Any], llm_call: _LLM_CALL, on_event: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        child_id = f"child_{role}_{uuid.uuid4().hex[:8]}"
        prompt = self._child_prompt(role, goal, context)
        child: Dict[str, Any] = {
            "id": child_id,
            "role": role,
            "status": "started",
            "started_at": time.time(),
            "prompt_chars": len(prompt),
            "output": "",
            "result": {},
        }
        run["children"].append(child)
        self._update_run(run)
        if on_event:
            on_event({"type": "orchestrator_child_started", "run_id": run["id"], "child_id": child_id, "role": role})

        raw = await llm_call(prompt, {"role": role, "goal": goal, "context": context})
        child["output"] = raw
        child["result"] = _parse_json_payload(raw)
        child["status"] = "completed"
        child["completed_at"] = time.time()
        run["status"] = "running"
        self._update_run(run)
        if on_event:
            on_event({"type": "orchestrator_child_completed", "run_id": run["id"], "child_id": child_id, "role": role, "result": child["result"]})
        return child

    async def run_goal(self, goal: str, llm_call: _LLM_CALL, on_event: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        run: Dict[str, Any] = {
            "id": f"orch_{uuid.uuid4().hex[:10]}",
            "goal": goal,
            "root": self.root,
            "status": "planning",
            "created_at": time.time(),
            "children": [],
            "files_changed": [],
            "reviewer_approved": False,
            "rounds": 0,
        }
        self._append_run(run)

        gate = ApprovalGate(self.default_policy or [])
        toolset = CodingToolset(self.context, approval=gate)

        def _emit(event: Dict[str, Any]) -> None:
            if on_event:
                on_event(event)

        planner = await self._run_role(run, "planner", goal, {"project_root": self.root}, llm_call, _emit)
        tasks = planner["result"].get("tasks") or []
        if not tasks:
            tasks = [{"id": "t1", "title": goal, "files": [], "steps": [], "acceptance": goal}]

        final_reviewer: Dict[str, Any] = {}
        approved = False
        for task in tasks:
            last_issues: List[str] = []
            for round_no in range(1, self.max_rounds + 1):
                run["rounds"] = max(run["rounds"], round_no)
                coder = await self._run_role(run, "coder", task.get("title") or goal, {"task": task, "issues": last_issues, "round": round_no}, llm_call, _emit)
                for file_change in coder["result"].get("files", []):
                    path = str(file_change.get("path", "")).strip()
                    content = str(file_change.get("content", ""))
                    if not path:
                        continue
                    approval = await toolset._approval("write", path, {"content_len": len(content)}, f"write {path}")
                    if not approval.get("approved"):
                        run["files_changed"].append({"path": path, "status": "denied", "reason": approval.get("decision", "deny")})
                        continue
                    write_result = await asyncio.to_thread(toolset.fs_write, path, content)
                    if write_result.get("ok"):
                        run["files_changed"].append({"path": path, "status": "written", "round": round_no})
                    else:
                        run["files_changed"].append({"path": path, "status": "error", "error": write_result.get("error", "")})
                    if on_event:
                        on_event({"type": "orchestrator_file_write", "run_id": run["id"], "path": path, "status": run["files_changed"][-1].get("status")})

                reviewer = await self._run_role(run, "reviewer", task.get("title") or goal, {"task": task, "round": round_no, "files_changed": run["files_changed"]}, llm_call, _emit)
                final_reviewer = reviewer
                approved = bool(reviewer["result"].get("approved") is True)
                last_issues = reviewer["result"].get("issues", [])
                if approved:
                    break

        run["status"] = "completed" if approved else "completed_with_issues"
        run["reviewer_approved"] = approved
        run["finished_at"] = time.time()
        self._update_run(run)
        run["result"] = final_reviewer["result"]
        return run
