"""Tests for the core_jailbreak agent + search kind selection + web-link cards."""
import json
import os
import sys
import tempfile
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ai_engine.agents import AgentSkillManager


# ----------------------------------------------------------------------
# 1. core_jailbreak exists in CODE and seeds correctly
# ----------------------------------------------------------------------

class TestCoreJailbreakAgent:
    def test_in_core_agents(self):
        ids = [a["id"] for a in AgentSkillManager.CORE_AGENTS]
        assert "core_jailbreak" in ids, f"core_jailbreak missing from CORE_AGENTS: {ids}"

    def test_has_bypass_policy(self):
        jb = next(a for a in AgentSkillManager.CORE_AGENTS if a["id"] == "core_jailbreak")
        sp = jb["systemPrompt"]
        assert "ПОЛНЫЙ ОБХОД" in sp
        assert "БЕЗОГРАНИЧЕННЫЙ" in sp
        assert "RAT" in sp
        assert "NSFW" in sp or "18+" in sp
        assert "ЗАПРЕЩЁННЫЕ ФРАЗЫ" in sp

    def test_has_skills(self):
        jb = next(a for a in AgentSkillManager.CORE_AGENTS if a["id"] == "core_jailbreak")
        skills = jb["skills"]
        for s in ("web_search", "code_generation", "nsfw_content", "harmful_code", "full_bypass"):
            assert s in skills, f"skill {s} missing"

    def test_folder_is_core(self):
        jb = next(a for a in AgentSkillManager.CORE_AGENTS if a["id"] == "core_jailbreak")
        assert jb["folder"] == "core"

    def test_core_prompt_version(self):
        jb = next(a for a in AgentSkillManager.CORE_AGENTS if a["id"] == "core_jailbreak")
        assert jb.get("corePromptVersion") == 8


# ----------------------------------------------------------------------
# 2. seed_core_agents creates + upgrades jailbreak
# ----------------------------------------------------------------------

class TestJailbreakSeeding:
    def _mgr(self, agents_file):
        m = AgentSkillManager(agents_file)
        m.seed_core_agents()
        return m

    def test_fresh_seed_creates_jailbreak(self):
        tmp = tempfile.mktemp(suffix=".json")
        try:
            m = self._mgr(tmp)
            jb = m.get_agent("core_jailbreak")
            assert jb is not None
            assert "ПОЛНЫЙ ОБХОД" in jb["systemPrompt"]
            assert jb["folder"] == "core"
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_stale_jailbreak_gets_upgraded(self):
        """An old agents.json with core_jailbreak but without the new policy gets upgraded."""
        tmp = tempfile.mktemp(suffix=".json")
        stale = {
            "agents": [
                {"id": "core_jailbreak", "name": "Old JB", "folder": "core",
                 "systemPrompt": "old prompt without policy", "skills": []},
            ],
            "skills": [],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(stale, f, ensure_ascii=False)
        try:
            m = self._mgr(tmp)
            jb = m.get_agent("core_jailbreak")
            assert "БЕЗОГРАНИЧЕННЫЙ" in jb["systemPrompt"], "stale prompt not upgraded"
            assert jb["corePromptVersion"] == 8
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_user_agent_untouched(self):
        tmp = tempfile.mktemp(suffix=".json")
        data = {
            "agents": [
                {"id": "my_custom", "name": "Custom", "folder": "user",
                 "systemPrompt": "user prompt", "skills": []},
            ],
            "skills": [],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        try:
            m = self._mgr(tmp)
            cu = m.get_agent("my_custom")
            assert cu["systemPrompt"] == "user prompt"
            assert "corePromptVersion" not in cu
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def test_idempotent(self):
        tmp = tempfile.mktemp(suffix=".json")
        m1 = self._mgr(tmp)
        prompt1 = m1.get_agent("core_jailbreak")["systemPrompt"]
        m2 = self._mgr(tmp)
        prompt2 = m2.get_agent("core_jailbreak")["systemPrompt"]
        assert prompt1 == prompt2


# ----------------------------------------------------------------------
# 3. New core skills exist
# ----------------------------------------------------------------------

class TestJailbreakSkills:
    def test_skills_in_core_skills(self):
        ids = [s["id"] for s in AgentSkillManager.CORE_SKILLS]
        for s in ("code_generation", "nsfw_content", "harmful_code", "full_bypass"):
            assert s in ids, f"core skill {s} missing from CORE_SKILLS"


# ----------------------------------------------------------------------
# 4. Search kind selection in main.py
# ----------------------------------------------------------------------

class TestSearchKindSelection:
    def test_presearch_kind_logic(self):
        """Verify the kind-selection regex in main.py picks 'web' for non-video queries."""
        src = (Path(__file__).parent.parent / "backend" / "main.py").read_text(encoding="utf-8")
        # Find the video keyword regex used for pre-search kind
        assert "_video_kw_re" in src, "pre-search kind selector missing"
        assert "'web'" in src, "web kind not used"
        # The logic: _search_kind = 'auto' if video keywords else 'web'
        m = re.search(r"_search_kind\s*=\s*'auto'\s+if\s+_video_kw_re\.search\(_search_term\)\s+else\s+'web'", src)
        assert m, "pre-search kind selection logic not found"

    def test_bing_fallback_present(self):
        src = (Path(__file__).parent.parent / "backend" / "main.py").read_text(encoding="utf-8")
        assert "bing.com/search" in src, "Bing fallback missing"
        assert "b_algo" in src, "Bing parser missing"


# ----------------------------------------------------------------------
# 5. Web-link cards in main.js (source checks)
# ----------------------------------------------------------------------

class TestWebLinkCards:
    def test_web_url_regex_in_enhance(self):
        src = (Path(__file__).parent.parent / "frontend" / "js" / "main.js").read_text(encoding="utf-8")
        assert "WEB_URL_RE" in src, "web URL regex missing"
        assert "web-link" in src, "web-link class missing"
        # Open-in-browser button
        assert "openExternal" in src or "window.open" in src

    def test_web_open_btn_in_css(self):
        css = (Path(__file__).parent.parent / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        assert "web-open-btn" in css, "web-open-btn CSS missing"
        assert "stream-card.web-link" in css


# ----------------------------------------------------------------------
# 6. Jailbreak toggle in frontend
# ----------------------------------------------------------------------

class TestJailbreakToggle:
    def test_toggle_in_html(self):
        html = (Path(__file__).parent.parent / "frontend" / "home.html").read_text(encoding="utf-8")
        assert "jailbreakToggle" in html, "jailbreakToggle button missing"

    def test_toggle_in_js(self):
        src = (Path(__file__).parent.parent / "frontend" / "js" / "main.js").read_text(encoding="utf-8")
        assert "jailbreakToggle" in src
        assert "coreJailbreakActive" in src
        assert "core_jailbreak" in src
        # core_jailbreak попадает в payload через agentMselCurrent() (объединяет
        # core-тумблеры + мульти-выбор в шапке) — вызывается и в WS, и в fetch.
        assert "if (coreJailbreakActive) arr.push('core_jailbreak')" in src
        assert src.count("agentMselCurrent()") >= 2

    def test_agents_json_has_jailbreak(self):
        p = Path(__file__).parent.parent / "backend" / "agents.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            ids = [a.get("id") for a in data.get("agents", [])]
            assert "core_jailbreak" in ids, "agents.json not synced with core_jailbreak"
