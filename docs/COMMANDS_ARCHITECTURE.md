# Архитектура Системы Команд, Логирования и Хоткеев

## Обзор

Системаslash-команд — это **overlay на один запрос**, а не переключатель состояния сессии.
Пользователь пишет `/rag + /jailbreak сделай X` — система парсит команды, строит контекст
выполнения (какие тулы разрешены, какой промпт-фрагмент добавить, куда роутить),
выполняет запрос и выбрасывает контекст. Следующее сообщение снова чистое.

## Структура Документа

1. [Быстрые Команды Навигации](#1-быстрые-команды-навигации)
2. [Хоткеи (По Дефолту Не Назначены)](#2-хоткеи)
3. [Логирование (Переделка)](#3-логирование)
4. [Dashboard (Под MCP и Все Функции)](#4-dashboard)
5. [Выбор Генерации (Базовая Модель vs MCP)](#5-выбор-генерации)
6. [Команда /gen (Генерация)](#6-команда-gen)
7. [Интеграция с MCP](#7-интеграция-с-mcp)
8. [Файлы для Создания](#8-файлы-для-создания)
9. [Порядок Реализации](#9-порядок-реализации)

---

## 1. Быстрые Команды Навигации

**Цель:** Быстрый переход между страницами приложения без изменения основной функциональности.

### Реестр Команд

```json
{
  "commands": [
    {
      "id": "nav_home",
      "aliases": ["home", "главная"],
      "description": "Перейти на главную страницу",
      "type": "navigation",
      "target": "home"
    },
    {
      "id": "nav_chat",
      "aliases": ["chat", "чат"],
      "description": "Перейти в чат",
      "type": "navigation",
      "target": "chat"
    },
    {
      "id": "nav_settings",
      "aliases": ["settings", "настройки"],
      "description": "Перейти в настройки",
      "type": "navigation",
      "target": "settings"
    },
    {
      "id": "nav_docs",
      "aliases": ["docs", "документация"],
      "description": "Перейти к документации",
      "type": "navigation",
      "target": "docs"
    },
    {
      "id": "nav_storage",
      "aliases": ["storage", "хранилище"],
      "description": "Перейти в хранилище",
      "type": "navigation",
      "target": "storage"
    },
    {
      "id": "nav_logs",
      "aliases": ["logs", "логи"],
      "description": "Перейти в логи",
      "type": "navigation",
      "target": "logs"
    },
    {
      "id": "command_help",
      "aliases": ["help", "справка"],
      "description": "Показать список всех команд",
      "type": "help",
      "target": "show_help_overlay"
    }
  ]
}
```

### Как Это Работает

**Файл: frontend/js/core/commands.js**

```javascript
// Парсинг и выполнение команд
class CommandParser {
  parse(input) {
    // Пример: "/nav settings + /help"
    const commands = input.match(/\/(\w+)(?:\s+(.*?))?(?=\+|$)/g);
    
    return commands.map(cmd => {
      const match = cmd.match(/\/(\w+)\s*(.*)/);
      return {
        name: match[1],
        args: match[2] ? match[2].split(' ') : []
      };
    });
  }
  
  execute(commands, context) {
    for (const cmd of commands) {
      const handler = this.registry.get(cmd.name);
      
      if (cmd.type === 'navigation') {
        // Навигация — просто переход, без изменения состояния
        navigateTo(cmd.target);
      } else if (cmd.type === 'help') {
        // Help — показать overlay
        showHelpOverlay();
      } else if (cmd.type === 'overlay') {
        // Overlay — временный контекст на один запрос
        this.applyOverlay(cmd, context);
      }
    }
  }
}
```

### UI: Кнопка Help в Скрытом Меню

**В композере (компактном меню):**
- Иконка `?` — при клике показывает dropdown со списком всех команд
- Команды сгруппированы: Навигация / Генерация / Режимы / Быстрые действия
- Каждая команда имеет description и пример использования

### Быстрые Действия (Не Навигация)

```json
{
  "quick_actions": [
    {
      "id": "quick_new_chat",
      "aliases": ["new", "новый чат"],
      "description": "Создать новый чат",
      "action": "create_new_chat"
    },
    {
      "id": "quick_save_chat",
      "aliases": ["save", "сохранить"],
      "description": "Сохранить текущий чат",
      "action": "save_current_chat"
    },
    {
      "id": "quick_export",
      "aliases": ["export", "экспорт"],
      "description": "Экспортировать чат в MD/JSON",
      "action": "export_chat"
    }
  ]
}
```

---

## 2. Хоткеи

**Цель:** Быстрый доступ к командам через клавиатуру. По умолчанию — не назначены.

### Конфигурация

**Файл: frontend/js/core/hotkeys.js**

```javascript
// Конфигурация хоткеев (сохраняется в localStorage)
const HOTKEYS_STORAGE = 'amt_hotkeys';

// По умолчанию: пустой (все хоткеи не назначены)
const defaultHotkeys = {
  'nav_home': '',
  'nav_chat': '',
  'nav_settings': '',
  'nav_docs': '',
  'nav_storage': '',
  'nav_logs': '',
  'command_help': '',
  'quick_new_chat': '',
  'quick_save_chat': ''
};

// Загрузка/сохранение
function loadHotkeys() {
  return { ...defaultHotkeys, ...JSON.parse(localStorage.getItem(HOTKEYS_STORAGE) || '{}') };
}

function saveHotkeys(hotkeys) {
  localStorage.setItem(HOTKEYS_STORAGE, JSON.stringify(hotkeys));
}

// Обработчик клавиатуры
function initHotkeyListener() {
  document.addEventListener('keydown', (e) => {
    const hotkeys = loadHotkeys();
    
    // Проверяем совпадение
    for (const [action, keyCombo] of Object.entries(hotkeys)) {
      if (!keyCombo) continue;
      
      if (matchesKeyCombo(e, keyCombo)) {
        e.preventDefault();
        executeAction(action);
        break;
      }
    }
  });
}

// UI: Настройки → Хоткеи
// Поле для ��аписи клавиши при нажатии
// Кнопка "Сбросить все" — возвращает дефолт (пусто)
```

### Пример Назначения

```javascript
// Пользователь назначает:
// Ctrl+1 → nav_home
// Ctrl+2 → nav_chat  
// Ctrl+H → command_help

{
  'nav_home': 'ctrl+1',
  'nav_chat': 'ctrl+2',
  'command_help': 'ctrl+h'
}
```

---

## 3. Логирование (Переделка)

**Проблема:** Текущие логи некорректны, не отражают реальную работу приложения.

### Новая Система Логирования

**Принципы:**
1. **Структурированные логи** — JSON, не текст
2. **Полный контекст** — каждый лог имеет trace_id, session_id, user_action
3. **Корреляция** — связываем все события одного запроса
4. **Уровни детализации** — DEBUG / INFO / WARN / ERROR
5. **Метрики** — время выполнения, количество токенов, ошибки

### Формат Логов

```json
{
  "timestamp": "2024-11-26T14:30:45.123Z",
  "level": "info",
  "trace_id": "abc-123-def",
  "session_id": "sess-456",
  "module": "mcp_manager",
  "event": "mcp_server_connected",
  "message": "Подключён MCP-сервер: rag",
  "data": {
    "server_id": "rag",
    "type": "stdio",
    "connection_time_ms": 1250
  },
  "user_action": "mcp_connect",
  "correlation_id": "corr-789"
}
```

### Методы Логирования

**Файл: backend/logging_structured.py**

```python
import json
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

class StructuredLogger:
    def __init__(self, module: str):
        self.module = module
        self.trace_id = str(uuid.uuid4())
        
    def _log(self, level: str, event: str, message: str, 
             data: Optional[Dict] = None, user_action: Optional[str] = None):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "trace_id": self.trace_id,
            "module": self.module,
            "event": event,
            "message": message,
            "data": data or {},
            "user_action": user_action
        }
        
        # Запись в файл + консоль
        self._write_log(log_entry)
        
    def info(self, event: str, message: str, **kwargs):
        self._log("info", event, message, **kwargs)
    
    def warn(self, event: str, message: str, **kwargs):
        self._log("warn", event, message, **kwargs)
    
    def error(self, event: str, message: str, **kwargs):
        self._log("error", event, message, **kwargs)
    
    def debug(self, event: str, message: str, **kwargs):
        if os.environ.get("AMT_DEBUG") == "1":
            self._log("debug", event, message, **kwargs)

# Пример использования
logger = StructuredLogger("mcp_manager")
logger.info("mcp_server_connected", "Подключён MCP-сервер: rag",
            server_id="rag", type="stdio")
```

### Ключевые События для Логирования

**API Layer:**
```python
# До запроса
logger.info("api_request_start", "Получен запрос", 
            endpoint="/chat", method="POST", 
            payload_size=len(request_body))

# После обработки
logger.info("api_request_complete", "Запрос обработан",
            duration_ms=duration, status=200, tokens_used=523)
```

**MCP Layer:**
```python
# Подключение сервера
logger.info("mcp_server_connected", "Подключён MCP-сервер",
            server_id="rag", type="stdio", connection_time_ms=1250)

# Вызов инструмента
logger.info("mcp_tool_call", "Вызов инструмента",
            server_id="rag", tool_name="search_documents",
            args={"query": "test", "limit": 5}, duration_ms=450)

# Ошибка инструмента
logger.error("mcp_tool_error", "Ошибка инструмента",
            server_id="writer", tool_name="create_office",
            error_message="File too large", error_code=500)
```

**AI Engine:**
```python
# Перед вызовом модели
logger.info("ai_call_start", "Вызов модели",
            model="gpt-4", temperature=0.7, 
            context_tokens=1200, system_prompt_len=350)

# После получения ответа
logger.info("ai_call_complete", "Модель ответила",
            model="gpt-4", duration_ms=2340, 
            response_tokens=456, cost=0.0023)

# Ошибка
logger.error("ai_call_error", "Ошибка модели",
            model="gpt-4", error_code=429, 
            error_message="Rate limit exceeded")
```

**Orchestrator:**
```python
# Сжатие контекста
logger.info("orchestrator_context_compress", "Сжатие контекста",
            original_tokens=8000, compressed_tokens=2500, 
            ratio=0.31, strategy="summary")

# Дрейф роли
logger.warn("orchestrator_role_drift", "Обнаружен дрейф роли",
            original_role="helpful_assistant", 
            detected_role="coding_agent", confidence=0.72)
```

### Хранение Логов

**Файл: backend/logs/amt_events.jsonl**

- JSON Lines формат (по одной строке на событие)
- Ротация: 7 дней, 100МБ макс
- Структура:
  ```
  logs/
    amt_events-2024-11-26.jsonl
    amt_events-2024-11-25.jsonl
    .rotation_state.json  # текущий файл, размер, последняя дата
  ```

---

## 4. Dashboard

**Цель:** Визуализация логов в реальном времени.

### UI: Страница "Логи"

**Колонки:**
- Время (timestamp)
- Уровень (DEBUG/INFO/WARN/ERROR) — цветная метка
- Модуль (mcp_manager, ai_engine, orchestrator)
- Событие (event name)
- Сообщение (message)
- Длительность (duration_ms, если есть)
- Данные (expandable JSON)

**Фильтры:**
- По уровню (checkbox: DEBUG, INFO, WARN, ERROR)
- По модулю (dropdown: all, mcp, ai, orchestrator, api)
- По времени (последние 1ч / 24ч / 7дн)
- Поиск по тексту

**Виджеты (верхняя панель):**
- Всего событий за 24ч
- Ошибок за 24ч
- Среднее время запроса
- Активных MCP-серверов
- Запросов в час (график)

### Данные для Dashboard

**API Endpoint:**
```
GET /api/logs?from=2024-11-26T00:00:00Z&to=2024-11-26T23:59:59Z
            &level=info,error&module=mcp_manager&limit=100
```

**Ответ:**
```json
{
  "events": [
    {
      "timestamp": "2024-11-26T14:30:45.123Z",
      "level": "info",
      "module": "mcp_manager",
      "event": "mcp_server_connected",
      "message": "Подключён MCP-сервер: rag",
      "data": {
        "server_id": "rag",
        "type": "stdio",
        "connection_time_ms": 1250
      }
    }
  ],
  "summary": {
    "total_events": 1523,
    "errors": 42,
    "avg_response_time_ms": 1250,
    "active_mcp_servers": 3
  }
}
```

---

## 5. Выбор Генерации (Базовая Модель vs MCP)

**Проблема:** Когда пользователь просит "сгенерируй файл", нужно дать выбор:
- Базовая модель (медленнее, но без ограничений)
- MCP Writer (быстрее, валидация, но требует подключения)

### Логика

```python
# backend/generation_choice.py

async def show_generation_choice(file_type: str) -> dict:
    # Определяем, какие MCP-серверы доступны
    available_writers = [
        s for s in mcp_manager.list_servers()
        if s.id in ['writer', 'media'] and s.enabled
    ]
    
    if not available_writers:
        # Только базовая модель
        return {"mode": "base_model"}
    
    # Если есть MCP-writer — показываем выбор
    if file_type in ('xlsx', 'docx', 'pptx', 'pdf'):
        choice = await show_user_choice([
            "Базовая модель (медленнее, но без ограничений)",
            "MCP Writer (быстрее, валидация)"
        ])
        
        if choice == "MCP Writer":
            return {"mode": "mcp", "server": "writer"}
        else:
            return {"mode": "base_model"}
    
    elif file_type in ('image', 'video', 'audio'):
        choice = await show_user_choice([
            "Базовая модель (генерация через API)",
            "MCP Media (локальная генерация)"
        ])
        
        if choice == "MCP Media":
            return {"mode": "mcp", "server": "media"}
        else:
            return {"mode": "base_model"}
```

### UI: Модалка Выбора

```javascript
// frontend/js/components/filegenChoice.js

function showFileGenerationChoice(fileType) {
  const modal = document.getElementById('filegenChoiceModal');
  
  const options = fileType === 'code' ? [
    {
      title: "Базовая модель",
      description: "Генерация через API, без ограничений по формату",
      value: "base"
    },
    {
      title: "MCP Writer",
      description: "Быстрее, валидация, локальная генерация",
      value: "mcp_writer",
      enabled: mcp_manager.isAvailable('writer')
    }
  ] : [
    {
      title: "Базовая модель",
      description: "Генерация через API",
      value: "base"
    },
    {
      title: "MCP Media",
      description: "Локальная генерация медиа",
      value: "mcp_media",
      enabled: mcp_manager.isAvailable('media')
    }
  ];
  
  modal.innerHTML = `
    <h3>Как сгенерировать файл?</h3>
    <div class="choice-list">
      ${options.map(opt => `
        <button data-choice="${opt.value}" ${!opt.enabled ? 'disabled' : ''}>
          <strong>${opt.title}</strong>
          <div class="description">${opt.description}</div>
        </button>
      `).join('')}
    </div>
  `;
  
  modal.classList.add('active');
}
```

---

## 6. Команда /gen (Генерация)

**Синтаксис:**

### Базовая генерация (по промпту):
```
/gen photo <промпт>           — генерация фото по описанию
/gen image <промпт>          — генерация картинки по описанию
/gen video <промпт>         — генерация видео по описанию
/gen audio <текст>          — генерация аудио (TTS)
```

### Генерация по примеру (image-to-image / video-to-video):
```
/gen photo <файл.изображение> <промпт>          — доработка/трансформация фото
/gen image <файл.изображение> <промпт>          — изменение картинки по образцу
/gen video <файл.видео> <промпт>               — доработка видео по образцу
```

**Примеры:**
```
/gen photo sunset.jpg "сделай ночь"
/gen image logo.png "добавь градиент и тень"
/gen video clip.mp4 "замедли в 2 раза и добавь фильтр"
```

### Комбинированная генерация (несколько типов разом):
```
/gen combo photo:закат,video:волны,audio:рассказ       — генерация фото + видео + аудио
/gen combo image:картинка,pdf:документ                  — генерация картинки и PDF
```

### Генерация файлов:
```
/gen file <формат> <описание>
```

**Поддерживаемые форматы:**
```
/gen file xlsx "таблица продаж за квартал с диаграммой"
/gen file docx "отчёт о проекте с оглавлением"
/gen file pptx "преентаци�� на 10 слайдов про ИИ"
/gen file pdf "руководство пользователя"
/gen file csv "данные о продажах"
/gen file json "структура базы данных"
/gen file yaml "конфигурация приложения"
/gen file py "скрипт для парсинга сайта"
/gen file js "модуль для обработки файлов"
/gen file ts "типизированный модуль"
/gen file html "лендинг с адаптивной версткой"
/gen file css "стили для тёмной темы"
/gen file sh "bash-скрипт для бэкапа"
/gen file bat "Windows-скрипт для запуска"
/gen file md "документация по API"
/gen file txt "простой текстовый файл"
```

### Примеры использования:
```
/gen photo красивый закат над океаном
/gen video кот играет с мячиком 5 секунд
/gen audio расскажи мне анекдот
/gen photo sunset.jpg "сделай ночной вариант"
/gen combo photo:закат,video:волны,audio:рассказ
/gen file xlsx таблица продаж за квартал с диаграммой
/gen file pptx презентация на 10 слайдов про ИИ
/gen file py скрипт для парсинга сайтов с retry
```

### Логика обработки:

```python
# backend/command_engine.py

def handle_gen_command(args, context):
    gen_type = args.get('type', 'image')
    filetype = args.get('filetype', '')
    reference_file = args.get('reference')  # для image-to-image
    
    # === БАЗОВАЯ ГЕНЕРАЦИЯ ===
    if gen_type in ('photo', 'image'):
        context.enable_mcp.add('media')
        context.set_tool('generate_image')
        context.prompt_hint = "Генерируй картинку по описанию"
        
        # Если есть референс-файл — image-to-image
        if reference_file:
            context.prompt_hint += f" (по образцу: {reference_file})"
            context.set_tool('generate_image_from_reference')
            
    elif gen_type == 'video':
        context.enable_mcp.add('media')
        context.set_tool('generate_video')
        context.prompt_hint = "Генерируй видео по описанию (5-10 секунд)"
        
        if reference_file:
            context.prompt_hint += f" (по образцу: {reference_file})"
            context.set_tool('generate_video_from_reference')
            
    elif gen_type == 'audio':
        context.enable_mcp.add('media')
        context.set_tool('generate_audio')
        context.prompt_hint = "Генерируй голосовое сообщение (TTS)"
        
    # === КОМБИНИРОВАННАЯ ГЕНЕРАЦИЯ ===
    elif gen_type == 'combo':
        # args.get('items') = ["photo:закат", "video:волны", "audio:рассказ"]
        for item in args.get('items', []):
            item_type, item_prompt = item.split(':', 1)
            # Активируем все нужные MCP-серверы
            if item_type in ('photo', 'image'):
                context.enable_mcp.add('media')
                context.set_tool('generate_image')
            elif item_type == 'video':
                context.enable_mcp.add('media')
                context.set_tool('generate_video')
            elif item_type == 'audio':
                context.enable_mcp.add('media')
                context.set_tool('generate_audio')
            elif item_type in ('pdf', 'docx', 'xlsx'):
                context.enable_mcp.add('writer')
                context.set_tool(f'create_{item_type}')
                
        context.prompt_hint = "Генерируй несколько типов контента разом"
        
    # === ГЕНЕРАЦИЯ ФАЙЛОВ ===
    elif gen_type == 'file':
        context.enable_mcp.add('writer')
        
        # Определяем инструмент по формату
        tool_map = {
            'xlsx': 'create_office',
            'docx': 'create_office',
            'pptx': 'create_office',
            'pdf': 'create_pdf',
            'csv': 'create_data',
            'json': 'create_data',
            'yaml': 'create_data',
            'py': 'create_code',
            'js': 'create_code',
            'ts': 'create_code',
            'html': 'create_code',
            'css': 'create_code',
            'sh': 'create_code',
            'bat': 'create_code',
            'md': 'create_text',
            'txt': 'create_text'
        }
        
        tool_name = tool_map.get(filetype, 'create_text')
        context.set_tool(tool_name)
        context.prompt_hint = f"Сгенерируй файл формата {filetype}"
        
        # Для презентаций — специальный промпт
        if filetype == 'pptx':
            context.prompt_hint += " (слайды, заголовки, контент)"
            
        # Для Python/JS/TS — генерация кода
        if filetype in ('py', 'js', 'ts'):
            context.prompt_hint += " (рабочий код с комментариями)"
            
        # Для HTML/CSS — фронтенд
        if filetype in ('html', 'css'):
            context.prompt_hint += " (адаптивная верстка, валидный код)"
    
    # Если MCP не подключён — фолбэк на базовую модель
    if not context.mcp_available():
        context.use_base_model = True
        context.prompt_hint += " (через базовую модель, без MCP)"
```

### UI-помощь:
- Когда пользователь вводит `/gen`, autocomplete показывает под-типы
- После выбора типа — подсказка для аргумента
- Для `/gen photo` — поле для выбора референс-файла (опционально)
- Для `/gen combo` — мультиселектор типов + отдельные промпты
- Для `/gen file` — dropdown с форматами
- Если MCP не подключён — автоматический фолбэк + уведомление

---

## 7. Интеграция с MCP

**При выполнении команды, которая включает MCP-сервер:**

```python
# backend/command_engine.py

async def execute_command_request(request, active_commands):
    # 1. Определяем, какие MCP-серверы нужно включить
    mcp_servers_to_enable = set()
    for cmd in active_commands:
        if cmd.effects.enable_mcp:
            mcp_servers_to_enable.update(cmd.effects.enable_mcp)
    
    # 2. Регистрируем тулы этих MCP-серверов
    for server_id in mcp_servers_to_enable:
        await mcp_manager.ensure_connected(server_id)
        # Тулы автоматически регистрируются в tool_registry
    
    # 3. Строим контекст выполнения
    context = CommandContext(
        system_prompt_fragments=[cmd.effects.system_prompt_fragment for cmd in active_commands],
        enabled_tools=[...],
        enabled_agents=[...],
        mcp_servers=mcp_servers_to_enable
    )
    
    # 4. Выполняем запрос через call_ai_api с этим контекстом
    result = await call_ai_api(
        user_message,
        history,
        settings,
        context=context
    )
    
    # 5. После выполнения — выбрасываем контекст
    # (следующий запрос снова чистый)
    return result
```

---

## 8. Файлы для Создания

### Backend:
1. **backend/command_engine.py** — парс��нг и выполнение команд
2. **backend/command_registry.json** — реестр команд
3. **backend/logging_structured.py** — структурированное логирование
4. **backend/logs/** — папка для логов
5. **backend/api/logs.py** — endpoint для dashboard

### Frontend:
1. **frontend/js/core/commands.js** — парсинг и выполнение команд
2. **frontend/js/core/hotkeys.js** — система хоткеев
3. **frontend/js/components/helpOverlay.js** — overlay со списком команд
4. **frontend/js/components/filegenChoice.js** — модалка выбора генерации
5. **frontend/js/pages/logsDashboard.js** — dashboard логов

### Конфигурация:
1. **frontend/js/config/hotkeys.json** — дефолтные хоткеи (пусто)
2. **backend/config/logging.json** — уровни логирования по модулям

---

## 9. Порядок Реализации

### Фаза 1: Основа (3 дня)
1. Структурированное логирование (backend/logging_structured.py)
2. Реестр команд (backend/command_registry.json)
3. Парсер команд (backend/command_engine.py)
4. UI: help overlay (frontend/js/components/helpOverlay.js)

### Фаза 2: Быстрые Команды (2 дня)
1. Навигационные команды (frontend/js/core/commands.js)
2. Быстрые действия
3. Autocomplete для команд
4. Интеграция с композером

### Фаза 3: Хоткеи (1 день)
1. Система хоткеев (frontend/js/core/hotkeys.js)
2. UI: Настройки → Хоткеи
3. Запись/сохранение комбинаций

### Фаза 4: Dashboard (3 дня)
1. API endpoint для логов (backend/api/logs.py)
2. UI: страница "Логи" (frontend/js/pages/logsDashboard.js)
3. Фильтры и виджеты
4. Реальное время (polling или WebSocket)

### Фаза 5: Генерация (2 дня)
1. Команда /gen (backend/command_engine.py)
2. Модалка выбора генерации (frontend/js/components/filegenChoice.js)
3. Интеграция с MCP
4. Фолбэк на базовую модель

### Итого: ~11 дней

---

## Приложения

### А. Примеры Логов

```json
{"timestamp":"2024-11-26T14:30:45.123Z","level":"info","trace_id":"abc-123","module":"api","event":"request_start","message":"Получен запрос","data":{"endpoint":"/chat","method":"POST"},"user_action":"chat_send"}

{"timestamp":"2024-11-26T14:30:45.456Z","level":"info","trace_id":"abc-123","module":"mcp_manager","event":"server_connect","message":"Подключение к MCP-серверу","data":{"server_id":"rag","type":"stdio"}}

{"timestamp":"2024-11-26T14:30:46.700Z","level":"info","trace_id":"abc-123","module":"ai_engine","event":"model_call","message":"Вызов модели","data":{"model":"gpt-4","temperature":0.7,"context_tokens":1200}}

{"timestamp":"2024-11-26T14:30:48.050Z","level":"info","trace_id":"abc-123","module":"ai_engine","event":"model_response","message":"Ответ получен","data":{"model":"gpt-4","duration_ms":2340,"response_tokens":456}}

{"timestamp":"2024-11-26T14:30:48.051Z","level":"info","trace_id":"abc-123","module":"api","event":"request_complete","message":"Запрос обработан","data":{"duration_ms":2928,"status":200}}
```

### Б. Список Событий для ��огирования

**API Layer:**
- request_start
- request_complete
- request_error

**MCP Layer:**
- server_connect
- server_disconnect
- server_error
- tool_call
- tool_complete
- tool_error

**AI Engine:**
- model_call_start
- model_call_complete
- model_call_error
- context_compress
- tool_execute

**Orchestrator:**
- context_check
- role_drift_detected
- auto_save
- monitor_snapshot

**User Actions:**
- chat_send
- chat_save
- chat_export
- settings_change
- file_upload
- command_execute
