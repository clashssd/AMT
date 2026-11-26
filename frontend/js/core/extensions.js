/**
 * Frontend extension loader.
 *
 * Загружает список расширений с бэкенда, для каждого с `frontend: true`
 * подтягивает index.js через /api/extensions/{name}/index.js и вызывает
 * его init(ctx). ctx предоставляет UI-примитивы (registerPage) и доступ
 * к бэкенду (api.fetch).
 *
 * Без рамок, без сборки — просто <script src="js/extensions.js"> и вызов
 * AMTExtensions.init() после DOMContentLoaded.
 */
(function () {
    'use strict';

    const API_BASE = window.location.origin;

    /** @type {Array<{id:string,name:string,page:HTMLElement|null}>} */
    const registered = [];

    /**
     * Реестр навигации: находит nav-ссылки в сайдбаре.
     * @returns {HTMLElement|null}
     */
    function findSidebarNav() {
        return document.querySelector('.sidebar nav') || document.querySelector('nav');
    }

    /**
     * Регистрирует новую страницу и добавляет ссылку в навигацию.
     * @param {string} id — ключ страницы (id элемента <main>)
     * @param {string} label — текст в сайдбаре
     * @param {string} mainId — id <main> блока
     * @param {string} html — содержимое
     * @returns {HTMLElement}
     */
    function registerPage(id, label, mainId, html) {
        // создать <main> страницу
        const main = document.createElement('main');
        main.id = mainId;
        main.className = 'page hidden';
        main.innerHTML = html;
        document.body.appendChild(main);

        // добавить ссылку в сайдбар
        const nav = findSidebarNav();
        let link = null;
        if (nav) {
            link = document.createElement('a');
            link.href = '#';
            link.className = 'nav-ext-link';
            link.dataset.page = mainId;
            link.dataset.i18n = 'ext_' + id;
            link.dataset.i18nRu = label;
            link.textContent = label;
            link.addEventListener('click', (e) => {
                e.preventDefault();
                // переключить страницу через существующий showPage
                if (typeof showPage === 'function') showPage(mainId);
                else document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
                main.classList.remove('hidden');
            });
            nav.appendChild(link);
        }

        const entry = { id, name: label, page: main, link };
        registered.push(entry);
        return main;
    }

    /**
     * Удалить зарегистрированные страницы/ссылки (для перерисовки после вкл/выкл).
     */
    function clearAll() {
        for (const entry of registered) {
            if (entry.page && entry.page.parentNode) entry.page.parentNode.removeChild(entry.page);
            if (entry.link && entry.link.parentNode) entry.link.parentNode.removeChild(entry.link);
        }
        registered.length = 0;
    }

    /**
     * Перерисовать расширения: убрать старые, загрузить только включённые.
     * @returns {Promise<Array>} список инициализированных
     */
    async function refresh() {
        clearAll();
        return loadAll();
    }

    /**
     * Загрузить и инициализировать ВСЕ frontend-расширения (включённые по умолчанию).
     * @returns {Promise<Array>} список инициализированных
     */
    async function loadAll() {
        let list = [];
        try {
            const r = await fetch(API_BASE + '/api/extensions/list');
            const d = await r.json();
            // только frontend-расширения, которые ВКЛЮЧЕНЫ
            list = (d.extensions || []).filter(e => e.frontend && e.enabled !== false);
        } catch (e) {
            console.warn('[ext] cannot load list', e);
            return [];
        }

        const done = [];
        for (const ext of list) {
            try {
                const js = await fetch(API_BASE + '/api/extensions/' + encodeURIComponent(ext.name) + '/index.js');
                if (!js.ok) { console.warn('[ext] no index.js for ' + ext.name); continue; }
                const src = await js.text();
                // создаём функцию init из кода
                const fn = new Function(src + '\nreturn init;');
                const initFn = fn();
                if (typeof initFn !== 'function') { console.warn('[ext] ' + ext.name + ' has no init'); continue; }
                const ctx = {
                    api: {
                        fetch: (path, opts) => fetch(API_BASE + path, opts).then(r => r.json()),
                    },
                    ui: { registerPage },
                    project: {},
                    tools: {},
                };
                initFn(ctx);
                done.push(ext.name);
            } catch (e) {
                console.error('[ext] failed to init ' + ext.name, e);
            }
        }
        return done;
    }

    window.AMTExtensions = { loadAll, refresh, clearAll, registerPage, registered };
})();
