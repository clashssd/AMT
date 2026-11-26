import asyncio
import fnmatch
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True)
class PermissionRule:
    action: str
    resource: str
    effect: str


def _normalize_rule(rule: dict | PermissionRule) -> PermissionRule:
    if isinstance(rule, PermissionRule):
        return rule
    return PermissionRule(
        action=str(rule.get("action", "*")).strip(),
        resource=str(rule.get("resource", "*")).strip(),
        effect=str(rule.get("effect", "ask")).strip().lower(),
    )


def _resource_matches(pattern: str, resource: str) -> bool:
    resource = (resource or "").strip()
    pattern = (pattern or "*").strip()
    if pattern == "*" or pattern == "":
        return True
    # A pattern ending in a space followed by `*` is a command prefix pattern:
    # "git status *" matches "git status", "git status -sb", etc.
    prefix = pattern[:-1] if pattern.endswith("*") and " " in pattern else None
    if prefix is not None and resource.startswith(prefix.rstrip() + " "):
        return True
    if pattern.endswith("*") and not any(ch in pattern for ch in ("[", "]", "?")):
        prefix_star = pattern[:-1]
        if resource.startswith(prefix_star) or resource == prefix_star.strip():
            return True
    return fnmatch.fnmatch(resource, pattern)


class ApprovalGate:
    def __init__(self, policy: Iterable[dict | PermissionRule] = (), saved_patterns: Iterable[dict | PermissionRule] = None, timeout_seconds: float = 120.0):
        self.policy = [_normalize_rule(rule) for rule in (policy or [])]
        self.saved_patterns = [_normalize_rule(rule) for rule in (saved_patterns or [])]
        self.timeout_seconds = max(float(timeout_seconds), 0.0)
        self.pending: dict[str, asyncio.Future] = {}
        self.pending_meta: dict[str, dict] = {}

    def _last_matching_rule(self, rules: Iterable[PermissionRule], action: str, resource: str) -> PermissionRule | None:
        matched: PermissionRule | None = None
        for rule in rules:
            action_ok = rule.action in ("*", action)
            resource_ok = _resource_matches(rule.resource, resource)
            if action_ok and resource_ok:
                matched = rule
        return matched

    def match(self, action: str, resource: str) -> str:
        # An explicit policy `deny` is a hard barrier: even a later `allow` rule in
        # the same policy list cannot override it, and saved `always` patterns can
        # never override a matching policy `deny`.
        deny_rule = self._last_matching_rule(
            [r for r in self.policy if r.effect == "deny"], action, resource
        )
        if deny_rule:
            return "deny"

        policy_rule = self._last_matching_rule(self.policy, action, resource)
        if policy_rule:
            return policy_rule.effect

        saved = self._last_matching_rule(self.saved_patterns, action, resource)
        if saved and saved.effect == "allow":
            return "allow"
        return "ask"

    async def require(self, action: str, resource: str, args: dict | None = None, preview: str = "", on_request: Callable[[str], None] | None = None) -> dict:
        effect = self.match(action, resource)
        if effect == "allow":
            return {"approved": True, "decision": "allow", "action": action, "resource": resource}
        if effect == "deny":
            return {"approved": False, "decision": "deny", "action": action, "resource": resource}

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        request_id = f"{action}:{resource}:{id(future)}"
        self.pending[request_id] = future
        self.pending_meta[request_id] = {
            "action": action,
            "resource": resource,
            "args": args or {},
            "preview": preview,
        }
        if on_request:
            on_request(request_id)
        try:
            decision = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            self.pending.pop(request_id, None)
            return {
                "approved": False,
                "decision": "timeout",
                "action": action,
                "resource": resource,
                "args": args or {},
                "preview": preview,
            }
        finally:
            self.pending.pop(request_id, None)
            self.pending_meta.pop(request_id, None)

        decision = str(decision or "").lower()
        if decision in ("once", "always", "allow"):
            return {
                "approved": True,
                "decision": decision,
                "action": action,
                "resource": resource,
                "args": args or {},
                "preview": preview,
            }
        return {
            "approved": False,
            "decision": "reject",
            "action": action,
            "resource": resource,
            "args": args or {},
            "preview": preview,
        }
