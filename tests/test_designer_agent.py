import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_core_designer_exists_in_agents():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from ai_engine.agents import AgentSkillManager
    ids = [a["id"] for a in AgentSkillManager.CORE_AGENTS]
    assert "core_designer" in ids
    designer = next(a for a in AgentSkillManager.CORE_AGENTS if a["id"] == "core_designer")
    assert "premium" in designer["description"].lower() or "дизайн" in designer["description"].lower()
    assert "transform" in designer["systemPrompt"].lower() or "opacity" in designer["systemPrompt"].lower()
    assert "ui_design" in designer["skills"]

def test_command_registry_contains_design():
    data = json.loads((ROOT / "backend" / "command_registry.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in data["commands"]]
    assert "design" in ids
    design = next(c for c in data["commands"] if c["id"] == "design")
    assert design["type"] == "feature"
    assert design["effects"]["enable_agent"] == "designer"


def test_main_maps_designer_alias_to_core_agent(tmp_backend):
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    import main

    assert main._agent_from_enabled_agents(["designer"], "") == "core_designer"
    assert main._agent_from_enabled_agents([], "manual") == "manual"
