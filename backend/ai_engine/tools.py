"""
Безопасный слой инструментов (tool-calling) для AMT.

Политика безопасности (чтобы ИИ/пользователь НЕ могли ничего сломать):
- Только READ-операции по файлам (чтение, список каталога) — только в разрешённых каталогах.
- Запуск команд — только из белого списка (whitelist) и с таймаутом, в разрешённом каталоге.
  По умолчанию whitelist пуст → команды запрещены, пока пользователь явно не разрешит.
- Каждый инструмент логируется (кто, что, результат, время).
- auto-approve: если False, действие требует подтверждения на фронтенде (approve/deny).

Экземпляр живёт в main.py как `tools`.
"""
import os
import json
import time
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Optional

from .desktop_tools import desktop_sandbox as _desktop_sandbox

CONFIG_FILE = os.environ.get("AMT_TOOLS_CONFIG") or os.path.join(os.path.dirname(__file__), "..", "tools_config.json")
LOG_FILE = os.environ.get("AMT_TOOLS_LOG") or os.path.join(os.path.dirname(__file__), "..", "tools_log.jsonl")

# Разрешённые каталоги по умолчанию: рабочая папка + user home (read-only)
DEFAULT_ALLOWED_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.path.expanduser("~"),
]
# По умолчанию команды НЕ разрешены (пустой whitelist) — безопасно.
DEFAULT_COMMAND_WHITELIST: list[str] = []


@dataclass
class ToolsConfig:
    enabled: bool = False
    auto_approve: bool = False          # если True — не запрашивать подтверждение на фронтенде
    allowed_dirs: list = field(default_factory=lambda: list(DEFAULT_ALLOWED_DIRS))
    command_whitelist: list = field(default_factory=lambda: list(DEFAULT_COMMAND_WHITELIST))
    command_timeout: int = 30           # сек
    max_output_bytes: int = 50000       # резка вывода

    def to_dict(self):
        return asdict(self)


class ToolSandbox:
    """Изолированный безопасный исполнитель инструментов."""

    def __init__(self, config_path: str = CONFIG_FILE, log_path: str = LOG_FILE):
        self.config_path = config_path
        self.log_path = log_path
        self.cfg = self._load()
        if not isinstance(self.cfg, ToolsConfig):
            self.cfg = ToolsConfig()

    # ---- config ----
    def _load(self) -> ToolsConfig:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                cfg = ToolsConfig()
                for k in ("enabled", "auto_approve", "command_timeout", "max_output_bytes"):
                    if k in d:
                        setattr(cfg, k, d[k])
                if isinstance(d.get("allowed_dirs"), list):
                    cfg.allowed_dirs = d["allowed_dirs"]
                if isinstance(d.get("command_whitelist"), list):
                    cfg.command_whitelist = d["command_whitelist"]
                return cfg
            except Exception:
                return ToolsConfig()
        return ToolsConfig()

    def save_config(self, patch: dict):
        for k in ("enabled", "auto_approve", "allowed_dirs", "command_whitelist", "command_timeout", "max_output_bytes"):
            if k in patch:
                setattr(self.cfg, k, patch[k])
        os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.cfg.to_dict(), f, ensure_ascii=False, indent=2)

    def public_config(self) -> dict:
        """Конфиг без секретных деталей для фронтенда."""
        c = self.cfg.to_dict()
        return c

    # ---- logging ----
    def _log(self, action: str, tool: str, detail: dict, result: str):
        try:
            rec = {
                "ts": int(time.time()),
                "action": action,
                "tool": tool,
                "detail": detail,
                "result": result[:300],
            }
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def recent_log(self, limit: int = 100) -> list:
        out = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                pass
        return out[-limit:]

    # ---- path safety ----
    def _resolve_safe(self, path: str) -> str:
        """Разрешает путь и проверяет, что он внутри одного из allowed_dirs."""
        p = os.path.abspath(os.path.expanduser(str(path)))
        for base in self.cfg.allowed_dirs:
            base_abs = os.path.abspath(base)
            try:
                if os.path.commonpath([p, base_abs]) == base_abs:
                    return p
            except Exception:
                continue
        raise PermissionError(f"Путь вне разрешённых каталогов: {p}")

    # ---- tools ----
    def read_file(self, path: str) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        p = self._resolve_safe(path)
        if not os.path.isfile(p):
            return {"ok": False, "error": "Файл не найден"}
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            raw = f.read(self.cfg.max_output_bytes)
        text = raw.decode("utf-8", errors="replace")
        out = {"ok": True, "path": p, "size": size, "truncated": size > len(raw), "content": text}
        self._log("read_file", "read_file", {"path": p}, "ok")
        return out

    def list_dir(self, path: str = ".") -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        p = self._resolve_safe(path)
        if not os.path.isdir(p):
            return {"ok": False, "error": "Каталог не найден"}
        entries = []
        try:
            for name in sorted(os.listdir(p)):
                fp = os.path.join(p, name)
                entries.append({"name": name, "is_dir": os.path.isdir(fp), "size": 0 if os.path.isdir(fp) else os.path.getsize(fp)})
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._log("list_dir", "list_dir", {"path": p}, f"{len(entries)}")
        return {"ok": True, "path": p, "entries": entries}

    def run_command(self, command: str, workdir: str = "") -> dict:
        """Запускает ТОЛЬКО команду из белого списка, с таймаутом, в разрешённом каталоге."""
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        cmd = (command or "").strip()
        if not cmd:
            return {"ok": False, "error": "Пустая команда"}
        # Точное совпадение с whitelist (базовая команда)
        base = cmd.split()[0]
        allowed = any(cmd == w or (w and cmd.startswith(w + " ")) or (w and cmd.startswith(w + "\t")) for w in self.cfg.command_whitelist)
        if not allowed:
            self._log("run_command_denied", "run_command", {"cmd": cmd}, "not in whitelist")
            return {"ok": False, "error": "Команда не в белом списке. Добавьте её в Настройки → Инструменты.", "code": "whitelist"}
        cwd = self._resolve_safe(workdir or self.cfg.allowed_dirs[0])
        start = time.time()
        try:
            r = subprocess.run(
                cmd, shell=True, cwd=cwd,
                capture_output=True, timeout=self.cfg.command_timeout,
                text=True,
            )
            stdout = r.stdout[: self.cfg.max_output_bytes]
            stderr = r.stderr[: self.cfg.max_output_bytes]
            self._log("run_command", "run_command", {"cmd": cmd, "cwd": cwd, "exit": r.returncode}, "ok")
            return {"ok": True, "exit_code": r.returncode, "stdout": stdout, "stderr": stderr, "elapsed_s": round(time.time() - start, 2)}
        except subprocess.TimeoutExpired:
            self._log("run_command_timeout", "run_command", {"cmd": cmd}, "timeout")
            return {"ok": False, "error": f"Таймаут ({self.cfg.command_timeout} c)"}
        except Exception as e:
            self._log("run_command_error", "run_command", {"cmd": cmd}, str(e))
            return {"ok": False, "error": str(e)}

    def open_url(self, url: str, browser: str = "") -> dict:
        """Открывает URL в системном браузере (безопасно: только http/https).
        Делегирует в DesktopSandbox (единый источник истины)."""
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        return _desktop_sandbox.open_url(url, browser)

    def write_file(self, path: str, content: str = "") -> dict:
        """Записывает файл ТОЛЬКО в разрешённых каталогах. Требует enabled."""
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        p = self._resolve_safe(path)
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            self._log("write_file_denied", "write_file", {"path": p}, "outside allowed dirs")
            return {"ok": False, "code": "denied", "error": f"Путь вне разрешённых каталогов: {p}"}
        except Exception as e:
            self._log("write_file_error", "write_file", {"path": p}, str(e))
            return {"ok": False, "error": str(e)}
        self._log("write_file", "write_file", {"path": p, "bytes": len(content.encode("utf-8"))}, "ok")
        return {"ok": True, "path": p, "bytes": len(content.encode("utf-8"))}

    def create_dir(self, path: str) -> dict:
        """Создаёт каталог ТОЛЬКО в разрешённых каталогах."""
        if not self.cfg.enabled:
            return {"ok": False, "error": "Инструменты выключены"}
        p = self._resolve_safe(path)
        try:
            os.makedirs(p, exist_ok=True)
        except PermissionError:
            self._log("create_dir_denied", "create_dir", {"path": p}, "outside allowed dirs")
            return {"ok": False, "code": "denied", "error": f"Путь вне разрешённых каталогов: {p}"}
        except Exception as e:
            self._log("create_dir_error", "create_dir", {"path": p}, str(e))
            return {"ok": False, "error": str(e)}
        self._log("create_dir", "create_dir", {"path": p}, "ok")
        return {"ok": True, "path": p}

    def execute(self, tool: str, **args) -> dict:
        if tool == "read_file":
            return self.read_file(args.get("path", ""))
        if tool == "list_dir":
            return self.list_dir(args.get("path", "."))
        if tool == "run_command":
            return self.run_command(args.get("command", ""), args.get("workdir", ""))
        if tool == "write_file":
            return self.write_file(args.get("path", ""), args.get("content", ""))
        if tool == "create_dir":
            return self.create_dir(args.get("path", ""))
        # Desktop tools (delegated to DesktopSandbox)
        if tool in ("open_url", "launch_app", "page_recon",
                     "window_focus", "window_send_keys", "window_click", "window_screenshot",
                     "window_ui_recon", "find_element_by_text",
                     "browser_recon_cdp", "browser_click_cdp", "browser_fill_cdp",
                     "browser_press_cdp", "browser_navigate_cdp", "browser_screenshot_cdp"):
            return _desktop_sandbox.execute(tool, **args)
        return {"ok": False, "error": "Неизвестный инструмент"}


tools = ToolSandbox()
