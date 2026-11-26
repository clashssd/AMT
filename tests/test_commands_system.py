"""
test_commands_system.py — тесты системы slash-команд и структурированного логирования
"""
import sys
import os
import json
import uuid
from pathlib import Path

# Добавляем backend в путь
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from command_engine import CommandParser, build_context, REGISTRY, ParsedCommand
from logging_structured import StructuredLogger, LogEvent, LOG_DIR


class TestCommandParser:
    """Тесты парсера slash-команд."""
    
    def setup_method(self):
        self.parser = CommandParser(REGISTRY)
    
    def test_single_command_no_args(self):
        """Одна команда без аргументов."""
        cmds, text = self.parser.parse("/jailbreak")
        assert len(cmds) == 1
        assert cmds[0].id == "jailbreak"
        assert text == ""
    
    def test_single_command_with_text(self):
        """Команда + текст."""
        cmds, text = self.parser.parse("/jailbreak напиши код")
        assert len(cmds) == 1
        assert cmds[0].id == "jailbreak"
        assert "напиши код" in text
    
    def test_two_commands_with_plus(self):
        """Две команды через +."""
        cmds, text = self.parser.parse("/rag + /jailbreak сделай X")
        assert len(cmds) == 2
        assert cmds[0].id == "rag"
        assert cmds[1].id == "jailbreak"
        assert "сделай X" in text
    
    def test_three_commands(self):
        """Три команды через +."""
        cmds, text = self.parser.parse("/rag + /orchestrator + /memory проанализируй")
        assert len(cmds) == 3
        assert cmds[0].id == "rag"
        assert cmds[1].id == "orchestrator"
        assert cmds[2].id == "memory"
    
    def test_no_commands(self):
        """Без команд — чистый текст."""
        cmds, text = self.parser.parse("привет мир")
        assert len(cmds) == 0
        assert text == "привет мир"
    
    def test_gen_file_xlsx(self):
        """Генерация файла xlsx."""
        cmds, text = self.parser.parse("/gen file xlsx таблица продаж")
        assert len(cmds) == 1
        assert cmds[0].id == "gen"
        assert cmds[0].args.get('type') == 'file'
        assert cmds[0].args.get('filetype') == 'xlsx'
    
    def test_gen_photo(self):
        """Генерация фото."""
        cmds, text = self.parser.parse("/gen photo закат над морем")
        assert len(cmds) == 1
        assert cmds[0].id == "gen"
        assert cmds[0].args.get('type') == 'photo'
    
    def test_gen_combo(self):
        """Комбинированная генерация."""
        cmds, text = self.parser.parse("/gen combo photo:закат,video:волны,audio:рассказ")
        assert len(cmds) == 1
        assert cmds[0].id == 'gen'
        assert cmds[0].args.get('type') == 'combo'
        assert len(cmds[0].args.get('items', [])) == 3
    
    def test_agent_command(self):
        """Команда агента."""
        cmds, text = self.parser.parse("/agent web найди информацию")
        assert len(cmds) == 1
        assert cmds[0].id == "agent"
        assert cmds[0].args.get('name') == "web"
    
    def test_navigation_command(self):
        """Навигационная команда."""
        cmds, text = self.parser.parse("/nav_settings")
        assert len(cmds) == 1
        assert cmds[0].id == "nav_settings"
    
    def test_alias_resolution(self):
        """Алиас команды."""
        cmds, text = self.parser.parse("/jb")
        assert len(cmds) == 1
        assert cmds[0].id == "jailbreak"  # jb → jailbreak
    
    def test_combined_gen_and_rag(self):
        """Комбинация /gen и /rag."""
        cmds, text = self.parser.parse("/gen file py скрипт + /rag")
        assert len(cmds) == 2
        cmd_ids = [c.id for c in cmds]
        assert "gen" in cmd_ids
        assert "rag" in cmd_ids


class TestBuildContext:
    """Тесты построения контекста команд."""
    
    def setup_method(self):
        self.parser = CommandParser(REGISTRY)
    
    def test_jailbreak_context(self):
        """Контекст jailbreak."""
        cmds, _ = self.parser.parse("/jailbreak")
        ctx = build_context(cmds, REGISTRY)
        assert ctx.enable_jailbreak is True
        assert len(ctx.system_prompt_fragments) > 0
    
    def test_rag_context(self):
        """Контекст RAG."""
        cmds, _ = self.parser.parse("/rag")
        ctx = build_context(cmds, REGISTRY)
        assert "rag" in ctx.enabled_mcp
        assert len(ctx.enabled_tools) > 0
    
    def test_combined_context(self):
        """Комбинированный контекст."""
        cmds, _ = self.parser.parse("/rag + /jailbreak")
        ctx = build_context(cmds, REGISTRY)
        assert "rag" in ctx.enabled_mcp
        assert ctx.enable_jailbreak is True
    
    def test_gen_file_context(self):
        """Контекст генерации файла."""
        cmds, _ = self.parser.parse("/gen file xlsx")
        ctx = build_context(cmds, REGISTRY)
        assert "writer" in ctx.enabled_mcp
        # xlsx → create_office
        assert "create_office" in ctx.enabled_tools
    
    def test_gen_photo_context(self):
        """Контекст генерации фото."""
        cmds, _ = self.parser.parse("/gen photo тест")
        ctx = build_context(cmds, REGISTRY)
        assert "media" in ctx.enabled_mcp
        assert "generate_image" in ctx.enabled_tools


class TestStructuredLogger:
    """Тесты структурированного логирования."""
    
    def test_logger_creates_files(self):
        """Логгер создаёт JSONL-файлы."""
        logger = StructuredLogger()
        trace_id = logger.start_request("test_req")
        assert trace_id is not None
        assert len(trace_id) == 36  # UUID
    
    def test_log_event_structure(self):
        """Структура LogEvent."""
        logger = StructuredLogger()
        trace_id = logger.start_request("test_req", "hello")
        
        # Читаем последний лог-файл
        files = sorted(LOG_DIR.glob('logs_*.jsonl'))
        assert len(files) > 0
        last_file = files[-1]
        
        with open(last_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Последний элемент — наш event
        last_event = json.loads(lines[-1])
        assert last_event['category'] == 'request_start'
        assert last_event['level'] == 'DEBUG'
        assert last_event['trace_id'] == trace_id
        assert last_event['timestamp'] is not None
    
    def test_log_ai_call(self):
        """Логирование AI-вызова."""
        logger = StructuredLogger()
        trace_id = logger.start_request("req1")
        logger.log_ai_call(
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=1500.0,
            trace_id=trace_id
        )
        
        events = logger.get_recent_logs(limit=5, trace_id=trace_id)
        ai_events = [e for e in events if e['category'] == 'ai_call']
        assert len(ai_events) == 1
        assert ai_events[0]['metadata']['model'] == 'test-model'
        assert ai_events[0]['metadata']['prompt_tokens'] == 100
    
    def test_log_mcp_call(self):
        """Логирование MCP-вызова."""
        logger = StructuredLogger()
        trace_id = logger.start_request("req2")
        logger.log_mcp_call(
            server="rag",
            tool="search_documents",
            params={"query": "test"},
            result="found 3 docs",
            duration_ms=500.0,
            trace_id=trace_id
        )
        
        events = logger.get_recent_logs(limit=5, trace_id=trace_id)
        mcp_events = [e for e in events if e['category'] == 'mcp_call']
        assert len(mcp_events) == 1
        assert mcp_events[0]['metadata']['server'] == 'rag'
        assert mcp_events[0]['metadata']['tool'] == 'search_documents'
    
    def test_log_tool_call(self):
        """Логирование tool-вызова."""
        logger = StructuredLogger()
        trace_id = logger.start_request("req3")
        logger.log_tool_call(
            tool="create_office",
            params={"filetype": "xlsx"},
            success=True,
            duration_ms=200.0,
            trace_id=trace_id
        )
        
        events = logger.get_recent_logs(limit=5, trace_id=trace_id)
        tool_events = [e for e in events if e['category'] == 'tool_call']
        assert len(tool_events) == 1
        assert tool_events[0]['metadata']['success'] is True
    
    def test_get_trace(self):
        """Полная цепочка по trace_id."""
        logger = StructuredLogger()
        trace_id = logger.start_request("req4")
        logger.log_ai_call("m", 10, 20, 100.0, trace_id=trace_id)
        logger.log_tool_call("t", {}, True, None, 50.0, trace_id=trace_id)
        
        events = logger.get_trace(trace_id)
        assert len(events) >= 3  # request_start + ai_call + tool_call
    
    def test_dashboard_data(self):
        """Данные для дашборда."""
        logger = StructuredLogger()
        trace_id = logger.start_request("req5")
        logger.log_ai_call("m", 10, 20, 100.0, trace_id=trace_id)
        
        data = logger.get_dashboard_data()
        assert 'total_events' in data
        assert 'by_category' in data
        assert 'by_level' in data
        assert 'unique_traces' in data


class TestCommandRegistry:
    """Тесты реестра команд."""
    
    def test_registry_structure(self):
        """Реестр содержит все 23 команды (15 базовых + 7 кодинг + 1 designer)."""
        assert 'commands' in REGISTRY
        assert len(REGISTRY['commands']) == 23
    
    def test_registry_command_fields(self):
        """Каждая команда имеет обязательные поля."""
        for cmd in REGISTRY['commands']:
            assert 'id' in cmd
            assert 'description' in cmd
            assert 'type' in cmd
    
    def test_registry_aliases(self):
        """Алиасы работают."""
        ids = {c['id'] for c in REGISTRY['commands']}
        assert 'jailbreak' in ids
        assert 'rag' in ids
        assert 'gen' in ids


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
