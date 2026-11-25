"""Pytest configuration: isolate backend state between tests.

Each test run that imports `main` will use temp dirs for logs/chats/files
and a fresh memory/orchestrator, so tests don't pollute the real project.
"""
import os
import sys
import json
import pytest

# Make backend importable
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(BACKEND_DIR))


@pytest.fixture
def tmp_backend(tmp_path, monkeypatch):
    """Redirect all persistent files (logs, chats, files, memory, settings,
    orchestrator config/stats) to a temp dir before importing main."""
    logs_dir = tmp_path / "logs"
    chats_dir = tmp_path / "chats"
    files_dir = tmp_path / "files"
    mem_file = tmp_path / "memory.json"
    settings_file = tmp_path / "settings.json"
    orch_stats = tmp_path / "orch_stats.json"

    logs_dir.mkdir()
    chats_dir.mkdir()

    # Pre-create settings without a key
    settings_file.write_text(json.dumps({
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": "",
        "model": "gpt-4o-mini",
        "systemPrompt": "",
        "temperature": 0.7,
        "maxTokens": 4096,
        "contextWindow": 128000,
        "httpProxy": "",
        "httpsProxy": "",
    }))

    monkeypatch.setenv("AMT_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("AMT_CHATS_DIR", str(chats_dir))
    monkeypatch.setenv("AMT_FILES_DIR", str(files_dir))
    monkeypatch.setenv("AMT_MEMORY_FILE", str(mem_file))
    monkeypatch.setenv("AMT_SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("AMT_ORCH_STATS", str(orch_stats))
    monkeypatch.setenv("AMT_AGENTS_FILE", str(tmp_path / "agents.json"))
    monkeypatch.setenv("AMT_KEYS_FILE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("AMT_SESSIONS_FILE", str(tmp_path / "sessions.json"))
    monkeypatch.setenv("AMT_AGENTS_FILE", str(tmp_path / "agents.json"))
    monkeypatch.setenv("AMT_KEYS_FILE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("AMT_BG_DIR", str(tmp_path / "backgrounds"))
    monkeypatch.setenv("AMT_CONFIGS_DIR", str(tmp_path / "configs"))
    monkeypatch.setenv("AMT_PROJECTS_CURRENT", str(tmp_path / "projects_current.json"))
    monkeypatch.setenv("AMT_EXTENSIONS_STATE", str(tmp_path / "extensions_state.json"))
    monkeypatch.setenv("AMT_SYSINTERACTION_FILE", str(tmp_path / "sysinteraction.json"))
    monkeypatch.setenv("AMT_TOOLS_CONFIG", str(tmp_path / "tools_config.json"))
    monkeypatch.setenv("AMT_TOOLS_LOG", str(tmp_path / "tools_log.jsonl"))
    monkeypatch.setenv("AMT_DESKTOP_LOG", str(tmp_path / "desktop_log.jsonl"))
    (tmp_path / "backgrounds").mkdir()
    (tmp_path / "configs").mkdir()

    return {
        "tmp": tmp_path,
        "logs_dir": logs_dir,
        "chats_dir": chats_dir,
        "files_dir": files_dir,
        "mem_file": mem_file,
        "settings_file": settings_file,
        "orch_stats": orch_stats,
    }
