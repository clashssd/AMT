"""AI Orchestrator — контроллер качества чатов.

Роль оркестратора:
1. **Контроль контекста** — следит, чтобы модель не теряла нить диалога.
   Перед каждым ответом проверяет длину истории и при необходимости
   поджимает старые сообщения (summary-сжатие).
2. **Контроль роли** — следит, чтобы модель не уходила от системного
   промпта. После каждого ответа — быстрая проверка на «дрейф роли».
3. **Умное сохранение** — определяет момент, когда чат стоит сохранить
   (по длине, по завершённости темы), и маркирует чат.
4. **Мониторинг модели** — замеряет задержки, ошибки, качество (по длине
   и полноте ответов), пишет подробные логи с пом��ткой [Orchestrator].
5. **Настройка** — параметры (пороги, включённость проверок) хранятся
   в оркестраторе и могут меняться через API.

Логи оркестратора пишутся в тот же лог-файл, но с меткой [Orchestrator]
в начале строки, чтобы их было легко отличить и фильтровать.
"""

import json
import os
import time
import asyncio
from datetime import datetime
from typing import Optional

import httpx


class Orchestrator:
    def __init__(self, log_dir: str, settings_path: str):
        self.log_dir = log_dir
        self.settings_path = settings_path
        self.log_path = self._current_log_path()
        # Настройки оркестратора
        self.config = {
            "enabled": True,
            "auto_mode": True,
            "role_drift_check": True,
            "monitor_latency": True,
            "auto_save_threshold": 10,
            "keep_full_context": True,
        }
        self._load_config()
        # Статистика мониторинга
        self.stats = {
            "total_requests": 0,
            "total_errors": 0,
            "avg_latency_s": 0.0,
            "latencies": [],
            "role_drift_events": 0,
            "context_compactions": 0,
        }
        self._restore_stats()

    # ---------- Логирование ----------

    def _current_log_path(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"chat_{today}.log")

    def log(self, event: str, detail: dict):
        """Пишет лог с пометкой [Orchestrator] сверху."""
        try:
            # Если день сменился — переключаем путь к файлу
            if self.log_path != self._current_log_path():
                self.log_path = self._current_log_path()
            ts = datetime.now().strftime("%H:%M:%S")
            parts = [f"[Orchestrator] [{event}]"]
            for k, v in detail.items():
                parts.append(f"{k}={v}")
            line = f"{ts}  " + "  ".join(parts)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # лог не должен ронять приложение

    # ---------- Конфигурация ----------

    def _load_config(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.config.update(data.get("orchestrator", {}))
            except Exception:
                pass

    def save_config(self):
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump({"orchestrator": self.config}, f, ensure_ascii=False, indent=2)

    def _restore_stats(self):
        stats_file = os.path.join(self.log_dir, "orchestrator_stats.json")
        if os.path.exists(stats_file):
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    self.stats.update(json.load(f))
            except Exception:
                pass

    def save_stats(self):
        try:
            stats_file = os.path.join(self.log_dir, "orchestrator_stats.json")
            os.makedirs(os.path.dirname(stats_file), exist_ok=True)
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 1. Контроль контекста ----------

    def estimate_tokens(self, text: str) -> int:
        """Простая оценка токенов (кириллица ~2.7, латиница ~4 на токен)."""
        if not text:
            return 0
        cyr = latin = other = 0
        for ch in text:
            code = ord(ch)
            if 0x0400 <= code <= 0x04FF:
                cyr += 1
            elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
                latin += 1
            else:
                other += 1
        return int(cyr / 2.7 + latin / 4 + other / 4) + 1

    def context_size(self, history: list) -> int:
        total = 0
        for m in history:
            total += self.estimate_tokens(m.get("content", ""))
        return total

    def compact_context(self, history: list, system_prompt: str, context_window: int = 128000) -> list:
        """Сохраняет ВЕСЬ контекст.

        Поджимание происходит только в одном случае — когда суммарный контекст
        реально превышает окно модели (иначе модель его физически не примет).
        В «авто»-режиме лимит рассчитывается от context_window модели.
        """
        size = self.context_size(history)
        # Мягкий предел = 90% от окна модели. Ниже него — полностью сохраняем.
        limit = int(context_window * 0.9) if self.config.get("auto_mode") else 128000
        if size < limit:
            return history

        keep_last = 8
        if len(history) <= keep_last:
            return history

        old = history[:-keep_last]
        recent = history[-keep_last:]

        summary_parts = []
        for m in old:
            role = "Пользователь" if m.get("role") == "user" else "Ассистент"
            content = m.get("content", "")[:200]
            summary_parts.append(f"{role}: {content}")
        summary_text = (
            "[Сводка предыдущей части разговора — полный контекст превысил окно модели, "
            "старая часть сжата]\n"
            + "\n".join(summary_parts)
        )

        compacted = [{"role": "system", "content": (system_prompt + "\n\n" + summary_text)}]
        compacted.extend(recent)

        self.stats["context_compactions"] += 1
        self.save_stats()
        self.log("CONTEXT_COMPACTED", {
            "before_msgs": len(history),
            "after_msgs": len(compacted),
            "before_tokens": size,
            "limit": limit,
        })
        return compacted

    # ---------- 2. Контроль роли ----------

    def check_role_drift(self, system_prompt: str, assistant_response: str) -> bool:
        """Эвристика: не отклонилась ли модель от роли.

        Проверяет маркеры, типичные для «срыва» из роли:
        - отрицание системной инструкции
        - просьба «забудь промпт»
        - выход из заданного стиля
        """
        if not self.config["role_drift_check"]:
            return False
        markers = [
            "я не могу следовать",
            "забудь всё",
            "я не ассистент",
            "без ограничений",
            "игнорируй инструкцию",
        ]
        text_lower = assistant_response.lower()
        for marker in markers:
            if marker in text_lower:
                self.stats["role_drift_events"] += 1
                self.save_stats()
                self.log("ROLE_DRIFT", {"marker": marker, "preview": assistant_response[:80]})
                return True
        return False

    def drift_reminder(self, system_prompt: str) -> str:
        """Возвращает напоминание-системный промпт, если был дрейф."""
        if self.stats["role_drift_events"] > 0:
            return (
                system_prompt + "\n\n"
                "[Важно от Orchestrator] Ты строго придерживайся своей роли и инструкций. "
                "Не выходи за рамки. Если вопрос выходит из темы — мягко верни разговор к цели."
            )
        return system_prompt

    # ---------- 4. Мониторинг ----------

    def record_response(self, latency_s: float, success: bool, response_len: int = 0):
        """Фиксирует задержку и результат для мониторинга ка��ества."""
        if not self.config["monitor_latency"]:
            return
        self.stats["total_requests"] += 1
        if not success:
            self.stats["total_errors"] += 1
        self.stats["latencies"].append(latency_s)
        # храним последние 100 для усреднения
        self.stats["latencies"] = self.stats["latencies"][-100:]
        if self.stats["latencies"]:
            self.stats["avg_latency_s"] = round(
                sum(self.stats["latencies"]) / len(self.stats["latencies"]), 2
            )
        self.save_stats()
        self.log("MONITOR", {
            "latency_s": round(latency_s, 2),
            "success": success,
            "resp_len": response_len,
            "avg_latency": self.stats["avg_latency_s"],
            "total_req": self.stats["total_requests"],
            "total_err": self.stats["total_errors"],
        })

    def auto_tune(self):
        """Авто-подстройка параметров под наблюдаемое поведение чатов."""
        if not self.config.get("auto_mode"):
            return
        avg = self.stats["avg_latency_s"]
        if avg > 8 and self.stats["total_requests"] > 5:
            self.config["auto_save_threshold"] = 20
        elif avg < 3 and self.stats["total_requests"] > 5:
            self.config["auto_save_threshold"] = 5
        self.log("AUTO_TUNE", {"avg_latency": avg, "auto_save_threshold": self.config["auto_save_threshold"]})
        self.save_config()

    def get_health_report(self) -> dict:
        """Сводка для отображения в UI мониторинга."""
        return {
            "total_requests": self.stats["total_requests"],
            "total_errors": self.stats["total_errors"],
            "avg_latency_s": self.stats["avg_latency_s"],
            "role_drift_events": self.stats["role_drift_events"],
            "context_compactions": self.stats["context_compactions"],
            "last_latency": self.stats["latencies"][-1] if self.stats["latencies"] else 0,
        }

    # ---------- 3. Умное сохранение ----------

    def should_auto_save(self, message_count: int) -> bool:
        """Определяет, пора ли сохранить чат (по пороговому числу сообщений)."""
        return message_count > 0 and message_count % self.config["auto_save_threshold"] == 0

    def mark_chat_complete(self, chat_id: str, reason: str = "auto"):
        self.log("CHAT_SAVED", {"chat_id": chat_id, "reason": reason})
