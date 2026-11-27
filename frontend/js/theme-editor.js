/* ============================================================================
   AMT Chat — THEME EDITOR (v2)
   Полный редактор тем. Подключается ПОСЛЕ themes.js (нужен window.AMTThemes)
   и theme-schema.js (window.AMTThemeSchema). Чистый vanilla, без DOM-сидения.
   ==========================================================================*/
(function () {
    "use strict";

    const S = () => window.AMTThemeSchema;
    const T = () => window.AMTThemes;

    // Все контролы (обязательные id из плана)
    const IDS = [
        "teAccent", "teAccent2", "teBg1", "teBg2", "teBg3", "teText", "teTextDim",
        "teGlass", "teBorder", "teSuccess", "teWarning", "teDanger", "teInfo",
        "teRadius", "teBlur", "teGlow", "teShadow", "teMotion", "teFont", "teHeadingFont", "teScale",
        "teFieldBg", "teFieldBorder", "teFieldText", "teFieldPlaceholder",
        "teCardBg", "teCardBg2", "teModalBg", "teOverlay", "teDropdownBg", "teTooltipBg",
        "teCodeBg", "teTableBg", "teTableHover", "teScrollbarThumb", "teScrollbarTrack",
        "teControlBg", "teControlBorder", "teControlChecked",
    ];
    const RANGE_VALS = { teGlass: "teGlassVal", teBorder: "teBorderVal", teOverlay: "teOverlayVal", teRadius: "teRadiusVal", teBlur: "teBlurVal", teGlow: "teGlowVal", teScale: "teScaleVal" };

    let draft = null;   // черновик v2-темы
    let selectedId = null; // id выбранной темы
    let isCustom = false; // выбранная — кастомная?
    let previewTimer = null;

    function $(id) { return document.getElementById(id); }
    function readColor(id) { const el = $(id); return el ? el.value : ""; }

    // Собрать текущий черновик из контролов
    function buildDraft() {
        const base = T().current ? T().current() : {};
        const cur = selectedId ? ({ ...loadAllThemes() }[selectedId]) : null;
        const theme = S().normalizeTheme(cur, selectedId || "ocean");
        const c = theme.colors, s = theme.surfaces, sh = theme.shape, ef = theme.effects, ty = theme.typography, mo = theme.motion;

        // Цвета (быстрые)
        c.bg = [readColor("teBg1") || c.bg[0], readColor("teBg2") || c.bg[1], readColor("teBg3") || c.bg[2]];
        c.accent = readColor("teAccent") || c.accent;
        c.accent2 = readColor("teAccent2") || c.accent2;
        c.text = readColor("teText") || c.text;
        c.textDim = readColor("teTextDim") || c.textDim;
        c.glass = `rgba(255,255,255,${(+readColor("teGlass") || 2) / 100})`;
        c.glass2 = `rgba(255,255,255,${Math.max(0, (+readColor("teGlass") || 2) - 1) / 100})`;
        c.border = `rgba(255,255,255,${(+readColor("teBorder") || 6) / 100})`;
        c.success = readColor("teSuccess") || c.success;
        c.warning = readColor("teWarning") || c.warning;
        c.danger = readColor("teDanger") || c.danger;
        c.info = readColor("teInfo") || c.info;

        // Поля (color-контролы дают hex → ставим как есть, если не трогали)
        const setSurface = (key, colorId) => { const v = readColor(colorId); if (v) s[key] = v; };
        setSurface("fieldBg", "teFieldBg"); setSurface("fieldBorder", "teFieldBorder");
        setSurface("fieldText", "teFieldText"); setSurface("fieldPlaceholder", "teFieldPlaceholder");
        setSurface("cardBg", "teCardBg"); setSurface("cardBg2", "teCardBg2");
        setSurface("modalBg", "teModalBg");
        s.overlayBg = `rgba(0,0,0,${(+readColor("teOverlay") || 62) / 100})`;
        setSurface("dropdownBg", "teDropdownBg"); setSurface("tooltipBg", "teTooltipBg");
        setSurface("codeBg", "teCodeBg"); setSurface("tableBg", "teTableBg");
        setSurface("tableRowHover", "teTableHover");
        setSurface("scrollbarThumb", "teScrollbarThumb"); setSurface("scrollbarTrack", "teScrollbarTrack");
        setSurface("controlBg", "teControlBg"); setSurface("controlBorder", "teControlBorder");
        setSurface("controlChecked", "teControlChecked");

        // Форма/эффекты
        sh.radius = +readColor("teRadius") || sh.radius;
        ef.blur = +readColor("teBlur") || ef.blur;
        ef.glow = (+readColor("teGlow") || 35) / 100;
        ef.shadow = $("teShadow").value || ef.shadow;
        mo.speed = $("teMotion").value || mo.speed;
        ty.font = $("teFont").value || ty.font;
        ty.headingFont = $("teHeadingFont").value || ty.headingFont;
        ty.scale = (+readColor("teScale") || 100) / 100;

        theme.version = 2;
        theme.id = selectedId || ("custom_" + Date.now().toString(36));
        theme.label = $("teName").value.trim() || theme.label || selectedId || "Кастомная";
        draft = theme;
        return theme;
    }

    function loadAllThemes() {
        // themes (встроенные) + customThemes (кастомные) — берём из themes.js публичного API
        // Т.к. window.AMTThemes.current() даёт только текущее, для полного списка
        // читаем напрямую (дублируем логику init). Для надёжности — через localStorage.
        let builtin = {};
        try { builtin = JSON.parse(JSON.stringify(window.__AMT_BUILTIN_THEMES__ || {})); } catch {}
        let custom = {};
        try { custom = JSON.parse(localStorage.getItem("amt_custom_themes_v2") || "{}"); } catch {}
        return { ...builtin, ...custom };
    }

    // Показать контролы значениями выбранной темы
    function loadToControls(theme, id) {
        selectedId = id;
        isCustom = !window.__AMT_BUILTIN_IDS__ || !window.__AMT_BUILTIN_IDS__.includes(id);
        const t = S().normalizeTheme(theme, id);
        S().deriveSurfaces(t);
        const c = t.colors, s = t.surfaces, sh = t.shape, ef = t.effects, ty = t.typography, mo = t.motion;

        const set = (id2, v) => { const el = $(id2); if (el) el.value = v; };
        const hexFromRgba = (rgba) => {
            const m = /rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/.exec(rgba || "");
            if (!m) return "";
            const toHex = n => Math.round(n).toString(16).padStart(2, "0");
            return "#" + toHex(+m[1]) + toHex(+m[2]) + toHex(+m[3]);
        };
        const alphaPct = (rgba) => {
            const m = /rgba?\([^)]*[,/]\s*([\d.]+)\s*\)/.exec(rgba || "");
            return m ? Math.round(parseFloat(m[1]) * 100) : 0;
        };

        set("teBg1", c.bg[0]); set("teBg2", c.bg[1]); set("teBg3", c.bg[2] || c.bg[1]);
        set("teAccent", c.accent); set("teAccent2", c.accent2);
        set("teText", c.text); set("teTextDim", c.textDim);
        set("teGlass", alphaPct(c.glass)); set("teGlassVal").textContent = alphaPct(c.glass) + "%";
        set("teBorder", alphaPct(c.border)); set("teBorderVal").textContent = alphaPct(c.border) + "%";
        set("teSuccess", c.success || ""); set("teWarning", c.warning || ""); set("teDanger", c.danger || ""); set("teInfo", c.info || "");
        set("teFieldBg", hexFromRgba(s.fieldBg)); set("teFieldBorder", hexFromRgba(s.fieldBorder));
        set("teFieldText", hexFromRgba(s.fieldText)); set("teFieldPlaceholder", hexFromRgba(s.fieldPlaceholder));
        set("teCardBg", hexFromRgba(s.cardBg)); set("teCardBg2", hexFromRgba(s.cardBg2));
        set("teModalBg", hexFromRgba(s.modalBg));
        set("teOverlay", alphaPct(s.overlayBg)); set("teOverlayVal").textContent = alphaPct(s.overlayBg) + "%";
        set("teDropdownBg", hexFromRgba(s.dropdownBg)); set("teTooltipBg", hexFromRgba(s.tooltipBg));
        set("teCodeBg", hexFromRgba(s.codeBg)); set("teTableBg", hexFromRgba(s.tableBg));
        set("teTableHover", hexFromRgba(s.tableRowHover));
        set("teScrollbarThumb", hexFromRgba(s.scrollbarThumb)); set("teScrollbarTrack", hexFromRgba(s.scrollbarTrack));
        set("teControlBg", hexFromRgba(s.controlBg)); set("teControlBorder", hexFromRgba(s.controlBorder)); set("teControlChecked", hexFromRgba(s.controlChecked));
        set("teRadius", sh.radius); set("teRadiusVal").textContent = sh.radius + "px";
        set("teBlur", ef.blur); set("teBlurVal").textContent = ef.blur + "px";
        set("teGlow", Math.round(ef.glow * 100)); set("teGlowVal").textContent = Math.round(ef.glow * 100) + "%";
        set("teShadow", ef.shadow); set("teMotion", mo.speed);
        set("teFont", ty.font); set("teHeadingFont", ty.headingFont || ty.font);
        set("teScale", Math.round(ty.scale * 100)); set("teScaleVal").textContent = Math.round(ty.scale * 100) + "%";
        set("teName", t.label || id);

        updateContrast();
    }

    function updateContrast() {
        const t = buildDraft();
        const el = $("teContrast");
        const w = $("teWarning");
        if (el) {
            const ratios = S().contrastFor(t);
            const fmt = r => r != null ? r.toFixed(2) + ":1" : "—";
            el.textContent = `Контраст — текст/фон: ${fmt(ratios.textOnBg)} · акцент/фон: ${fmt(ratios.accentOnBg)}`;
        }
        if (w) {
            const ratios = S().contrastFor(t);
            const msgs = [];
            if (ratios.textOnBg != null && ratios.textOnBg < 4.5) msgs.push("Контраст текста ниже 4.5:1");
            if (ratios.accentOnBg != null && ratios.accentOnBg < 3) msgs.push("Контраст акцента ниже 3:1");
            if (msgs.length) { w.hidden = false; w.textContent = "⚠ " + msgs.join(" · "); }
            else w.hidden = true;
        }
    }

    // Живой предпросмотр (debounce 80ms)
    function schedulePreview() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(() => {
            const t = buildDraft();
            if (T().applyTheme) T().applyTheme("__preview__"); // noop-safe
            const vars = S().toCssVars(t);
            const r = document.documentElement.style;
            for (const k in vars) r.setProperty(k, vars[k]);
            updateContrast();
        }, 80);
    }

    // Сохранить как новую кастомную
    function saveNew() {
        const t = buildDraft();
        const name = $("teName").value.trim() || ("Тема " + new Date().toLocaleDateString());
        const id = "custom_" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 24);
        const all = loadAllThemes();
        t.id = id; t.label = name;
        all[id] = t;
        localStorage.setItem("amt_custom_themes_v2", JSON.stringify(all));
        window.__AMT_CUSTOM_IDS__ = Object.keys(all).filter(k => k.startsWith("custom_"));
        selectedId = id; isCustom = true;
        loadToControls(t, id);
        applyAndPersist();
    }

    // Обновить текущую (только кастомную)
    function updateCurrent() {
        if (!isCustom) { alert("Встроенную тему нельзя перезаписать. Нажмите «Сохранить как новую» или «Дублировать»."); return; }
        const t = buildDraft();
        t.id = selectedId;
        const all = loadAllThemes();
        all[selectedId] = t;
        localStorage.setItem("amt_custom_themes_v2", JSON.stringify(all));
        applyAndPersist();
    }

    function duplicate() {
        const t = buildDraft();
        const name = (t.label || selectedId || "Тема") + " (копия)";
        const id = "custom_" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/\s+/g, "-").slice(0, 28);
        const all = loadAllThemes();
        t.id = id; t.label = name;
        all[id] = t;
        localStorage.setItem("amt_custom_themes_v2", JSON.stringify(all));
        window.__AMT_CUSTOM_IDS__ = Object.keys(all).filter(k => k.startsWith("custom_"));
        selectedId = id; isCustom = true;
        loadToControls(t, id);
        applyAndPersist();
    }

    function removeTheme() {
        if (!isCustom) { alert("Встроенную тему удалить нельзя."); return; }
        if (!confirm(`Удалить кастомную тему «${selectedId}»?`)) return;
        const all = loadAllThemes();
        delete all[selectedId];
        localStorage.setItem("amt_custom_themes_v2", JSON.stringify(all));
        window.__AMT_CUSTOM_IDS__ = Object.keys(all).filter(k => k.startsWith("custom_"));
        // переключаемся на ocean
        selectedId = "ocean"; isCustom = false;
        const ocean = S().DEFAULT_THEME;
        loadToControls(ocean, "ocean");
        applyAndPersist();
    }

    function exportTheme() {
        const t = buildDraft();
        const blob = new Blob([JSON.stringify(t, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "amt-theme-" + (t.label || t.id).toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".json";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    }

    function importTheme() {
        const f = $("teImportFile");
        if (!f) return;
        f.click();
        f.onchange = () => {
            const file = f.files[0];
            if (!file) return;
            const r = new FileReader();
            r.onload = () => {
                try {
                    const raw = JSON.parse(r.result);
                    const t = S().normalizeTheme(raw, raw.id || "imported");
                    const name = t.label || "Импортированная";
                    const id = "custom_" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 24);
                    const all = loadAllThemes();
                    t.id = id;
                    all[id] = t;
                    localStorage.setItem("amt_custom_themes_v2", JSON.stringify(all));
                    window.__AMT_CUSTOM_IDS__ = Object.keys(all).filter(k => k.startsWith("custom_"));
                    selectedId = id; isCustom = true;
                    loadToControls(t, id);
                    applyAndPersist();
                } catch (e) { alert("Неверный JSON темы: " + e.message); }
            };
            r.readAsText(file);
        };
    }

    function resetTheme() {
        // вернуть значения выбранной темы
        if (!selectedId) return;
        const all = loadAllThemes();
        const t = all[selectedId];
        if (!t) { loadToControls(S().DEFAULT_THEME, "ocean"); return; }
        loadToControls(t, selectedId);
        applyAndPersist();
    }

    function applyAndPersist() {
        const t = buildDraft();
        if (T().applyTheme) T().applyTheme(selectedId || "ocean");
        // применить черновик как текущий (для предпросмотра)
        const vars = S().toCssVars(t);
        const r = document.documentElement.style;
        for (const k in vars) r.setProperty(k, vars[k]);
        if (T().persist) T().persist();
    }

    // События
    function init() {
        if (!$("teAccent")) return;

        // Заполнить селекты шрифтов (teFont, teHeadingFont) из AMTThemes.fonts
        const fonts = (T() && T().fonts) ? T().fonts : [];
        ["teFont", "teHeadingFont"].forEach(fid => {
            const sel = $(fid);
            if (!sel) return;
            sel.innerHTML = "";
            for (const f of fonts) {
                const opt = document.createElement("option");
                opt.value = f.id;
                opt.textContent = f.label;
                sel.appendChild(opt);
            }
        });

        // range/select/color/text → живой предпросмотр
        IDS.forEach(id => {
            const el = $(id);
            if (!el) return;
            const ev = el.type === "range" ? "input" : (el.tagName === "SELECT" ? "change" : "input");
            el.addEventListener(ev, schedulePreview);
        });
        // value-labels
        Object.entries(RANGE_VALS).forEach(([inp, out]) => {
            const el = $(inp), o = $(out);
            if (el && o) el.addEventListener("input", () => { o.textContent = el.value + (inp === "teScale" ? "%" : (inp === "teRadius" || inp === "teBlur" ? "px" : "%")); });
        });

        $("teSaveNew").onclick = saveNew;
        $("teUpdate").onclick = updateCurrent;
        $("teDuplicate").onclick = duplicate;
        $("teDelete").onclick = removeTheme;
        $("teExport").onclick = exportTheme;
        $("teImport").onclick = importTheme;
        $("teReset").onclick = resetTheme;

        // При выборе темы в селекторе themePick — подхватываем её в редактор
        const tp = $("themePick");
        if (tp) tp.addEventListener("change", () => {
            const all = loadAllThemes();
            const t = all[tp.value] || S().DEFAULT_THEME;
            loadToControls(t, tp.value);
        });

        // Начальное состояние: текущая тема
        const cur = T().current ? T().current() : { theme: "ocean" };
        const all = loadAllThemes();
        const t = all[cur.theme] || all["ocean"] || S().DEFAULT_THEME;
        loadToControls(t, cur.theme || "ocean");
    }

    if (document.readyState !== "loading") init();
    else document.addEventListener("DOMContentLoaded", init);
})();
