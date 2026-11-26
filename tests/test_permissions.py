import asyncio
import time


def test_last_matching_rule_wins():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate(
        [
            {"action": "shell", "resource": "*", "effect": "ask"},
            {"action": "shell", "resource": "git status *", "effect": "allow"},
        ]
    )

    assert gate.match("shell", "git status") == "allow"
    assert gate.match("shell", "git commit -m x") == "ask"


def test_saved_always_cannot_override_deny():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate(
        policy=[
            {"action": "edit", "resource": "*.env", "effect": "deny"},
            {"action": "edit", "resource": "*", "effect": "allow"},
        ],
        saved_patterns=[{"action": "edit", "resource": "*.env", "effect": "allow"}],
    )

    assert gate.match("edit", "src/.env") == "deny"


def test_default_is_ask_when_no_rule_matches():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([])

    assert gate.match("shell", "rm -rf .") == "ask"


def test_require_allows_when_effect_is_allow():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([{"action": "shell", "resource": "*", "effect": "allow"}])

    result = asyncio.run(gate.require("shell", "git status", {}, "git status"))

    assert result["approved"] is True
    assert result["decision"] == "allow"


def test_require_rejects_when_effect_is_deny():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([{"action": "shell", "resource": "*", "effect": "deny"}])

    result = asyncio.run(gate.require("shell", "rm -rf .", {}, "rm -rf ."))

    assert result["approved"] is False
    assert result["decision"] == "deny"


def test_require_timeout_rejects_pending_approval():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([{"action": "shell", "resource": "*", "effect": "ask"}], timeout_seconds=0.05)

    start = time.monotonic()
    result = asyncio.run(gate.require("shell", "git status", {}, "git status"))
    elapsed = time.monotonic() - start

    assert result["approved"] is False
    assert result["decision"] == "timeout"
    assert elapsed < 0.5


def test_require_reports_pending_request_id():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([{"action": "shell", "resource": "*", "effect": "ask"}], timeout_seconds=5)
    seen = []

    async def run():
        async def answer_later():
            await asyncio.sleep(0.02)
            gate.pending[seen[0]].set_result("once")

        task = asyncio.create_task(answer_later())
        return await gate.require("shell", "git commit", {}, "git commit", on_request=seen.append)

    result = asyncio.run(run())

    assert result["approved"] is True
    assert result["decision"] == "once"
    assert seen and isinstance(seen[0], str)


def test_require_accepts_response_when_future_resolves():
    from ai_engine.permissions import ApprovalGate

    gate = ApprovalGate([{"action": "shell", "resource": "*", "effect": "ask"}], timeout_seconds=5)

    async def run():
        task = asyncio.create_task(gate.require("shell", "git status", {}, "git status"))
        # wait until the gate registers its pending future
        for _ in range(50):
            if gate.pending:
                break
            await asyncio.sleep(0.01)
        assert gate.pending, "expected a pending approval request"
        only_future = next(iter(gate.pending.values()))
        only_future.set_result("always")
        return await task

    result = asyncio.run(run())

    assert result["approved"] is True
    assert result["decision"] == "always"
