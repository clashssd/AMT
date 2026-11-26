"""
backend/api/logs.py

API endpoint для dashboard логов.
Предоставляет доступ к структурированным логам.
"""

from fastapi import APIRouter, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import os

from backend.logging_structured import LOG_DIR

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def get_logs(
    from: Optional[str] = Query(None, description="Дата начала (ISO format)"),
    to: Optional[str] = Query(None, description="Дата окончания (ISO format)"),
    level: Optional[str] = Query(None, description="Уровни через запятую: info,error,warn,debug"),
    module: Optional[str] = Query(None, description="Фильтр по модулю"),
    search: Optional[str] = Query(None, description="Текстовый поиск"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Возвращает список лог-событий с фильтрами и пагинацией.
    """
    # Определяем период
    if not to:
        to_dt = datetime.utcnow()
    else:
        to_dt = datetime.fromisoformat(to.replace("Z", ""))
    
    if not from:
        # Дефолт: 24 часа
        from_dt = to_dt - timedelta(hours=24)
    else:
        from_dt = datetime.fromisoformat(from.replace("Z", ""))
    
    # Загружаем логи
    all_events = _load_logs(from_dt, to_dt)
    
    # Применяем фильтры
    if level:
        levels = [l.strip() for l in level.split(",")]
        all_events = [e for e in all_events if e.get("level") in levels]
    
    if module:
        all_events = [e for e in all_events if e.get("module") == module]
    
    if search:
        search_lower = search.lower()
        all_events = [
            e for e in all_events
            if search_lower in e.get("message", "").lower() or
               search_lower in e.get("event", "").lower() or
               search_lower in json.dumps(e.get("data", {})).lower()
        ]
    
    # Сортируем по времени (новые сверху)
    all_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Пагинация
    total = len(all_events)
    start = (page - 1) * limit
    end = start + limit
    paged_events = all_events[start:end]
    
    # Сводка
    summary = _calculate_summary(all_events)
    
    return {
        "events": paged_events,
        "total": total,
        "page": page,
        "limit": limit,
        "summary": summary
    }


def _load_logs(from_dt: datetime, to_dt: datetime) -> List[Dict[str, Any]]:
    """Загружает логи из файлов JSONL."""
    events = []
    
    # Определяем файлы
    from_date_str = from_dt.strftime("%Y-%m-%d")
    to_date_str = to_dt.strftime("%Y-%m-%d")
    
    # Загружаем все файлы в периоде
    date = from_dt
    while date <= to_dt:
        date_str = date.strftime("%Y-%m-%d")
        log_file = LOG_DIR / f"amt_events-{date_str}.jsonl"
        
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        
                        # Фильтруем по времени
                        event_ts = datetime.fromisoformat(event.get("timestamp", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
                        if from_dt <= event_ts <= to_dt:
                            events.append(event)
                    except json.JSONDecodeError:
                        continue
        
        date += timedelta(days=1)
    
    return events


def _calculate_summary(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Вычисляет сводную статистику."""
    total = len(events)
    errors = sum(1 for e in events if e.get("level") == "error")
    
    # Среднее время
    durations = [
        e.get("data", {}).get("duration_ms")
        for e in events
        if e.get("data", {}).get("duration_ms") is not None
    ]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    # Активные MCP
    active_mcp = set()
    for e in events:
        if e.get("module") == "mcp_manager" and e.get("event") == "server_connect":
            server_id = e.get("data", {}).get("server_id")
            if server_id:
                active_mcp.add(server_id)
    
    return {
        "total_events": total,
        "errors": errors,
        "avg_response_time_ms": round(avg_duration, 2),
        "active_mcp_servers": len(active_mcp)
    }
