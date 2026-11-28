# BRAND — AMT Chat

## Design tokens

### Палитра (5 colors)

Цвета взяты из `frontend/themes.json` (default theme: `ocean`).

| Название | HEX | RGB | Использование |
|----------|-----|-----|---------------|
| `bg-primary` | `#05050a` | `5, 5, 10` | Фон (основной) |
| `bg-secondary` | `#11131a` | `17, 19, 26` | Фон (векторы) |
| `accent` | `#8b86c9` | `139, 134, 201` | Акцент (кнопки, ссылки, highlight) |
| `text` | `#d0d0d0` | `208, 208, 208` | Основной текст |
| `text-dim` | `#8a8a9a` | `138, 138, 154` | Вспомогательный текст |

### Шрифт

- **Font:** system (без веб-шрифта, без loading)
- **Heading font:** system
- **Scale:** 1.0

### Форма (Shape)

- **Radius:** 18px (cards, buttons, inputs)
- **Radius SM:** 10px (small elements)

### Эффекты

- **Blur:** 18px (glassmorphism)
- **Glow:** 0.35 (subtle)
- **Shadow:** md

## Motif (визуальный мотив)

**Terminal prompt + cursor mark.**
- Пунктирная линия (cursor blink)
- Промпт `>` (открытый, незавершённый)
- Векторная сетка (coordinated points)

## Композиция

**Calm / Technical.**
- Много whitespace
- Минимум анимации (subtle fade, no bounce)
- Grid-based layout
- Monospace для code blocks

## Применение

- **README hero:** `bg-primary` + `accent` для title, `text-dim` для подзаголовка
- **Section headers:** `bg-secondary` + `accent` для icon
- **Code blocks:** `bg-primary` + `text` + `mono` font
- **Buttons:** `accent` background, `text` color (white on dark, black on light)
- **Links:** `accent` color, underline on hover

## Примечания

- **Не использовать:** yellow grid template, decorative borders, heavy shadows
- **Избегать:** stock imagery, generic icons, promotional text
- **Предпочитать:** real screenshots, project-native diagrams, code fragments
