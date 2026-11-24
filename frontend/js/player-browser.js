/**
 * player-browser.js — in-player YouTube/Twitch browser.
 * Called from main.js when the media overlay opens with type="search" or type="channel".
 * Exposes: window.initSearchTab, window.initChannelTab
 *
 * Search supports three result kinds (sent to /api/web/search):
 *   - "video" → only YouTube video cards (embeddable)
 *   - "web"   → regular browser results, rendered as link cards that open in the
 *                default browser (most sites deny iframing via X-Frame-Options)
 *   - "auto"  → mixed: embeddable video cards + web link cards
 */
(function () {
    const API_BASE = window.API_BASE || '';

    // ===================== Shared helpers =====================

    function openInBrowser(url) {
        if (!url) return;
        // Open in frameless Electron window (in-player browser, bypasses X-Frame-Options)
        if (window.api && window.api.openBrowserWindow) {
            window.api.openBrowserWindow(url).catch(() => {
                if (window.api && window.api.openExternal) window.api.openExternal(url).catch(() => {});
                else { try { window.open(url, '_blank', 'noopener'); } catch (_) {} }
            });
        } else if (window.api && window.api.openExternal) {
            window.api.openExternal(url).catch(() => {
                try { window.open(url, '_blank', 'noopener'); } catch (_) {}
            });
        } else {
            try { window.open(url, '_blank', 'noopener'); } catch (_) {}
        }
    }

    function makeVideoCard(vid) {
        const card = document.createElement('div');
        card.className = 'sidebar-video-card' + (vid.live ? ' live' : '');
        const thumb = document.createElement('img');
        thumb.className = 'thumb';
        thumb.src = vid.thumb || '';
        thumb.alt = '';
        thumb.addEventListener('error', () => {
            // Favicon fallback when thumbnail is missing/blocked
            if (vid.favicon) {
                const fav = document.createElement('img');
                fav.className = 'thumb';
                fav.src = vid.favicon;
                fav.alt = '';
                thumb.replaceWith(fav);
            } else {
                thumb.style.background = 'linear-gradient(135deg,#1a1630,#0c0a18)';
                thumb.textContent = '';
                const glyph = document.createElement('span');
                glyph.style.cssText = 'position:absolute;font-size:26px;opacity:0.4';
                glyph.textContent = vid.platform === 'twitch' ? '🔴' : '▶';
                thumb.style.position = 'relative';
                thumb.appendChild(glyph);
            }
        });
        if (vid.live) {
            const badge = document.createElement('span');
            badge.className = 'live-badge';
            badge.textContent = 'LIVE';
            thumb.style.position = 'relative';
            thumb.appendChild(badge);
        }
        const info = document.createElement('div');
        info.className = 'info';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = vid.title || vid.id;
        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = [vid.duration, vid.viewers ? vid.viewers + ' зрителей' : null,
            vid.platform && vid.platform !== 'youtube' && vid.platform !== 'twitch' ? '🌐 ' + vid.platform : null
        ].filter(Boolean).join(' · ');
        info.appendChild(title);
        if (meta.textContent) info.appendChild(meta);
        card.appendChild(thumb);
        card.appendChild(info);
        card.dataset.vid = vid.id || '';
        card.dataset.url = vid.url || '';
        card.dataset.live = vid.live ? '1' : '';
        card.dataset.platform = vid.platform || '';
        return card;
    }

    function extractYtId(url) {
        if (!url) return '';
        const m = String(url).match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/);
        return m ? m[1] : '';
    }

    // Web result → link card with "Открыть в браузере" button.
    function makeWebLinkCard(item) {
        const card = document.createElement('div');
        card.className = 'sidebar-video-card web-link';
        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = item.title || item.url || 'Ссылка';
        card.appendChild(title);
        const meta = document.createElement('div');
        meta.className = 'meta';
        const host = (item.host) || (item.url ? (function () { try { return new URL(item.url).hostname.replace(/^www\./, ''); } catch (_) { return ''; } })() : '');
        meta.textContent = host ? ('🌐 ' + host + ' — откроется в плеере') : 'Откроется в плеере';
        card.appendChild(meta);
        const openBtn = document.createElement('button');
        openBtn.className = 'web-open-btn';
        openBtn.textContent = 'Открыть в плеере';
        openBtn.addEventListener('click', (e) => { e.stopPropagation(); openInBrowser(item.url); });
        card.appendChild(openBtn);
        card.addEventListener('click', () => openInBrowser(item.url));
        card.dataset.url = item.url || '';
        card.dataset.platform = 'web';
        return card;
    }

    function loadVideoIntoMain(mainEl, vid) {
        if (!mainEl) return;
        mainEl.innerHTML = '';

        // Web (не-встраиваемый) результат — показываем в ТЕЛЕ плеера, а не снаружи:
        // iframe-попытка (часть сайтов позволяет, часть блокирует) + превью-карточка
        // с кнопкой «Открыть в браузере» (для заблокированных сайтов).
        // Detect if this is a playable video (YouTube, Twitch, or direct file)
        const isYtUrl2 = /youtube\.com|youtu\.be/.test(vid.url || '');
        const isTwUrl2 = /twitch\.tv/.test(vid.url || '');
        const isDirectVideo = /\.(mp4|webm|mov|m4v|mkv|m3u8)(\?|$)/i.test(vid.url || '') ||
            (vid.streamUrl && /\.(mp4|webm|m3u8)/.test(vid.streamUrl)) ||
            isYtUrl2 || isTwUrl2;
        if (vid.platform === 'web' || (!vid.id && vid.url)) {
            if (isDirectVideo) {
                const vWrap = document.createElement('div');
                vWrap.className = 'stream-filter-wrap';
                vWrap.style.cssText = 'width:100%;height:100%;position:relative;';
                const vLoader = document.createElement('div');
                vLoader.className = 'stream-loading';
                vLoader.textContent = 'Загрузка видео…';
                
                if (isYtUrl2) {
                    // YouTube → iframe embed (like main.js does)
                    const m = (vid.url || '').match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/);
                    if (!m) { // fallback: just embed the URL
                        const fbIfr = document.createElement('iframe');
                        fbIfr.src = vid.url;
                        fbIfr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
                        vWrap.appendChild(fbIfr);
                        vWrap.appendChild(vLoader);
                        mainEl.appendChild(vWrap);
                        return;
                    }
                    const ytIfr = document.createElement('iframe');
                    ytIfr.src = m ? 'https://www.youtube.com/embed/' + m[1] + '?autoplay=1' : (vid.url || '');
                    ytIfr.allow = 'autoplay; fullscreen; picture-in-picture';
                    ytIfr.allowFullscreen = true;
                    ytIfr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
                    ytIfr.addEventListener('load', () => vLoader.remove());
                    vWrap.appendChild(ytIfr);
                    vWrap.appendChild(vLoader);
                } else if (isTwUrl2) {
                    // Twitch → player.twitch.tv embed
                    const twIfr = document.createElement('iframe');
                    const twUrl = vid.url || '';
                    let twEmbed = 'https://player.twitch.tv/?channel=';
                    const chMatch = twUrl.match(/twitch\.tv\/([\w-]+)/);
                    const vidMatch = twUrl.match(/twitch\.tv\/videos\/(\d+)/);
                    if (vidMatch) twEmbed = 'https://player.twitch.tv/?video=' + vidMatch[1] + '&parent=127.0.0.1';
                    else if (chMatch) twEmbed += chMatch[1] + '&parent=127.0.0.1';
                    twIfr.src = twEmbed;
                    twIfr.allow = 'autoplay; fullscreen; picture-in-picture';
                    twIfr.allowFullscreen = true;
                    twIfr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
                    twIfr.addEventListener('load', () => vLoader.remove());
                    vWrap.appendChild(twIfr);
                    vWrap.appendChild(vLoader);
                } else {
                    // Direct video file (mp4/webm/m3u8) → native <video>
                    const v = document.createElement('video');
                    v.src = vid.streamUrl || vid.url;
                    v.controls = false;
                    v.loop = false;
                    v.crossOrigin = 'anonymous';
                    v.style.width = '100%';
                    v.style.height = '100%';
                    v.style.objectFit = 'contain';
                    v.style.background = '#000';
                    v.style.position = 'absolute';
                    v.style.top = '0';
                    v.style.left = '0';
                    v.addEventListener('loadeddata', () => vLoader.remove());
                    v.addEventListener('error', () => {
                        vLoader.textContent = 'Не удалось загрузить видео';
                    });
                    vWrap.appendChild(v);
                    vWrap.appendChild(vLoader);
                }
                mainEl.appendChild(vWrap);
                return;
            }

            // Веб-страница (сайт) — frameless окно внутри приложения
            const wrap = document.createElement('div');
            wrap.style.cssText = 'width:100%;height:100%;position:relative;';
            const loader = document.createElement('div');
            loader.className = 'stream-loading';
            loader.textContent = 'Загрузка страницы…';
            const ifr = document.createElement('iframe');
            ifr.src = vid.url || '';
            ifr.allow = 'autoplay; fullscreen; picture-in-picture';
            ifr.allowFullscreen = true;
            ifr.referrerPolicy = 'no-referrer';
            ifr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
            const open = () => openInBrowser(vid.url);
            let blocked = false;
            const showBlocked = () => {
                if (blocked) return;
                blocked = true;
                const card = document.createElement('div');
                card.className = 'web-link-main';
                card.style.cssText = 'height:100%;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:14px;padding:40px;text-align:center;position:relative;z-index:1;background:var(--panel,rgba(10,10,18,0.95));';
                const t = document.createElement('div');
                t.style.cssText = 'font-size:20px;font-weight:600;color:#e8e6f5;max-width:560px;';
                t.textContent = vid.title || vid.url;
                card.appendChild(t);
                const host = (function () { try { return vid.url ? new URL(vid.url).hostname.replace(/^www\./, '') : ''; } catch (_) { return ''; } })();
                if (host) {
                    const h = document.createElement('div');
                    h.style.cssText = 'color:var(--muted);font-size:13px;';
                    h.textContent = host;
                    card.appendChild(h);
                }
                const note = document.createElement('div');
                note.style.cssText = 'color:var(--muted);font-size:12px;max-width:420px;';
                note.textContent = 'Сайт не позволяет встроить страницу в iframe. Откройте в плеере (отдельное окно):';
                card.appendChild(note);
                const btn = document.createElement('button');
                btn.style.cssText = 'margin-top:8px;padding:10px 22px;border-radius:10px;border:0;background:#7c5cff;color:#fff;font-size:14px;cursor:pointer;';
                btn.textContent = 'Открыть в плеере';
                btn.addEventListener('click', open);
                card.appendChild(btn);
                wrap.appendChild(card);
            };
            // Блокировку iframe не detectar напрямую (iframe не шлёт ошибок) —
            // таймаут: если load не пришёл за 4 сек, показываем fallback-карточку ПОД iframe.
            const t = setTimeout(showBlocked, 4000);
            ifr.addEventListener('load', () => { clearTimeout(t); loader.remove(); });
            // Клик по всей области (если iframe не загрузился) тоже открывает браузер
            wrap.addEventListener('click', (e) => {
                if (e.target === wrap) open();
            });
            wrap.appendChild(ifr);
            wrap.appendChild(loader);
            mainEl.appendChild(wrap);
            // Служебная кнопка сверху — всегда можно открыть во внешнем браузере
            if (window.openMediaOverlay) { /* placeholder */ }
            return;
        }

        const wrap = document.createElement('div');
        wrap.style.cssText = 'width:100%;height:100%;position:relative;';
        const loader = document.createElement('div');
        loader.className = 'stream-loading';
        loader.textContent = 'Загрузка…';
        const ifr = document.createElement('iframe');
        let src;
        if (vid.id && vid.platform !== 'twitch') {
            src = 'https://www.youtube.com/embed/' + vid.id + '?autoplay=1';
        } else if (vid.id && vid.platform === 'twitch') {
            // VOD-ссылка twitch.tv/videos/<id> или id из карточки канала.
            // Для Twitch player: parent = домен, с которого встраивается iframe.
            // В Electron (file://) location.hostname пуст → используем 127.0.0.1
            // (Twitch разрешает localhost/127.0.0.1 как parent для локальных клиентов).
            const m = String(vid.url || '').match(/twitch\.tv\/videos\/([A-Za-z0-9]+)/);
            const vodId = m ? m[1] : vid.id;
            const parent = location.hostname || '127.0.0.1';
            src = 'https://player.twitch.tv/?video=' + vodId + '&parent=' + encodeURIComponent(parent) + '&autoplay=true';
        } else {
            src = vid.url || '';
        }
        ifr.src = src;
        ifr.allow = 'autoplay; fullscreen; picture-in-picture';
        ifr.allowFullscreen = true;
        ifr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
        ifr.addEventListener('load', () => loader.remove());
        setTimeout(() => { if (loader.parentNode) loader.textContent = 'Не удаётся загрузить.'; }, 8000);
        wrap.appendChild(ifr);
        wrap.appendChild(loader);
        mainEl.appendChild(wrap);
    }

    // ===================== Search Tab =====================

    window.initSearchTab = function (sidebarEl, mainEl) {
        if (!sidebarEl) return;
        sidebarEl.innerHTML = '';

        const section = document.createElement('div');
        section.className = 'sidebar-section-title';
        section.textContent = 'Поиск';
        sidebarEl.appendChild(section);

        // Kind toggle: Видео / Веб / Авто
        const kindLabel = document.createElement('div');
        kindLabel.style.cssText = 'color:var(--muted);font-size:12px;margin:4px 0 6px;';
        kindLabel.textContent = 'Где искать:';
        sidebarEl.appendChild(kindLabel);
        const kindToggle = document.createElement('div');
        kindToggle.className = 'platform-toggle';
        const kindOpts = [
            { key: 'auto', label: 'Авто' },
            { key: 'video', label: 'Видео' },
            { key: 'web', label: 'Веб' },
        ];
        let kind = 'auto';
        const kindBtns = {};
        kindOpts.forEach(o => {
            const b = document.createElement('button');
            b.textContent = o.label;
            if (o.key === kind) b.className = 'active';
            b.addEventListener('click', () => {
                kind = o.key;
                Object.values(kindBtns).forEach(x => x.classList.remove('active'));
                b.classList.add('active');
            });
            kindToggle.appendChild(b);
            kindBtns[o.key] = b;
        });
        sidebarEl.appendChild(kindToggle);

        const wrap = document.createElement('div');
        wrap.className = 'search-input-wrap';
        const input = document.createElement('input');
        input.placeholder = 'Видео, канал, сайт…';
        input.type = 'text';
        const btn = document.createElement('button');
        btn.textContent = 'Искать';
        wrap.appendChild(input);
        wrap.appendChild(btn);
        sidebarEl.appendChild(wrap);

        const resultsEl = document.createElement('div');
        resultsEl.style.marginTop = '8px';
        sidebarEl.appendChild(resultsEl);

        async function doSearch() {
            const q = input.value.trim();
            if (!q) return;
            // kind 'video' → youtube, 'web' → web, 'auto' → auto
            const sendKind = kind === 'video' ? 'youtube' : (kind === 'web' ? 'web' : 'auto');
            resultsEl.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:8px;">Поиск…</div>';
            try {
                const res = await fetch(`${API_BASE}/api/web/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: q, kind: sendKind, limit: 10 }),
                });
                const data = await res.json();
                resultsEl.innerHTML = '';
                if (!data.ok || !data.results || !data.results.length) {
                    resultsEl.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:8px;">Ничего не найдено</div>';
                    return;
                }
                data.results.forEach(item => {
                    // item.type: "video" | "channel" | "live" | "web"; item.source: "YouTube" | "DuckDuckGo"
                    const plat = item.platform || (item.type === 'web' ? 'web' : (item.source === 'YouTube' ? 'youtube' : ''));
                    const isWeb = item.type === 'web' || plat === 'web' ||
                        (!item.id && !/youtube\.com|youtu\.be|twitch\.tv/i.test(item.url || ''));
                    if (isWeb) {
                        const card = makeWebLinkCard({ ...item, platform: plat });
                        resultsEl.appendChild(card);
                        return;
                    }
                    const vid = {
                        id: item.id || extractYtId(item.url) || '',
                        title: item.title || item.url || '',
                        thumb: item.thumb || (item.source === 'YouTube' && item.id ? '' : ''),
                        favicon: item.favicon || '',
                        url: item.url || '',
                        platform: (item.source === 'YouTube') ? 'youtube' : plat,
                        live: item.live || item.type === 'live' || false,
                        duration: item.duration || '',
                    };
                    if (vid.platform === 'youtube' && vid.id && !vid.thumb) {
                        vid.thumb = `https://i.ytimg.com/vi/${vid.id}/default.jpg`;
                    }
                    const card = makeVideoCard(vid);
                    card.addEventListener('click', () => {
                        loadVideoIntoMain(mainEl, vid);
                        resultsEl.querySelectorAll('.sidebar-video-card').forEach(c => c.style.outline = '');
                        card.style.outline = '2px solid rgba(124,92,255,0.6)';
                    });
                    resultsEl.appendChild(card);
                });
            } catch (e) {
                resultsEl.innerHTML = '<div style="color:#ef4949;font-size:13px;padding:8px;">Ошибка: ' + e.message + '</div>';
            }
        }

        btn.addEventListener('click', doSearch);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
        input.focus();
    };

    // ===================== Channel Tab =====================

    window.initChannelTab = function (sidebarEl, mainEl) {
        if (!sidebarEl) return;
        sidebarEl.innerHTML = '';

        const section = document.createElement('div');
        section.className = 'sidebar-section-title';
        section.textContent = 'Каналы';
        sidebarEl.appendChild(section);

        // Platform toggle
        const toggle = document.createElement('div');
        toggle.className = 'platform-toggle';
        const ytBtn = document.createElement('button');
        ytBtn.textContent = 'YouTube';
        ytBtn.className = 'active';
        const twBtn = document.createElement('button');
        twBtn.textContent = 'Twitch';
        toggle.appendChild(ytBtn);
        toggle.appendChild(twBtn);
        sidebarEl.appendChild(toggle);

        let platform = 'youtube';
        ytBtn.addEventListener('click', () => { platform = 'youtube'; ytBtn.classList.add('active'); twBtn.classList.remove('active'); });
        twBtn.addEventListener('click', () => { platform = 'twitch'; twBtn.classList.add('active'); ytBtn.classList.remove('active'); });

        // Channel input
        const wrap = document.createElement('div');
        wrap.className = 'search-input-wrap';
        const input = document.createElement('input');
        input.placeholder = 'Имя канала…';
        input.type = 'text';
        const btn = document.createElement('button');
        btn.textContent = 'Открыть';
        wrap.appendChild(input);
        wrap.appendChild(btn);
        sidebarEl.appendChild(wrap);

        const channelInfo = document.createElement('div');
        channelInfo.style.marginTop = '12px';
        sidebarEl.appendChild(channelInfo);

        // Helper: show a fallback "open channel page in browser" card when scraping finds nothing.
        function openChannelInBrowser(name) {
            const url = platform === 'youtube'
                ? 'https://www.youtube.com/@' + encodeURIComponent(name)
                : 'https://www.twitch.tv/' + encodeURIComponent(name);
            openInBrowser(url);
        }

        async function openChannel() {
            const name = input.value.trim();
            if (!name) return;
            channelInfo.innerHTML = '<div style="color:var(--muted);font-size:13px;">Загрузка…</div>';
            try {
                const url = platform === 'youtube'
                    ? `${API_BASE}/api/yt/channel?channel=${encodeURIComponent(name)}`
                    : `${API_BASE}/api/twitch/channel?channel=${encodeURIComponent(name)}`;
                const res = await fetch(url);
                const data = await res.json();
                channelInfo.innerHTML = '';

                if (!data.ok) {
                    channelInfo.innerHTML = '<div style="color:#ef4949;font-size:13px;">' + (data.error || 'Ошибка загрузки') + '</div>';
                    const fb = document.createElement('button');
                    fb.style.cssText = 'margin-top:8px;width:100%;padding:8px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:transparent;color:#e8e6f5;cursor:pointer;font-size:13px;';
                    fb.textContent = 'Открыть канал в плеере →';
                    fb.addEventListener('click', () => openChannelInBrowser(name));
                    channelInfo.appendChild(fb);
                    return;
                }

                // Channel card
                if (data.avatar || data.title) {
                    const cc = document.createElement('div');
                    cc.className = 'channel-card';
                    if (data.avatar) {
                        const img = document.createElement('img');
                        img.className = 'avatar';
                        img.src = data.avatar;
                        cc.appendChild(img);
                    }
                    const nameEl = document.createElement('div');
                    nameEl.className = 'name';
                    nameEl.textContent = data.title || data.channel || name;
                    cc.appendChild(nameEl);
                    if (data.subscribers) {
                        const stats = document.createElement('div');
                        stats.className = 'stats';
                        stats.textContent = data.subscribers;
                        cc.appendChild(stats);
                    }
                    if (data.live) {
                        const live = document.createElement('div');
                        live.className = 'stats';
                        live.style.color = '#ef4949';
                        live.textContent = '🔴 В ЭФИРЕ' + (data.viewers ? ' · ' + data.viewers + ' зрителей' : '');
                        cc.appendChild(live);
                    }
                    channelInfo.appendChild(cc);
                }

                // Video list
                if (data.videos && data.videos.length) {
                    const vidsTitle = document.createElement('div');
                    vidsTitle.className = 'sidebar-section-title';
                    vidsTitle.textContent = 'Видео' + (data.live ? ' (VOD) — канал в эфире' : '');
                    channelInfo.appendChild(vidsTitle);
                    data.videos.forEach(vid => {
                        vid.platform = platform;
                        // Для Twitch: url из API — twitch.tv/videos/<id>; для YouTube — youtube.com/watch?v=<id>
                        if (!vid.url && vid.id) {
                            vid.url = platform === 'twitch'
                                ? 'https://www.twitch.tv/videos/' + vid.id
                                : 'https://www.youtube.com/watch?v=' + vid.id;
                        }
                        const card = makeVideoCard(vid);
                        // Клик по ВЕСЕЙ карточке (включая миниатюру) → загрузить видео в основную область
                        card.addEventListener('click', (e) => {
                            e.stopPropagation();
                            loadVideoIntoMain(mainEl, vid);
                        });
                        channelInfo.appendChild(card);
                    });
                    // Кнопка «Смотреть последний стрим» — открывает VOD/стрим в основной области
                    const watchBtn = document.createElement('button');
                    watchBtn.style.cssText = 'margin-top:8px;width:100%;padding:9px;border-radius:9px;border:0;background:#7c5cff;color:#fff;font-size:13px;cursor:pointer;font-weight:600;';
                    watchBtn.textContent = '▶ Смотреть последний стрим';
                    watchBtn.addEventListener('click', () => {
                        const first = data.videos[0];
                        if (first) loadVideoIntoMain(mainEl, first);
                    });
                    channelInfo.appendChild(watchBtn);
                    // Auto-play first video (VOD or live)
                    const first = data.videos[0];
                    if (first && first.id) {
                        loadVideoIntoMain(mainEl, { ...first, url: 'https://www.twitch.tv/videos/' + first.id, platform: 'twitch' });
                    } else if (first) {
                        loadVideoIntoMain(mainEl, first);
                    }
                } else if (data.live && platform === 'twitch') {
                    // Live без VOD-ов — открываем стрим в плеере
                    const d = document.createElement('div');
                    d.style.cssText = 'color:var(--muted);font-size:13px;padding:8px;';
                    d.textContent = 'Канал в эфире — открываю стрим…';
                    channelInfo.appendChild(d);
                    const ifr = document.createElement('iframe');
                    const wrapIfr = document.createElement('div');
                    wrapIfr.style.cssText = 'width:100%;height:100%;position:relative;';
                    const loader = document.createElement('div');
                    loader.className = 'stream-loading';
                    loader.textContent = 'Загрузка стрима…';
                    ifr.src = (window.streamEmbedUrl || (u => u))('https://www.twitch.tv/' + (data.channel || name));
                    ifr.className = 'stream-embed';
                    ifr.allow = 'autoplay; fullscreen; picture-in-picture';
                    ifr.allowFullscreen = true;
                    ifr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
                    ifr.addEventListener('load', () => loader.remove());
                    wrapIfr.appendChild(ifr);
                    wrapIfr.appendChild(loader);
                    mainEl.innerHTML = '';
                    mainEl.appendChild(wrapIfr);
                } else {
                    // No videos, no live — dead end fallback.
                    const d = document.createElement('div');
                    d.style.cssText = 'color:var(--muted);font-size:13px;padding:8px;';
                    d.textContent = (platform === 'twitch'
                        ? 'Twitch: VOD не найдены (или канал оффлайн).'
                        : 'Видео не найдены.') + ' Откройте страницу канала в браузере, чтобы посмотреть вкладки вручную.';
                    channelInfo.appendChild(d);
                    const openBtn = document.createElement('button');
                    openBtn.style.cssText = 'margin-top:8px;width:100%;padding:9px;border-radius:9px;border:0;background:#7c5cff;color:#fff;font-size:13px;cursor:pointer;';
                    openBtn.textContent = 'Открыть канал в браузере →';
                    openBtn.addEventListener('click', () => openChannelInBrowser(name));
                    channelInfo.appendChild(openBtn);
                }
            } catch (e) {
                channelInfo.innerHTML = '<div style="color:#ef4949;font-size:13px;">Ошибка: ' + e.message + '</div>';
                const fb = document.createElement('button');
                fb.style.cssText = 'margin-top:8px;width:100%;padding:8px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:transparent;color:#e8e6f5;cursor:pointer;font-size:13px;';
                fb.textContent = 'Открыть канал в браузере →';
                fb.addEventListener('click', () => openChannelInBrowser(name));
                channelInfo.appendChild(fb);
            }
        }

        btn.addEventListener('click', openChannel);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') openChannel(); });
        input.focus();
    };

})();
