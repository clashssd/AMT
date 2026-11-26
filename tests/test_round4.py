"""Round-4: dashboard log parsing + storage collapse + file-gen core_agents + global player buttons + SVG tabs."""
import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(BASE, "backend", "main.py")
MAIN_JS = os.path.join(BASE, "frontend", "js", "main.js")
HOME_HTML = os.path.join(BASE, "frontend", "home.html")
STYLE_CSS = os.path.join(BASE, "frontend", "css", "style.css")
IPC_JS = os.path.join(BASE, "electron", "ipc.js")
PRELOAD_JS = os.path.join(BASE, "electron", "preload.js")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _dash_block(include_build=False):
    """Срез кода _parse_kv + _DASH_LINE_RE + _dash_parse_line (+ build_dashboard) из main.py."""
    src = _read(MAIN_PY)
    start = src.index("def _parse_kv")
    if include_build:
        end = src.index("def build_dashboard")
        # конец build_dashboard: следующая топовая def/class/маркер после неё
        bd = end
        nxt = re.search(r"\n(?:def |class |@app\.)", src[bd + 10:])
        end2 = bd + 10 + nxt.start() if nxt else len(src)
        code = src[start:end2]
    else:
        # конец _dash_parse_line: следующая 'def ' после него
        nxt = re.search(r"\ndef ", src[src.index("def _dash_parse_line") + 10:])
        end = src.index("def _dash_parse_line") + 10 + nxt.start()
        code = src[start:end]
    return "import re\n" + code


# ---------- 1. Dashboard line parser ----------

class TestDashboardParser:
    def test_parses_hhmmss_lines(self):
        """Стандартный формат '05:53:23  [RESPONSE]  model=... latency_s=1.86'."""
        ns = {}
        exec(compile(_dash_block(False), "<dash>", "exec"), ns)
        time_s, rest = ns["_dash_parse_line"]("05:53:23  [RESPONSE]  model=x  latency_s=1.86")
        assert time_s == "05:53:23"
        assert rest.startswith("[RESPONSE]")

    def test_parses_full_date_lines(self):
        """'2026-11-23 05:53:23  [TAG]  ...' (если форматтер добавит дату)."""
        ns = {}
        exec(compile(_dash_block(False), "<dash>", "exec"), ns)
        time_s, rest = ns["_dash_parse_line"]("2026-11-23 05:53:23  [SESSION_CREATED]  id=x")
        assert time_s == "05:53:23"
        assert rest.startswith("[SESSION_CREATED]")

    def test_parses_no_time_lines(self):
        """Строки без времени (тестовые / оркестратор без asctime)."""
        ns = {}
        exec(compile(_dash_block(False), "<dash>", "exec"), ns)
        time_s, rest = ns["_dash_parse_line"]("[ERROR]  error=NO_API_KEY")
        assert time_s == ""
        assert rest.startswith("[ERROR]")

    def test_build_dashboard_forms_tasks(self):
        """build_dashboard группирует SESSION_CREATED..RESPONSE в задачу."""
        ns = {}
        exec(compile(_dash_block(True), "<dash>", "exec"), ns)
        lines = [
            "05:53:27  [SESSION_CREATED]  id=chat_1  mode=chat  agent=core_web  key=None",
            "05:53:27  [REQUEST]  model=agnes-3.0-flash  history_len=10  msg_preview=test  key_id=None",
            "05:53:29  [RESPONSE]  model=agnes-3.0-flash  latency_s=1.91  prompt_tokens=6962",
        ]
        dash = ns["build_dashboard"](lines)
        assert dash["stats"]["total"] >= 1
        task = dash["tasks"][0]
        assert task["status"] == "completed"
        assert task["id"] == "chat_1"
        assert task["agent"] == "core_web"
        assert task["duration_s"] > 0


# ---------- 2. SESSION_CREATED logged on имитация path ----------

class TestSessionCreatedOnImitation:
    def test_logged_before_early_return(self):
        src = _read(MAIN_PY)
        # В блоке 'if not api_key:' должна быть log_chat_event SESSION_CREATED ДО return
        m = re.search(r"if not api_key:\s*\n\s*log_chat_event\(\"SESSION_CREATED\".*?\n\s*log_chat_event\(\"ERROR\".*?\n\s*return", src, re.DOTALL)
        assert m, "SESSION_CREATED не логируется на пути имитации"


# ---------- 3. Storage folders collapsible ----------

class TestStorageCollapse:
    def test_group_and_items_classes(self):
        src = _read(MAIN_JS)
        assert "storage-folder-group" in src
        assert "storage-folder-items collapsed" in src, "именованные папки должны быть collapsed по умолчанию"

    def test_toggle_handler(self):
        src = _read(MAIN_JS)
        assert "storage-folder-group > .storage-folder-label:not(.plain)" in src
        assert "classList.toggle('collapsed')" in src

    def test_css_collapse_rules(self):
        src = _read(STYLE_CSS)
        assert ".storage-folder-items.collapsed { display: none; }" in src
        assert ".storage-folder-group.expanded .sf-chevron" in src


# ---------- 4. SVG player tabs ----------

class TestSvgPlayerTabs:
    def test_no_emoji_tabs_in_html(self):
        src = _read(HOME_HTML)
        m = re.search(r'id="playerTabs">(.+?)</div>', src, re.DOTALL)
        assert m, "playerTabs not found"
        block = m.group(1)
        for emoji in ("📹", "🔴", "🔍", "📺"):
            assert emoji not in block, f"emoji {emoji} ещё в табах"
        assert block.count("<svg") >= 4, "ожидаются 4 SVG-иконки в табах"

    def test_svgicon_has_player_keys(self):
        src = _read(MAIN_JS)
        m = re.search(r"function svgIcon\(name\)\s*\{(.+?)\n\}", src, re.DOTALL)
        assert m
        for key in ("video:", "stream:", "search:", "channel:"):
            assert key in m.group(1), f"svgIcon нет ключа '{key}'"


# ---------- 5. Global player buttons (filters/fullscreen in iframe mode) ----------

class TestGlobalPlayerButtons:
    def test_initGlobalPlayerButtons_exists(self):
        src = _read(MAIN_JS)
        assert "function initGlobalPlayerButtons()" in src
        # Вызывается один раз в модуле
        assert "initGlobalPlayerButtons();" in src

    def test_not_inside_initPlayerControls(self):
        """Кнопки фильтров НЕ должны зависеть от initPlayerControls (видео-ветка)."""
        src = _read(MAIN_JS)
        ipc = src.index("function initPlayerControls(")
        end_ipc = src.index("function initGlobalPlayerButtons()", ipc)
        ipc_body = src[ipc:end_ipc]
        # filtersToggle-обработчик должен быть ВНЕ initPlayerControls
        assert "filtersToggle.addEventListener" not in ipc_body, "filtersToggle всё ещё внутри initPlayerControls"

    def test_fullscreen_uses_ipc(self):
        src = _read(MAIN_JS)
        assert "window.api.toggleFullscreen" in src
        ipc_src = _read(IPC_JS)
        assert "window:toggleFullscreen" in ipc_src
        assert "win.setFullScreen" in ipc_src
        preload_src = _read(PRELOAD_JS)
        assert "toggleFullscreen" in preload_src


# ---------- 6. File-gen passes core agents ----------

class TestFileGenCoreAgents:
    def test_activeCoreAgentList_defined(self):
        src = _read(MAIN_JS)
        assert "function activeCoreAgentList()" in src

    def test_file_kind_sends_core_agents(self):
        src = _read(MAIN_JS)
        # Внутри kind==='file' блока: activeCoreAgentList() вызывается и core_agents передаётся
        m = re.search(r"kind === 'file'([\s\S]{0,2000}?const activeCore = activeCoreAgentList\(\);[\s\S]{0,1000}?core_agents:\s*activeCore,)", src)
        assert m, "kind='file' не передаёт core_agents во внутренний /api/chat"

    def test_file_kind_sends_key_id(self):
        src = _read(MAIN_JS)
        m = re.search(r"if \(currentKeyId\) chatBody\.key_id = currentKeyId;", src)
        assert m, "key_id не передаётся во внутренний /api/chat при генерации файла"


# ---------- 7. Media overlay drag handle still intact ----------

class TestMediaOverlayDrag:
    def test_drag_handle_in_html(self):
        src = _read(HOME_HTML)
        assert 'id="mediaOverlayDrag"' in src

    def test_drag_uses_handle(self):
        src = _read(MAIN_JS)
        assert "const dragHandle = document.getElementById('mediaOverlayDrag')" in src
        assert "dragSource" in src
