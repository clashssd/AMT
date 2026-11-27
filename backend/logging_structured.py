"""
logging_structured.py — структурированное логирование JSON с trace_id
"""
import json
import uuid
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional
from pathlib import Path
from datetime import datetime, timezone

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

@dataclass
class LogEvent:
    """Структурированное лог-событие."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    level: str = 'INFO'
    category: str = 'general'
    message: str = ''
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

class StructuredLogger:
    """Структурированный логгер с записью в JSON-файлы."""
    
    # Шумовые категории — скрываются из UI по умолчанию
    _NOISE_CATEGORIES = frozenset({'request_start', 'general'})
    
    def __init__(self, log_dir: Path = LOG_DIR):
        self.log_dir = log_dir
        self.log_dir.mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self._active_traces: Dict[str, str] = {}
    
    def new_trace(self) -> str:
        """Создаёт новый trace_id."""
        trace_id = str(uuid.uuid4())
        self._active_traces[trace_id] = trace_id
        return trace_id
    
    def start_request(self, request_id: str, user_message: str = '') -> str:
        """Начинает трекер запроса."""
        trace_id = self.new_trace()
        self.log('DEBUG', 'request_start', f'Начался запрос: {user_message[:100]}', 
                 trace_id=trace_id, metadata={'request_id': request_id})
        return trace_id
    
    def log(self, level: str, category: str, message: str, 
            trace_id: Optional[str] = None, session_id: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None) -> None:
        """Записывает лог-событие."""
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        
        event = LogEvent(
            level=level,
            category=category,
            message=message,
            trace_id=trace_id,
            session_id=session_id,
            metadata=metadata or {}
        )
        
        self._write_event(event)
    
    def _write_event(self, event: LogEvent) -> None:
        """Записывает событие в файл."""
        with self._lock:
            # Файл по дате
            date_str = event.timestamp[:10]  # YYYY-MM-DD
            log_file = self.log_dir / f'logs_{date_str}.jsonl'
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(event.to_json() + '\n')
    
    def log_mcp_call(self, server: str, tool: str, params: Dict, result: Any = None, 
                     duration_ms: float = 0, trace_id: Optional[str] = None) -> None:
        """Логирует вызов MCP-инструмента."""
        self.log('INFO', 'mcp_call', f'MCP: {server}.{tool}', 
                 trace_id=trace_id,
                 metadata={
                     'server': server,
                     'tool': tool,
                     'params': params,
                     'result_type': type(result).__name__ if result else None,
                     'duration_ms': duration_ms
                 })
    
    def log_ai_call(self, model: str, prompt_tokens: int, completion_tokens: int, 
                    duration_ms: float, trace_id: Optional[str] = None) -> None:
        """Логирует вызов ИИ."""
        self.log('INFO', 'ai_call', f'AI: {model}',
                 trace_id=trace_id,
                 metadata={
                     'model': model,
                     'prompt_tokens': prompt_tokens,
                     'completion_tokens': completion_tokens,
                     'total_tokens': prompt_tokens + completion_tokens,
                     'duration_ms': duration_ms
                 })
    
    def log_tool_call(self, tool: str, params: Dict, success: bool, 
                      error: str = None, duration_ms: float = 0, 
                      trace_id: Optional[str] = None) -> None:
        """Логирует вызов инструмента."""
        level = 'INFO' if success else 'ERROR'
        self.log(level, 'tool_call', f'Tool: {tool} ({("OK" if success else "FAIL")})',
                 trace_id=trace_id,
                 metadata={
                     'tool': tool,
                     'params': params,
                     'success': success,
                     'error': error,
                     'duration_ms': duration_ms
                 })
    
    def get_recent_logs(self, limit: int = 100, 
                       category: Optional[str] = None,
                       level: Optional[str] = None,
                       trace_id: Optional[str] = None,
                       include_noise: bool = False) -> list:
        """Читает последние лог-события. По умолчанию скрывает шумовые категории."""
        events = []
        files = sorted(self.log_dir.glob('logs_*.jsonl'), reverse=True)
        scan_limit = limit * 5 if not include_noise else limit
        
        for log_file in files:
            if len(events) >= scan_limit:
                break
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if len(events) >= scan_limit:
                        break
                    try:
                        event = json.loads(line)
                        # Фильтры
                        if category and event.get('category') != category:
                            continue
                        if level and event.get('level') != level:
                            continue
                        if trace_id and event.get('trace_id') != trace_id:
                            continue
                        # По умолчанию скрываем шумовые категории
                        if not include_noise and event.get('category') in self._NOISE_CATEGORIES:
                            continue
                        events.append(event)
                    except json.JSONDecodeError:
                        continue
        
        return events[-limit:]
    
    def get_trace(self, trace_id: str) -> list:
        """Возвращает все события по trace_id."""
        return self.get_recent_logs(limit=1000, trace_id=trace_id, include_noise=True)
    
    def get_dashboard_data(self, time_window_minutes: int = 60) -> Dict[str, Any]:
        """Возвращает данные для дашборда (без шумовых категорий)."""
        events = self.get_recent_logs(limit=1000)
        
        # Формируем статистику
        categories = {}
        levels = {}
        traces = {}
        
        for event in events:
            cat = event.get('category', 'unknown')
            lvl = event.get('level', 'INFO')
            tid = event.get('trace_id', 'unknown')
            
            categories[cat] = categories.get(cat, 0) + 1
            levels[lvl] = levels.get(lvl, 0) + 1
            traces[tid] = traces.get(tid, 0) + 1
        
        return {
            'total_events': len(events),
            'by_category': categories,
            'by_level': levels,
            'unique_traces': len(traces),
            'recent_events': events[:50]
        }
    
    def clear_logs(self) -> Dict[str, Any]:
        """Удаляет все JSONL файлы структурных логов."""
        import os
        deleted = []
        for f in self.log_dir.glob('logs_*.jsonl'):
            try:
                f.unlink()
                deleted.append(f.name)
            except OSError:
                pass
        return {'deleted': len(deleted), 'files': deleted}

# Глобальный инстанс
logger = StructuredLogger()
