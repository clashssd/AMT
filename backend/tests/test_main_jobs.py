"""Layer 1.2: plan-job registry + FastAPI polling endpoints.

Tests use a real (stubbed) sandbox + orchestrator and a real resolve_plan_v2
call, so we exercise the full background-task path: start_plan_job →
asyncio.create_task → resolve_plan_v2 → _run_plan_job writes result.
"""
import asyncio

import pytest


@pytest.fixture
def main_mod(_isolate_main):
    import main
    return main


@pytest.fixture
def clean_jobs(main_mod):
    """Snapshot + restore the plan-jobs registry so tests are hermetic."""
    saved = dict(main_mod._plan_jobs)
    yield
    main_mod._plan_jobs.clear()
    main_mod._plan_jobs.update(saved)


def test_plan_jobs_registry_shape(main_mod, clean_jobs):
    job_id, rec = main_mod._new_plan_job()
    assert job_id.startswith("plan_")
    assert rec["status"] == "running"
    assert rec["result"] == ""
    assert job_id in main_mod._plan_jobs


def test_list_plan_jobs_returns_active_jobs(main_mod, clean_jobs):
    import time as _time
    # Seed two finished jobs (created=now so _plan_jobs_cleanup doesn't prune)
    main_mod._plan_jobs["plan_a"] = {
        "status": "done", "result": "ok", "error": "", "created": _time.time(),
    }
    main_mod._plan_jobs["plan_b"] = {
        "status": "error", "result": "", "error": "boom", "created": _time.time(),
    }
    # list_plan_jobs is a FastAPI coroutine — run it to a value
    return_value = asyncio.run(main_mod.list_plan_jobs())
    assert len(return_value["jobs"]) == 2
    ids = {j["job_id"] for j in return_value["jobs"]}
    assert ids == {"plan_a", "plan_b"}
    statuses = {j["job_id"]: j["status"] for j in return_value["jobs"]}
    assert statuses["plan_a"] == "done"
    assert statuses["plan_b"] == "error"


def test_get_plan_job_known_and_unknown(main_mod, clean_jobs):
    main_mod._plan_jobs["plan_x"] = {
        "status": "done", "result": "hello", "error": "", "created": 0,
    }
    r_known = asyncio.run(main_mod.get_plan_job("plan_x"))
    assert r_known["status"] == "done"
    assert r_known["result"] == "hello"

    r_unknown = asyncio.run(main_mod.get_plan_job("plan_zzz"))
    assert r_unknown["status"] == "not_found"


def test_start_plan_job_runs_and_completes(main_mod, clean_jobs, _make_sandbox_stub, _make_orchestrator_stub):
    """Start a plan-job in the background, wait for it to finish,
    assert the registry holds the result."""
    sandbox = _make_sandbox_stub()
    orch = _make_orchestrator_stub()

    plan = {
        "goal": "tiny test plan",
        "steps": [
            {"tool": "read_file", "args": {"path": "x"}, "expected": ""},
        ],
    }

    # Patch resolve_plan_v2 to avoid real tool calls (faster, deterministic)
    original = main_mod.resolve_plan_v2

    async def fake_resolve(plan_, sandbox_, orch_, api_key, base_url, model, proxy_string):
        await asyncio.sleep(0.02)
        return "done: 1/1 steps"

    main_mod.resolve_plan_v2 = fake_resolve
    try:
        # start_plan_job uses asyncio.create_task → needs a RUNNING loop.
        # Do it inside an async block, then await the job task there.
        async def _drive():
            job_id = main_mod.start_plan_job(plan, sandbox, orch, "k", "b", "m", "")
            assert job_id in main_mod._plan_jobs
            rec = main_mod._plan_jobs[job_id]
            assert rec["status"] == "running"
            await asyncio.wait_for(rec["task"], timeout=5.0)
            assert rec["status"] == "done"
            assert rec["result"] == "done: 1/1 steps"
        asyncio.run(_drive())
    finally:
        main_mod.resolve_plan_v2 = original
