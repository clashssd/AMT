# Расширения AMT Chat

Расширение — папка в `extensions/`, описанная `manifest.json`. Никакого
build-шага: фронтенд и бэкенд грузятся как обычные файлы.

## Структура расширения
```
extensions/имя-расширения/
  manifest.json      # обязательно
  backend.py         # опционально (Python)
  index.js           # опционально (frontend)
```

## manifest.json
```json
{
  "name": "example",
  "version": "1.0.0",
  "description": "Пример расширения",
  "frontend": true,
  "backend": true
}
```
- `name` — уникальный идентификатор (латиница, без пробелов).
- `frontend: true` — нужно ли грузить `index.js` в браузере.
- `backend: true` — нужно ли запускать `backend.py` в Python.

## backend.py (Python)
Вызывается `init(ctx)` при старте бэкенда. `ctx`:
- `ctx['tools']` — экземпляр `ToolSandbox` (можно регистрировать свои инструменты).
- `ctx['extensions_dir']` — путь к `extensions/`.

```python
def init(ctx):
    # например, добавить свой инструмент
    tools = ctx['tools']
    # tools.register_custom_tool('my_tool', my_handler)  # если метод есть
```
Исключения в `init` не роняют приложение: логгер пишет ошибку, расширение
пропускается, остальные грузятся.

## index.js (frontend)
Вызывается `init(ctx)`. `ctx`:
- `ctx.api.fetch(path, opts)` — запрос к бэкенду.
- `ctx.ui.registerPage(id, label, mainId, html)` — добавить страницу в навигацию.
- `ctx.project`, `ctx.tools` — доступ к текущему контексту.

```js
function init(ctx) {
  ctx.ui.registerPage(
    'my_ext',
    'Моё расшир.',
    'my-ext-page',
    `<h3>Привет</h3><button id="myBtn">Клик</button>`
  );
  document.getElementById('myBtn').onclick = () => {
    ctx.api.fetch('/api/extensions/list').then(r => r.json())
      .then(d => alert('Расширений: ' + d.extensions.length));
  };
}
```
`registerPage` создаёт `<main id="{mainId}">` и пункт в сайдбаре; клик переключает
страницу через существующий `showPage(mainId)`.

## Как проверить
1. Создайте папку и файлы.
2. Перезапустите приложение (в dev: перезапуск бэкенда; desktop: перезапуск).
3. `GET /api/extensions/list` покажет расширение; в сайдбаре появится пункт.

## Безопасность
- Python-разделы и JS грузятся из вашей же `extensions/` — доверяйте только
  расширениям, которые добавляли сами.
- Исolation: каждое расширение грузится в try/except; ошибка одного не влияет
  на другие.
- ИИ-инструменты, зарегистрированные расширением, подчиняются тем же правилам
  (разрешённые каталоги, авто-подтверждение, логирование).

## Управление в приложении

Управлять расширениями можно прямо в AMT Chat, без перезапуска:

1. Откройте **«Справка» → «Расширения»** (новая вкладка в навигации).
2. Список показывает все расширения из `extensions/` со статусом и флагами (frontend/backend).
3. Переключатель «вкл» — включает/выключает расширение. Выключенные не грузятся во фронтенд. Состояние сохраняется в `extensions_state.json`.
4. Кнопка **«+ Добавить расширение»** — подсказывает, куда положить папку.
5. Кнопка **«↻ Обновить список»** — перечитывает каталог `extensions/` (подхватывает новые папки без рестарта бэкенда).

Энпоинты управления:
- `GET /api/extensions/list` — список (с флагом `enabled`)
- `POST /api/extensions/{name}/toggle` — вкл/выкл (`{"enabled": true|false}`)
- `GET /api/extensions/state` — текущее состояние вкл/выкл
- `POST /api/extensions/reload` — перечитать каталог (подхватить новые папки)
