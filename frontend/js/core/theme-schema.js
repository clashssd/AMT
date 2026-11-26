/* ============================================================================
   AMT Chat — THEME SCHEMA v2
   Единая схема темы, normalize (v1 плоский → v2 вложенный), генерация CSS-vars,
   контрастность, производные поверхности. Подключается ДО i18n.js и themes.js.
   Не имеет DOM-зависимостей — чистые функции + глобальный namespace window.AMTThemeSchema.
   ==========================================================================*/
(function () {
    "use strict";

    // ---------- Утилиты цвета ----------
    function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

    // hex #rgb/#rrggbb → [r,g,b] 0..255
    function hexToRgb(hex) {
        if (typeof hex !== "string") return null;
        let h = hex.trim().replace(/^#/, "");
        if (h.length === 3) h = h.split("").map(c => c + c).join("");
        if (h.length !== 6) return null;
        const n = parseInt(h, 16);
        if (Number.isNaN(n)) return null;
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }

    // rgb/rgba(...) → [r,g,b]
    function parseRgb(str) {
        const m = /rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(str || "");
        if (!m) return null;
        return [clamp(+m[1], 0, 255), clamp(+m[2], 0, 255), clamp(+m[3], 0, 255)];
    }

    // Любой CSS-цвет (hex, rgb, rgba, named) → {r,g,b,a} | null
    function parseColor(c) {
        if (c == null || c === "") return null;
        const s = String(c).trim();
        if (s === "transparent") return { r: 0, g: 0, b: 0, a: 0 };
        let rgb = hexToRgb(s) || parseRgb(s);
        if (!rgb) {
            // named colors / fallback через canvas-лику (не используем): просто null
            return null;
        }
        let a = 1;
        const am = /,\s*([0-9.]+)\s*\)/.exec(s);
        if (am) a = clamp(parseFloat(am[1]), 0, 1);
        return { r: rgb[0], g: rgb[1], b: rgb[2], a };
    }

    // Relative luminance (WCAG 2.x)
    function luminance(c) {
        const { r, g, b } = c;
        const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    }

    // Контраст 1..21
    function contrastRatio(a, b) {
        const ca = parseColor(a), cb = parseColor(b);
        if (!ca || !cb) return null;
        const l1 = luminance(ca), l2 = luminance(cb);
        const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
        return (hi + 0.05) / (lo + 0.05);
    }

    function isReadable(fg, bg, min) {
        const r = contrastRatio(fg, bg);
        return r != null && r >= (min || 4.5);
    }

    // Смесить цвет c на процент p в сторону white (для surface-производных).
    // Возвращает rgba-строку (для CSS). Используется как fallback, если браузер
    // не понимает color-mix (Electron/Chromium понимает, но на всякий случай).
    function mixWithWhite(c, pct) {
        const col = parseColor(c);
        if (!col) return c;
        const mix = (v) => Math.round(v + (255 - v) * (pct / 100));
        return `rgba(${mix(col.r)}, ${mix(col.g)}, ${mix(col.b)}, 1)`;
    }

    // ---------- Дефолтная тема v2 ----------
    const DEFAULT_THEME = {
        version: 2,
        label: "Океан (дефолт)",
        id: "ocean",
        appearance: "dark",
        colors: {
            bg: ["#05050a", "#11131a", "#0b0f14"],
            glass: "rgba(255,255,255,0.02)",
            glass2: "rgba(255,255,255,0.03)",
            border: "rgba(255,255,255,0.06)",
            accent: "#8b86c9",
            accent2: "#aba5c9",
            text: "#d0d0d0",
            textDim: "#8a8a9a",
            success: "#4ade80",
            warning: "#facc15",
            danger: "#f87171",
            info: "#8ab4ff",
        },
        surfaces: {
            // Пустые = выводятся из colors через deriveTheme / color-mix
            fieldBg: "", fieldBgHover: "", fieldBorder: "", fieldBorderFocus: "",
            fieldText: "", fieldPlaceholder: "",
            cardBg: "", cardBg2: "", modalBg: "", overlayBg: "",
            dropdownBg: "", tooltipBg: "", codeBg: "", tableBg: "", tableRowHover: "",
            scrollbarThumb: "", scrollbarTrack: "",
            controlBg: "", controlBorder: "", controlChecked: "",
        },
        status: { success: "", warning: "", danger: "", info: "" },
        shape: { radius: 18, radiusSm: 10, radiusPill: 999 },
        effects: { blur: 18, glow: 0.35, shadow: "md" },
        typography: { font: "system", headingFont: "system", scale: 1 },
        motion: { speed: "normal" },
    };

    // ---------- v1 (плоский) → v2 (вложенный) ----------
    function normalizeTheme(raw, id) {
        if (!raw || typeof raw !== "object") {
            return Object.assign({}, DEFAULT_THEME, { id: id || "custom" });
        }
        // Уже v2?
        if (raw.version === 2 && raw.colors && raw.surfaces) {
            const out = structuredClone(DEFAULT_THEME);
            out.id = raw.id || id || out.id;
            out.label = raw.label || out.label;
            out.appearance = raw.appearance || "dark";
            out.colors = Object.assign(out.colors, raw.colors);
            out.surfaces = Object.assign(out.surfaces, raw.surfaces);
            out.status = Object.assign(out.status, raw.status || {});
            out.shape = Object.assign(out.shape, raw.shape || {});
            out.effects = Object.assign(out.effects, raw.effects || {});
            out.typography = Object.assign(out.typography, raw.typography || {});
            out.motion = Object.assign(out.motion, raw.motion || {});
            return out;
        }
        // v1 плоский: bg[], glass, glass2, border, accent, accent2, text, textDim, font
        const out = structuredClone(DEFAULT_THEME);
        out.id = raw.id || id || "custom";
        out.label = raw.label || id || "Кастомная";
        out.appearance = raw.appearance || "dark";
        if (Array.isArray(raw.bg) && raw.bg.length) {
            out.colors.bg = [raw.bg[0], raw.bg[1], raw.bg[2] || raw.bg[1] || raw.bg[0]];
        }
        if (raw.glass != null) out.colors.glass = raw.glass;
        if (raw.glass2 != null) out.colors.glass2 = raw.glass2;
        if (raw.border != null) out.colors.border = raw.border;
        if (raw.accent != null) out.colors.accent = raw.accent;
        if (raw.accent2 != null) out.colors.accent2 = raw.accent2;
        if (raw.text != null) out.colors.text = raw.text;
        if (raw.textDim != null) out.colors.textDim = raw.textDim;
        if (raw.success != null) out.colors.success = raw.success;
        if (raw.warning != null) out.colors.warning = raw.warning;
        if (raw.danger != null) out.colors.danger = raw.danger;
        if (raw.info != null) out.colors.info = raw.info;
        if (raw.font) out.typography.font = raw.font;
        if (raw.radius != null) out.shape.radius = raw.radius;
        // surfaces остаются пустыми → выводятся из colors
        return out;
    }

    // ---------- Производные поверхности (если не заданы явно) ----------
    function deriveSurfaces(theme) {
        const c = theme.colors;
        const s = theme.surfaces;
        const bg1 = c.bg && c.bg[0] ? c.bg[0] : "#05050a";
        const bg2 = c.bg && c.bg[1] ? c.bg[1] : bg1;
        const bg3 = c.bg && c.bg[2] ? c.bg[2] : bg2;
        const text = c.text || "#d0d0d0";
        const textDim = c.textDim || "#8a8a9a";
        const accent = c.accent || "#8b86c9";

        // Если поле пустое — выводим из базового через mixWithWhite (fallback).
        // В браузере CSS color-mix сядет точнее, но для предпросмотра/контраста
        // нужен JS-эквивалент.
        s.fieldBg = s.fieldBg || mixWithWhite(bg2, 0.06);
        s.fieldBgHover = s.fieldBgHover || mixWithWhite(bg3, 0.08);
        s.fieldBorder = s.fieldBorder || c.border;
        s.fieldBorderFocus = s.fieldBorderFocus || accent;
        s.fieldText = s.fieldText || text;
        s.fieldPlaceholder = s.fieldPlaceholder || mixWithWhite(textDim, 0.3);
        s.cardBg = s.cardBg || mixWithWhite(bg2, 0.04);
        s.cardBg2 = s.cardBg2 || mixWithWhite(bg3, 0.06);
        s.modalBg = s.modalBg || mixWithWhite(bg2, 0.04);
        s.overlayBg = s.overlayBg || "rgba(0,0,0,0.62)";
        s.dropdownBg = s.dropdownBg || mixWithWhite(bg3, 0.06);
        s.tooltipBg = s.tooltipBg || mixWithWhite(bg3, 0.10);
        s.codeBg = s.codeBg || mixWithWhite(bg1, 0.04);
        s.tableBg = s.tableBg || mixWithWhite(bg2, 0.04);
        s.tableRowHover = s.tableRowHover || mixWithWhite(text, 0.08);
        s.scrollbarThumb = s.scrollbarThumb || mixWithWhite(text, 0.22);
        s.scrollbarTrack = s.scrollbarTrack || "transparent";
        s.controlBg = s.controlBg || mixWithWhite(bg2, 0.06);
        s.controlBorder = s.controlBorder || c.border;
        s.controlChecked = s.controlChecked || accent;
        return s;
    }

    // ---------- toCssVars: 60+ переменных ----------
    function toCssVars(theme) {
        const t = normalizeTheme(theme);
        deriveSurfaces(t);
        const c = t.colors;
        const s = t.surfaces;
        const st = t.status;
        const sh = t.shape;
        const ef = t.effects;
        const ty = t.typography;
        const mo = t.motion;

        const bg1 = c.bg[0], bg2 = c.bg[1], bg3 = c.bg[2];
        const vars = {};
        // Фон
        vars["--bg-grad-1"] = bg1;
        vars["--bg-grad-2"] = bg2;
        vars["--bg-grad-3"] = bg3;
        // Стекло
        vars["--glass-bg"] = c.glass || "rgba(255,255,255,0.02)";
        vars["--glass-bg-2"] = c.glass2 || "rgba(255,255,255,0.03)";
        vars["--glass-border"] = c.border || "rgba(255,255,255,0.06)";
        vars["--glass"] = vars["--glass-bg"];
        // Акценты
        vars["--accent"] = c.accent;
        vars["--accent-2"] = c.accent2;
        // Текст
        vars["--text"] = c.text;
        vars["--text-dim"] = c.textDim;
        // Статусы (если не заданы в status — берём из colors)
        vars["--success"] = st.success || c.success;
        vars["--warning"] = st.warning || c.warning;
        vars["--danger"] = st.danger || c.danger;
        vars["--info"] = st.info || c.info;
        // Поля
        vars["--field-bg"] = s.fieldBg;
        vars["--field-bg-hover"] = s.fieldBgHover;
        vars["--field-border"] = s.fieldBorder;
        vars["--field-border-focus"] = s.fieldBorderFocus;
        vars["--field-text"] = s.fieldText;
        vars["--field-placeholder"] = s.fieldPlaceholder;
        // Поверхности
        vars["--card-bg"] = s.cardBg;
        vars["--card-bg-2"] = s.cardBg2;
        vars["--modal-bg"] = s.modalBg;
        vars["--overlay-bg"] = s.overlayBg;
        vars["--dropdown-bg"] = s.dropdownBg;
        vars["--tooltip-bg"] = s.tooltipBg;
        vars["--code-bg"] = s.codeBg;
        vars["--table-bg"] = s.tableBg;
        vars["--table-row-hover"] = s.tableRowHover;
        vars["--scrollbar-thumb"] = s.scrollbarThumb;
        vars["--scrollbar-track"] = s.scrollbarTrack;
        vars["--control-bg"] = s.controlBg;
        vars["--control-border"] = s.controlBorder;
        vars["--control-checked"] = s.controlChecked;
        vars["--surface-dim"] = s.cardBg;
        // Форма
        vars["--theme-radius"] = sh.radius + "px";
        vars["--radius-lg"] = sh.radius + "px";
        vars["--radius-sm"] = sh.radiusSm + "px";
        vars["--radius-pill"] = sh.radiusPill + "px";
        // Эффекты
        vars["--theme-blur"] = ef.blur + "px";
        vars["--theme-glow"] = ef.glow;
        vars["--shadow-md"] = ef.shadow === "sm"
            ? "0 1px 2px rgba(0,0,0,0.24)"
            : ef.shadow === "lg"
                ? "0 24px 64px rgba(0,0,0,0.36)"
                : "0 8px 24px rgba(0,0,0,0.28)";
        // Типографика
        vars["--font-scale"] = ty.scale;
        vars["--motion-speed"] = mo.speed;
        // Custom font families (set by theme editor; takes precedence over global font pick)
        if (ty.font === "custom" && ty.fontFamily) {
            vars["--font-family"] = ty.fontFamily;
        }
        if ((ty.headingFont === "custom") && ty.headingFontFamily) {
            vars["--heading-font-family"] = ty.headingFontFamily;
        }
        // appearance
        vars["--appearance"] = t.appearance;
        return vars;
    }

    // ---------- Публичное API ----------
    const API = {
        DEFAULT_THEME,
        normalizeTheme,
        deriveSurfaces,
        toCssVars,
        contrastRatio,
        isReadable,
        parseColor,
        hexToRgb,
        // Быстрые проверки для редактора
        contrastFor(theme) {
            const t = normalizeTheme(theme);
            deriveSurfaces(t);
            const c = t.colors;
            return {
                textOnBg: contrastRatio(c.text, c.bg[1] || c.bg[0]),
                accentOnBg: contrastRatio(c.accent, c.bg[1] || c.bg[0]),
                accentContrast: contrastRatio(c["accent-contrast"] || "#ffffff", c.accent),
            };
        },
    };

    window.AMTThemeSchema = API;
})();
