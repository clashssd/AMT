# DESIGN_UPDATE.md — Phase Tracking

Branch: `design/system-v2` (created)

| Phase | Title | Status | Commit |
|-------|-------|--------|--------|
| 0 | Baseline + white-plaque audit | ✅ | `docs(design): baseline screenshots and white plaque audit` |
| 1 | Tokens + theme schema v2 | ✅ | `feat(design): add design tokens and theme schema v2` |
| 2 | Full theme editor | ✅ | `feat(design): add full theme editor with field and surface controls` |
| 3 | Fields + white plaques (critical) | ✅ | `37894f2` |
| 4 | Unified button system | ✅ | `92ba36d` |
| 5 | Cards, modals, nav, feedback | ✅ | `feat(design): refresh cards, forms, modals and feedback` |
| 6 | Tokenization + guard script | ✅ | `afb5ee2` |
| 7 | Motion + bento home | ✅ | `e01a28d` |
| 8 | A11y + responsive | ✅ | `340fa20` |
| 9 | Final QA | ✅ | `32c7743` |
| 10 | Report | ✅ | — |

## Notes / decisions log
- Фаза 3: глобальный field-base в components-v2.css (input/textarea/select/checkbox/range/file/color, autofill-fix, select option dark bg, accent-color). Точечные white-plaque-фиксы: .send-btn/.web-open-btn/.player-tab; style.css tokenized .modal-glass select/input, .test-btn.primary, .opt-select, .search-input-wrap, .form-group, .chat-input, .web-open-btn.
- Фаза 4: unified `.btn` system (base + variants + sizes + states + loading spinner + button-in-button trailing icon). Composer ➤/⏹ → SVG. .stop-btn → danger-soft. Старые классы = алиасы над базовым слоем (без ручной переработки 131 кнопок).
- Фаза 5: карточки (`.home-card`/`.settings-glass`/`.storage-glass`/`.stat-card`) → `--card-bg`/`--card-bg-2`/`--border`. Модальные: `--modal-bg`/`--overlay-bg`/`--theme-radius` + max-height 86dvh/760px + overflow auto + blur-lg. main.js: `initModalA11y` (role=dialog/aria-modal/focus trap/Escape/focus return, MutationObserver на .hidden) + toast aria-live. components-v2: скроллбары, aria-invalid, чипы/бейджи/тумблеры, empty/error/skeleton, double-bezel inset-highlight.
- Фаза 6: bulk-tokenize style.css via `scripts/phase6-tokenize.mjs` (hex map + rgba channel-signature rules + catch-all for white/black). 146 changes, 218→135 literals. Guard `scripts/check-design-tokens.mjs` skips `:root`/`[data-theme]` token-definition blocks when counting, flags undefined var() refs, >120 literals, white bg outside accent-contrast. components-v2.css: 3 residual literals fixed (glass-border/glass-bg). package.json: `check:design` script.
- Фаза 7: motion-v2.css (body.no-anim kill-switch, prefers-reduced-motion, .reveal scroll-reveal, bento home grid 1.6fr/1fr at >=1024). main.js: initScrollReveal IntersectionObserver (threshold 0.15, stagger 60ms, cleanup on pagehide). style.css: 3 transition:all → specific property transitions + var(--ease-out).
- Фаза 8: components-v2.css: :focus-visible ring on all interactive, touch targets ≥38px, body overflow-x:hidden, .sr-only + skip-link, table a11y, @media print override. home.html: skip-link `<a href="#homePage">` + tabindex=-1 on main. check:design guard: skip @media print in white-bg check.
- style.css brace diff -2 = pre-existing (проверено git stash в фазе 3), не из наших правок.
