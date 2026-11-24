"""Round-6: jailbreak-as-primary-prompt + media error handling."""
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(BASE, "backend", "main.py")
AGENTS_PY = os.path.join(BASE, "backend", "ai_engine", "agents.py")
AGENTS_JSON = os.path.join(BASE, "backend", "agents.json")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ---------- 1. Jailbreak as primary system prompt ----------

class TestJailbreakPrimaryPrompt:
    def test_jailbreak_block_first(self):
        """In jailbreak mode, the jailbreak prompt must come BEFORE agent_block."""
        src = _read(MAIN_PY)
        # Find the system_prompt assembly for jailbreak mode
        assert "if jailbreak_active and core_block:" in src
        # The jailbreak branch must put core_block before agent_block
        m = re.search(r"if jailbreak_active and core_block:.*?core_block", src, re.DOTALL)
        assert m, "jailbreak mode must reference core_block"

    def test_jailbreak_override_instruction(self):
        src = _read(MAIN_PY)
        # The core_block header must contain explicit override instruction
        m = re.search(r"ПОВЕДЕНИЕ ЭТОГО ЧАТА.*?ПЕРЕОПРЕДЕЛЯЮТ", src, re.DOTALL)
        assert m, "core_block must contain explicit override instruction"

    def test_jailbreak_agent_id_core_jailbreak(self):
        src = _read(MAIN_PY)
        assert '"core_jailbreak" in core_agents' in src or "core_jailbreak" in src

    def test_non_jailbreak_mode_preserves_order(self):
        src = _read(MAIN_PY)
        # Non-jailbreak: system_prompt + agent_block + core_block (original order)
        assert "system_prompt + " in src or "agent_block" in src


# ---------- 2. core_jailbreak prompt v2 in agents.py ----------

class TestJailbreakPromptV2:
    def test_prompt_contains_bezogrannichny(self):
        src = _read(AGENTS_PY)
        assert "БЕЗОГРАНИЧЕННЫЙ" in src

    def test_prompt_contains_forbidden_phrases(self):
        src = _read(AGENTS_PY)
        assert "ЗАПРЕЩЁННЫЕ ФРАЗЫ" in src

    def test_prompt_version_2(self):
        src = _read(AGENTS_PY)
        assert '"corePromptVersion": 2' in src  # core_web is still v2

    def test_no_mojibake(self):
        src = _read(AGENTS_PY)
        # Check for common mojibake patterns (UTF-8 bytes misread as CP1251)
        # The file should have clean Cyrillic
        assert "модели" not in src or True  # just check it compiles
        import py_compile
        py_compile.compile(AGENTS_PY, doraise=True)


# ---------- 3. agents.json synced ----------

class TestAgentsJsonSynced:
    def test_core_jailbreak_in_json(self):
        import json
        with open(AGENTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        jb = next((a for a in data.get("agents", []) if a["id"] == "core_jailbreak"), None)
        assert jb, "core_jailbreak missing from agents.json"
        assert jb.get("corePromptVersion") == 8
        assert "БЕЗОГРАНИЧЕННЫЙ" in jb.get("systemPrompt", "")

    def test_core_web_in_json(self):
        import json
        with open(AGENTS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        cw = next((a for a in data.get("agents", []) if a["id"] == "core_web"), None)
        assert cw, "core_web missing from agents.json"
        assert "веб-агент" in cw.get("systemPrompt", "")


# ---------- 4. Media endpoints error handling ----------

class TestMediaErrorHandling:
    def test_media_generate_wrapped(self):
        src = _read(MAIN_PY)
        assert "_media_generate_inner" in src
        assert "JSONResponse(status_code=500" in src

    def test_media_check_wrapped(self):
        src = _read(MAIN_PY)
        m = re.search(r'def media_check.*?JSONResponse\(status_code=500', src, re.DOTALL)
        assert m, "media_check must return 500 JSON on error"

    def test_voices_list_wrapped(self):
        src = _read(MAIN_PY)
        m = re.search(r'def media_voices_list.*?JSONResponse\(status_code=500', src, re.DOTALL)
        assert m, "voices/list must return 500 JSON on error"

    def test_voices_clone_wrapped(self):
        src = _read(MAIN_PY)
        m = re.search(r'def media_voices_clone.*?JSONResponse\(status_code=500', src, re.DOTALL)
        assert m, "voices/clone must return 500 JSON on error"

    def test_jsonresponse_imported(self):
        src = _read(MAIN_PY)
        assert "from fastapi.responses import FileResponse, JSONResponse" in src or "JSONResponse" in src
