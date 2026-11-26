# AMT Chat — Аудит «белых плашек» и baseline (Фаза 0)

Дата: 2026-11-26 · Ветка: `design/system-v2` · База: commit `ee20c1d`

## 1. Среда / стек

- Electron 45, vanilla HTML/CSS/JS, без React/Tailwind/сборки.
- `home.html` — 157 КБ, 131 кнопка, 61 `.test-btn`, 123 input, 25 select, 36 inline style.
- `style.css` — 168 КБ. Темы задаются `[data-theme]` на `<html>` (9 тем) + CSS-переменные.
- Темы живут в `frontend/themes.json` (плоский формат v1), редактируются `frontend/js/themes.js`.
- Кастомные темы: `localStorage.amt_custom_themes` (JSON-объект).

## 2. «Белые плашки» — что реально найдено

### 2.1 Белый фон (критично)

| Файл:строка | Что | Вердикт |
|---|---|---|
| `style.css:1211` | `background: #fff;` (внутри `.docs-pre` / light code-block) | **Белая плашка** — заменить на `var(--code-bg)` |
| `style.css:4304-4307` | `.player-tab` `color: rgba(255,255,255,0.55)` | не фон, ок, но токенизировать (`--text-faint`) |
| `style.css:4398` | `background: #7c5cff;` (обновление-кнопка) | захардкоженный цвет, не `--accent` |

### 2.2 Белый/чёрный текст (67 вхождений `#fff`, 1 `#000`)

- `color: #fff` — по всей `style.css` (90, 157, 220, 225, 252, 299, 306, 462, 640, 653, 667, 784, 844, 888, 955, 1039, 1130, 1184, 1293, 1295, 1357, 1417, 1459, 1820, 1821, 1849, 1926, 1989, 2010, 2012, 2073, 2177, 2313, 2417, 2529, 2550, 2649, 2733, 2739, 2799, 2866, 2938, 2987, 3031, 3130, 3134, 3219, 3236, 3251, 3252, 3305, 3601, 3763, 3815, 3962, 3975, 4196, 4197, 4369, 4398, 4536, 4558, 4649, 4662, 4815).
- Все они — текст поверх тёмного/акцентного фона → заменить на `var(--accent-contrast)` / `var(--text-strong)`.
- `style.css:1212` `color: #000` — текст на белом блоке `.docs-pre` → вместе с фоном токенизируется.

### 2.3 Нативные контролы, которые не темизированы (причина белых плашек)

- `input/select/textarea` — нет глобального `background` в тёмной теме; нативный белый фон на Windows.
- `select` �� без `color-scheme: dark` → белый нативный попап.
- `input:-webkit-autofill` — не обработан → светло-жёлтый/белый.
- `input[type=checkbox/radio/range/file/color]` — без `accent-color` / `color-scheme`.
- `select option` — без явного тёмного фона.

### 2.4 Inline-стили в `home.html` (36 штук)

- В основном `margin-top / display / width / flex / grid-template` — **не цвета**, белых плашек не дают.
- Единственный цветовой inline: `home.html:796` `font-family:monospace` — не цвет.
- Вывод: inline-стили не источник белых плашек; трогать только если появится цвет.

### 2.5 `main.js`

- Шаблонных `background: #fff/#ffffff/white` в `main.js` **не найдено** (grep).
- Белых плашек из шаблонов main.js нет — источник именно в `style.css` и нативных контролах.

### 2.6 Вспышка белого при загрузке

- `html` явного `background` не имеет; `body` цвет из `var(--text)`, фон идёт через `.bg-media` (fixed, z-index -3).
- Риск вспышки минимален, но `html` стоит задать `background: var(--bg-grad-1)` + `color-scheme: dark` в tokens.css (Фаза 1/3).

## 3. Список элементов, которые выглядят как белые плашки

1. `input, select, textarea` — все 123 + 25 (нативный белый фон).
2. `select option` попап.
3. autofill в полях логина/пароля/ключей API.
4. `checkbox / radio / range / file / color`.
5. `.docs-pre` (код-блок со `#fff` фоном).
6. Вспышка `html` при загрузке.

## 4. План устранения (ссылки на фазы)

- Токены полей/поверхностей → Фаза 1 (`tokens.css`).
- Глобальные стили полей + нативные контролы + autofill + `color-scheme: dark` → Фаза 3.
- Замена `#fff` в `style.css` на токены → Фаза 6.
- Карточки/модалки/тосты/тултипы на токенах → Фаза 5.

## 5. Baseline-скриншоты

Скриншоты в headless Electron не делаются автоматически (нет playwright/puppeteer в проекте, добавлять зависимости запрещено).
Среда: `C:\Users\berds\Desktop\AMT\docs\design\baseline\` — запис��н этот аудит вместо скриншотов.
Человеку: при `npm start` визуальный baseline = текущая `main` (commit ee20c1d).
