import re


def test_main_language_policy_block_is_bilingual_safe():
    import main

    block = main._language_policy_block()
    assert "Internal agent" in block or "внутренние agent" in block.lower()
    assert "English" in block or "EN" in block
    assert "user's language" in block or "языке пользователя" in block.lower()


def test_coding_orchestrator_child_prompts_use_english_internal():
    from ai_engine.coding_orchestrator import CodingOrchestrator
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        root.joinpath("README.md").write_text("ok", encoding="utf-8")
        orch = CodingOrchestrator(str(root), storage_path=str(root / "runs.json"))
        planner = orch._child_prompt("planner", "fix bug", {"task": 1})
        coder = orch._child_prompt("coder", "fix bug", {"task": 1})
        reviewer = orch._child_prompt("reviewer", "fix bug", {"task": 1})

        assert re.search(r"English", planner)
        assert re.search(r"English", coder)
        assert re.search(r"English", reviewer)
        assert "user's language" in planner or "user language" in planner.lower()
