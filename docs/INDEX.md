# Documentation index — AMT Chat

Все документы проекта, отсортированные по назначению. Каждая ссылка ведёт к
файлу в этом каталоге (`docs/`).

---

## По порядку важности

| Документ | Когда читать |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Что изменилось в каждой версии (1.0.0 → 1.1.3) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Как устроено приложение: компоненты, процессы, дерево |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Как собрать, протестировать, внести изменения |
| [BUILD.md](BUILD.md) | Детальная сборка дистрибутива (PyInstaller, NSIS, подписывание) |
| [SETUP.md](SETUP.md) | Установка зависимостей и окружения |
| [EXTENSIONS.md](EXTENSIONS.md) | Система расширений: `manifest.json`, `init(ctx)`, хук-функции |
| [SECURITY.md](SECURITY.md) | Модель безопасности: шифрование, белые списки, аудит |
| [COMMANDS_SYSTEM_DETAILED.md](COMMANDS_SYSTEM_DETAILED.md) | Slash-команды: архитектура, реестр, парсер, потоки |
| [AMT_Chat_1.0.1_release_report.md](AMT_Chat_1.0.1_release_report.md) | Отчёт о релизе 1.0.1 (исторический) |

---

## Где что искать

- **Пользователю** (быстрый старт, установка):
  - [README.md](../README.md) — главное описание, возможности, установка.
  - [SETUP.md](SETUP.md) — если что-то не ставится.
- **Разработчику** (изменение кода, сборка, тестирование):
  - [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, версионирование, правила.
  - [BUILD.md](BUILD.md) — пайплайн сборки.
  - [ARCHITECTURE.md](ARCHITECTURE.md) — как всё связано.
- **Расширяющему** (дописывание приложения без перекомпиляции):
  - [EXTENSIONS.md](EXTENSIONS.md) — API для расширений.
- **Обеспокоенному безопасностью**:
  - [SECURITY.md](SECURITY.md) — что шифруется, что логируется, границы.
- **Изучающему slash-команды**:
  - [COMMANDS_SYSTEM_DETAILED.md](COMMANDS_SYSTEM_DETAILED.md) — реестр,
    парсер, как добавить свою команду.

---

## Подкаталоги

- `docs/design/` — спецификации дизайна (токены, визуальные решения).
- `docs/superpowers/` — рабочие документы по процессам разработки.
