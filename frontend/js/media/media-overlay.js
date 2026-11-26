// ===== МЕДИА-ОВЕРЛЕЙ (видео-плеер / фото / аудио / файлы) =====
(function () {
    const overlay = document.getElementById('mediaOverlay');
    const content = document.getElementById('mediaOverlayContent');
    const closeBtn = document.getElementById('mediaOverlayClose');
    const minimizeBtn = document.getElementById('mediaOverlayMinimize');
    const controls = document.getElementById('mediaPlayerControls');
    const seek = document.getElementById('playerSeek');
    const timeEl = document.getElementById('playerTime');
    const playBtn = document.getElementById('playerPlayPause');
    const muteBtn = document.getElementById('playerVolumeMute');
    const volSlider = document.getElementById('playerVolume');
    const subBtn = document.getElementById('playerSubtitles');
    const qualitySel = document.getElementById('playerQuality');
    const fsBtn = document.getElementById('playerFullscreen');
    const pipBtn = document.getElementById('playerPip');
    const filtersToggle = document.getElementById('playerFiltersToggle');
    const filtersPanel = document.getElementById('mediaFiltersPanel');
    const filtersReset = document.getElementById('mediaFiltersReset');
    const filterSliders = ['filterBrightness','filterContrast','filterSaturate','filterHue','filterBlur','filterDetail','filterNoise','filterSharp']
        .map(id => document.getElementById(id)).filter(Boolean);
    if (!overlay) return;

    let currentVideo = null;
    let currentQualities = null;
    let currentStream = null;
    let currentStreamWrap = null;
    let activeTab = 'video';

    // New tabbed layout refs
    const playerMain = document.getElementById('playerMain');
    const playerSidebar = document.getElementById('playerSidebar');
    const playerTabs = document.getElementById('playerTabs');

    function closeOverlay() {
        overlay.classList.add('hidden');
        if (currentVideo) { currentVideo.pause(); currentVideo = null; }
        if (currentStream) { try { currentStream.src = ''; } catch(e){} currentStream = null; }
        if (currentStreamWrap) { currentStreamWrap.style.filter = ''; currentStreamWrap = null; }
        if (document.fullscreenElement) document.exitFullscreen();
        controls.style.display = 'none';
        if (filtersPanel) filtersPanel.classList.add('hidden');
        resetFilters();
        // Reset tabs
        setPlayerTab('video');
        if (playerSidebar) playerSidebar.classList.add('hidden');
        // Закрываем встроенное browser-окно (если открыто)
        if (window.api && window.api.closeBrowserWindow) {
            window.api.closeBrowserWindow().catch(() => {});
        }
    }

    function setPlayerTab(tab) {
        activeTab = tab;
        if (playerTabs) {
            playerTabs.querySelectorAll('.player-tab').forEach(b => {
                b.classList.toggle('active', b.dataset.tab === tab);
            });
        }
        // Show sidebar for video/stream/search/channel tabs, hide for image/audio/file
        if (playerSidebar) {
            playerSidebar.classList.toggle('hidden', !['video', 'stream', 'search', 'channel'].includes(tab));
        }
        // Show/hide tabs bar — hide for image/audio/file
        if (playerTabs) {
            playerTabs.style.display = ['image', 'audio', 'file'].includes(tab) ? 'none' : '';
        }
    }

    // Показывает контроллы для iframe-режима (видео/стримы): доступны только фильтры и полный экран,
    // видео-специфичные кнопки (play/мьют/громкость/субтитры/качество/PiP) и timeline скрываются CSS-классом.
    function showIframeControls() {
        if (!controls) return;
        controls.classList.add('iframe-mode');
        controls.style.display = 'flex';
    }
    function hideIframeControls() {
        if (!controls) return;
        controls.classList.remove('iframe-mode');
        controls.style.display = 'none';
    }

    // Глобальные кнопки (фильтры/полный экран) — один раз в начале модуля.
    initGlobalPlayerButtons();

    function openOverlay(type, src, opts = {}) {
        // Render into playerMain (new tabbed layout) instead of content (legacy)
        const target = playerMain || content;
        target.innerHTML = '';
        if (playerSidebar) playerSidebar.innerHTML = '';
        closeOverlay();
        overlay.classList.remove('hidden');
        controls.style.display = 'none';

        // Determine which tab to activate
        let tab = type;
        if (type === 'stream') tab = 'stream';
        else if (type === 'video') tab = 'video';
        else if (type === 'search') tab = 'search';
        else if (type === 'channel') tab = 'channel';
        setPlayerTab(tab);

        if (type === 'video') {
            // YouTube/Twitch URL → iframe embed (native <video> can't play web pages)
            const isYtUrl = /youtube\.com|youtu\.be/.test(src);
            const isTwUrl = /twitch\.tv/.test(src);
            // Любой другой http(s) URL — пробуем iframe в плеере (часть сайтов
            // позволяет встраивание, часть блокирует через X-Frame-Options).
            // Если заблокирован — показываем карточку с кнопкой «Открыть в браузере».
            const isWebUrl = /^https?:\/\//i.test(src);
            if (isYtUrl || isTwUrl || isWebUrl) {
                const wrap = document.createElement('div');
                wrap.className = 'stream-filter-wrap';
                wrap.style.cssText = 'width:100%;height:100%;position:relative;';
                const loader = document.createElement('div');
                loader.className = 'stream-loading';
                loader.textContent = isYtUrl || isTwUrl ? 'Загрузка стрима…' : 'Загрузка страницы…';
                const ifr = document.createElement('iframe');
                if (isYtUrl) {
                    const m = src.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/);
                    if (m) ifr.src = 'https://www.youtube.com/embed/' + m[1] + '?autoplay=1';
                    else ifr.src = 'https://www.youtube.com/embed/' + src.replace(/^https?:\/\//, '');
                } else if (isTwUrl) {
                    ifr.src = streamEmbedUrl(src);
                } else {
                    // Любой другой http(s) URL — iframe прямо (с referrerPolicy,
                    // чтобы часть сайтов с X-Frame-Options: SAMEORIGIN прошла).
                    ifr.src = src;
                    ifr.referrerPolicy = 'no-referrer';
                }
                ifr.allow = 'autoplay; fullscreen; picture-in-picture';
                ifr.allowFullscreen = true;
                ifr.style.cssText = 'width:100%;height:100%;border:0;border-radius:10px;position:absolute;top:0;left:0;';
                ifr.addEventListener('load', () => loader.remove());
                // Для не-YouTube/Twitch: если iframe заблокирован (X-Frame-Options/DENY),
                // через 4 сек показываем fallback-карточку с кнопкой «Открыть в браузере».
                if (!isYtUrl && !isTwUrl) {
                    let blocked = false;
                    const showBlocked = () => {
                        if (blocked) return;
                        blocked = true;
                        const card = document.createElement('div');
                        card.className = 'web-link-main';
                        card.style.cssText = 'height:100%;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:14px;padding:40px;text-align:center;position:relative;z-index:1;background:var(--panel,rgba(10,10,18,0.95));';
                        const t = document.createElement('div');
                        t.style.cssText = 'font-size:20px;font-weight:600;color:#e8e6f5;max-width:560px;word-break:break-all;';
                        t.textContent = src;
                        card.appendChild(t);
                        const host = (function () { try { return new URL(src).hostname.replace(/^www\./, ''); } catch (_) { return ''; } })();
                        if (host) {
                            const h = document.createElement('div');
                            h.style.cssText = 'color:var(--muted);font-size:13px;';
                            h.textContent = host;
                            card.appendChild(h);
                        }
                        const note = document.createElement('div');
                        note.style.cssText = 'color:var(--muted);font-size:12px;max-width:420px;';
                        note.textContent = 'Сайт не позволяет встроить страницу в iframe (X-Frame-Options). Откройте в плеере (отдельное окно внутри приложения):';
                        card.appendChild(note);
                        // Кнопка «Открыть в плеере» — frameless Electron-окно (внутри приложения)
                        if (window.api && window.api.openBrowserWindow) {
                            const bv = document.createElement('button');
                            bv.style.cssText = 'margin-top:8px;padding:10px 22px;border-radius:10px;border:0;background:#7c5cff;color:#fff;font-size:14px;cursor:pointer;';
                            bv.textContent = '🌐 Открыть в плеере';
                            bv.addEventListener('click', () => {
                                if (wrap) wrap.style.display = 'none';
                                window.api.openBrowserWindow(src).catch(() => {
                                    if (wrap) wrap.style.display = '';
                                    if (window.api.openExternal) window.api.openExternal(src);
                                });
                            });
                            card.appendChild(bv);
                        } else {
                            const btn = document.createElement('button');
                            btn.style.cssText = 'margin-top:8px;padding:10px 22px;border-radius:10px;border:0;background:#7c5cff;color:#fff;font-size:14px;cursor:pointer;';
                            btn.textContent = 'Открыть в браузере';
                            btn.addEventListener('click', () => {
                                if (window.api && window.api.openExternal) window.api.openExternal(src);
                                else window.open(src, '_blank', 'noopener');
                            });
                            card.appendChild(btn);
                        }
                        wrap.appendChild(card);
                    };
                    const t = setTimeout(showBlocked, 4000);
                    ifr.addEventListener('load', () => clearTimeout(t));
                }
                setTimeout(() => { if (loader.parentNode) loader.textContent = isYtUrl || isTwUrl ? 'Не удаётся загрузить — возможно, стрим оффлайн или сайт заблокировал встраивание.' : 'Не удаётся загрузить — возможно, сайт заблокировал встраивание.'; }, 8000);
                wrap.appendChild(ifr);
                wrap.appendChild(loader);
                target.appendChild(wrap);
                currentStream = ifr;
                currentStreamWrap = wrap;
                showIframeControls();
            } else {
                // Прямой медиа-файл (mp4/webm) — нативный <video>
                const v = document.createElement('video');
                v.src = src;
                v.controls = false;
                v.loop = opts.loop || false;
                v.crossOrigin = 'anonymous';
                v.style.width = '100%'; v.style.maxHeight = 'calc(100vh - 140px)';
                target.appendChild(v);
                currentVideo = v;
                currentQualities = Array.isArray(opts.qualities) ? opts.qualities : null;
                if (pipBtn) pipBtn.classList.toggle('hidden', !('requestPictureInPicture' in v));
                controls.classList.remove('iframe-mode');
                controls.style.display = 'flex';
                initPlayerControls(v);
                v.play();
            }
        } else if (type === 'stream') {
            if (opts.channel) {
                // Канал → переключаемся на вкладку «Каналы» и предзаполняем
                setPlayerTab('channel');
                if (window.initChannelTab) window.initChannelTab(playerSidebar, target);
                // Предзаполняем input и запускаем поиск
                setTimeout(() => {
                    const inp = playerSidebar.querySelector('input[placeholder="Имя канала…"]');
                    if (inp && opts.channelName) {
                        inp.value = opts.channelName;
                        const btn = inp.parentElement.querySelector('button');
                        if (btn) btn.click();
                    }
                }, 50);
                return;
            }
            const wrap = document.createElement('div');
            wrap.className = 'stream-filter-wrap';
            wrap.style.cssText = 'width:100%;height:100%;position:relative;';
            const loader = document.createElement('div');
            loader.className = 'stream-loading';
            loader.textContent = 'Загрузка стрима…';
            const ifr = document.createElement('iframe');
            ifr.src = streamEmbedUrl(src);
            ifr.className = 'stream-embed';
            ifr.allow = 'autoplay; fullscreen; picture-in-picture';
            ifr.allowFullscreen = true;
            ifr.style.cssText = 'width:100%;height:100%;border:0;position:absolute;top:0;left:0;';
            ifr.addEventListener('load', () => loader.remove());
            setTimeout(() => { if (loader.parentNode) loader.textContent = 'Не удаётся загрузить — возможно, канал оффлайн или Twitch заблокировал встраивание.'; }, 8000);
            wrap.appendChild(ifr);
            wrap.appendChild(loader);
            target.appendChild(wrap);
            currentStream = ifr;
            // Сохраняем wrapper для применения фильтров
            currentStreamWrap = wrap;
            showIframeControls();
        } else if (type === 'image') {
            const img = document.createElement('img');
            img.src = src;
            img.alt = opts.alt || '';
            target.appendChild(img);
        } else if (type === 'audio') {
            const a = document.createElement('audio');
            a.src = src;
            a.controls = true;
            a.loop = opts.loop || false;
            target.appendChild(a);
            a.play();
        } else if (type === 'file') {
            const div = document.createElement('div');
            div.className = 'file-preview';
            div.innerHTML = `<h3 style="margin:0 0 12px">${escapeHtml(opts.filename || 'Файл')}</h3><pre>${escapeHtml(opts.content || 'Нет превью')}</pre>`;
            target.appendChild(div);
        } else if (type === 'search' || type === 'channel') {
            // Placeholder: will be filled by player-browser.js
            const ph = document.createElement('div');
            ph.style.cssText = 'color:var(--muted);font-size:16px;text-align:center;padding:40px;';
            ph.textContent = type === 'search' ? '🔍 Введите запрос' : '📺 Введите канал';
            target.appendChild(ph);
        }
    }

    // Конвертирует ссылку YouTube/Twitch в URL встроенного плеера (iframe).
    function streamEmbedUrl(url) {
        try {
            const u = new URL(url);
            const host = u.hostname.replace(/^www\./, '');
            if (host === 'youtu.be') {
                const id = u.pathname.slice(1).split('/')[0];
                return 'https://www.youtube.com/embed/' + id + '?autoplay=1';
            }
            if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
                if (u.pathname === '/embed/' || u.searchParams.has('embed')) {
                    return url.replace('/shorts/', '/embed/');
                }
                const id = u.searchParams.get('v') || u.pathname.split('/')[2];
                if (id) return 'https://www.youtube.com/embed/' + id + '?autoplay=1';
            }
            if (host === 'twitch.tv') {
                const chan = u.pathname.split('/').filter(Boolean)[0];
                if (chan) {
                    // Для Electron/file:// protocol location.hostname пустой —
                    // Twitch player требует parent-домен; используем 127.0.0.1
                    const parent = location.hostname || '127.0.0.1';
                    return 'https://player.twitch.tv/?channel=' + chan + '&parent=' + encodeURIComponent(parent);
                }
            }
        } catch (e) { /* не URL — оставляем как есть */ }
        return url;
    }
    window.streamEmbedUrl = streamEmbedUrl;

    function initPlayerControls(video) {
        function fmtTime(s) {
            s = Math.max(0, Math.floor(s));
            const m = Math.floor(s / 60), sec = s % 60;
            return m + ':' + String(sec).padStart(2, '0');
        }
        function updateTime() {
            if (!currentVideo) return;
            timeEl.textContent = fmtTime(currentVideo.currentTime) + ' / ' + fmtTime(currentVideo.duration || 0);
            if (seek) seek.value = currentVideo.duration ? (currentVideo.currentTime / currentVideo.duration * 100) : 0;
        }
        video.addEventListener('timeupdate', updateTime);
        video.addEventListener('loadedmetadata', updateTime);
        video.addEventListener('ended', () => { if (playBtn) playBtn.textContent = '▶'; });

        if (seek) {
            seek.addEventListener('input', () => {
                if (currentVideo && currentVideo.duration) {
                    currentVideo.currentTime = seek.value / 100 * currentVideo.duration;
                }
            });
        }
        if (playBtn) {
            playBtn.addEventListener('click', () => {
                if (!currentVideo) return;
                if (currentVideo.paused) { currentVideo.play(); playBtn.textContent = '⏸'; }
                else { currentVideo.pause(); playBtn.textContent = '▶'; }
            });
        }
        video.addEventListener('play', () => { if (playBtn) playBtn.textContent = '⏸'; });
        video.addEventListener('pause', () => { if (playBtn) playBtn.textContent = '▶'; });

        if (muteBtn) {
            muteBtn.addEventListener('click', () => {
                if (!currentVideo) return;
                currentVideo.muted = !currentVideo.muted;
                muteBtn.textContent = currentVideo.muted ? '🔇' : '🔊';
                if (volSlider) volSlider.value = currentVideo.muted ? 0 : (currentVideo.volume * 100);
            });
        }
        if (volSlider) {
            volSlider.addEventListener('input', () => {
                if (!currentVideo) return;
                currentVideo.volume = volSlider.value / 100;
                currentVideo.muted = volSlider.value == 0;
                muteBtn.textContent = currentVideo.muted ? '🔇' : '🔊';
            });
        }
        if (subBtn) {
            subBtn.addEventListener('click', () => {
                subBtn.classList.toggle('active');
                // Встроенные субтитры браузера: toggle через video textTracks
                if (currentVideo && currentVideo.textTracks) {
                    const tt = currentVideo.textTracks;
                    for (let i = 0; i < tt.length; i++) {
                        tt[i].mode = subBtn.classList.contains('active') ? 'showing' : 'hidden';
                    }
                }
            });
        }
        if (qualitySel) {
            qualitySel.addEventListener('change', () => {
                const val = qualitySel.value;
                if (!currentQualities || !currentVideo) return;
                const match = currentQualities.find(q => String(q.label) === val || String(q.value) === val || String(q.url) === val);
                if (match && match.url) {
                    const t = currentVideo.currentTime;
                    currentVideo.src = match.url;
                    currentVideo.play().then(() => { try { currentVideo.currentTime = t; } catch(e){} }).catch(()=>{});
                    flashStatus('Качество: ' + qualitySel.options[qualitySel.selectedIndex].text);
                } else {
                    flashStatus('Качество: ' + qualitySel.options[qualitySel.selectedIndex].text);
                }
            });
            // Заполняем селект из opts.qualities, если переданы
            if (currentQualities && currentQualities.length) {
                qualitySel.innerHTML = currentQualities.map(q =>
                    `<option value="${escapeHtml(String(q.url || q.label))}">${escapeHtml(q.label)}</option>`
                ).join('');
            }
        }
        if (pipBtn) {
            pipBtn.addEventListener('click', async () => {
                if (!currentVideo) return;
                if (document.pictureInPictureElement) {
                    try { await document.exitPictureInPicture(); } catch(e){}
                } else if (currentVideo.requestPictureInPicture) {
                    try { await currentVideo.requestPictureInPicture(); } catch(e){ flashStatus('PiP недоступен'); }
                }
            });
        }
    }

    // Кнопки, которые работают и для нативного <video>, и для iframe (фильтры/экран/сброс).
    // Прикрепляются ОДИН РАЗ в начале модуля — иначе в iframe-режиме initPlayerControls
    // не вызывается и эти кнопки «мёртвые».
    function initGlobalPlayerButtons() {
        if (filtersToggle && filtersPanel) {
            filtersToggle.addEventListener('click', () => {
                filtersPanel.classList.toggle('hidden');
                // Активная подсветка кнопки + мгновенное применение текущих фильтров
                filtersToggle.classList.toggle('active', !filtersPanel.classList.contains('hidden'));
                applyFilters();
            });
        }
        if (filtersReset) {
            filtersReset.addEventListener('click', () => resetFilters());
        }
        filterSliders.forEach(sl => {
            sl.addEventListener('input', () => applyFilters());
        });
        if (fsBtn) {
            fsBtn.addEventListener('click', () => {
                // В Electron — переключаем полноэкранный режим всего окна (надежнее, чем overlay.requestFullscreen).
                // ФАЙЛЫ/ИМAGED/АУДИО и iframe-режим: фильтры применяются к контейнеру playerMain,
                // поэтому в fullscreen они остаются видимыми (не сбрасываются).
                // Добавляем/убираем класс .fullscreen на оверлее — CSS убирает padding/сайдбар.
                if (window.api && window.api.toggleFullscreen) {
                    window.api.toggleFullscreen().then(r => {
                        if (r && r.fullscreen !== undefined) {
                            overlay.classList.toggle('fullscreen', r.fullscreen);
                        }
                    }).catch(() => {
                        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
                        else if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
                    });
                    return;
                }
                if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
                else if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
            });
        }
    }

    function applyFilters() {
        const g = id => { const el = document.getElementById(id); return el ? el.value : null; };
        const b = g('filterBrightness'), c = g('filterContrast'), s = g('filterSaturate'), h = g('filterHue'), bl = g('filterBlur');
        const d = g('filterDetail'), n = g('filterNoise'), sh = g('filterSharp');
        // Детализация/шум/улучшение — CSS-приёмы:
        //  - detail → контраст + чёткость (contrast + saturate-буст)
        //  - noise → лёгкое blur + контраст (имитация зерна)
        //  - sharp → контраст + насыщенность (имитация sharpen)
        const effContrast = c ? (Number(c) + (Number(sh||0)-100) * 0.15 - (Number(n||0) * 0.05)) : 100;
        const effSaturate = s ? (Number(s) + (Number(d||0)-100) * 0.2) : 100;
        const effBlur = bl ? (Number(bl) + (Number(n||0) * 0.02)) : 0;
        const filterVal = `brightness(${b}%) contrast(${effContrast.toFixed(1)}%) saturate(${effSaturate.toFixed(1)}%) hue-rotate(${h}deg) blur(${effBlur.toFixed(2)}px)`;
        if (currentVideo) {
            currentVideo.style.filter = filterVal;
        } else if (playerMain) {
            // Для iframe-стримов/видео: применяем фильтр к контейнеру playerMain
            playerMain.style.filter = filterVal;
        }
        filterSliders.forEach(sl => {
            const out = sl.parentElement.querySelector('[data-out]');
            if (out) {
                const id = sl.id;
                out.textContent = id === 'filterHue' ? (sl.value + '°') : (id === 'filterBlur' ? (sl.value + 'px') : (sl.value + '%'));
            }
        });
    }

    function resetFilters() {
        const defs = { filterBrightness:100, filterContrast:100, filterSaturate:100, filterHue:0, filterBlur:0,
                      filterDetail:100, filterNoise:0, filterSharp:100 };
        Object.keys(defs).forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.value = defs[id]; const out = el.parentElement.querySelector('[data-out]'); if (out) out.textContent = el.value + (id==='filterHue'?'°':(id==='filterBlur'||id==='filterNoise'||id==='filterDetail'||id==='filterSharp') ? (id==='filterBlur'?'px':'%') : ''); }
        });
        if (currentVideo) currentVideo.style.filter = '';
        if (playerMain) playerMain.style.filter = '';
        if (currentStreamWrap) currentStreamWrap.style.filter = '';
    }

    closeBtn.addEventListener('click', closeOverlay);
    // Минимизация: переключает в floating-режим (виджет в углу, чат доступен)
    const dragHandle = document.getElementById('mediaOverlayDrag');
    if (minimizeBtn) {
        minimizeBtn.addEventListener('click', () => {
            if (overlay.classList.contains('floating')) {
                // Выход из floating → обычный полноэкранный режим
                overlay.classList.remove('floating');
                overlay.style.left = '';
                overlay.style.top = '';
                overlay.style.right = '';
                overlay.style.bottom = '';
                overlay.style.width = '';
                overlay.style.height = '';
            } else {
                // Вход в floating: сбрасываем инлайновые координаты, чтобы правила CSS .floating сработали
                overlay.style.left = '';
                overlay.style.top = '';
                overlay.style.right = '';
                overlay.style.bottom = '';
                overlay.style.width = '';
                overlay.style.height = '';
                overlay.classList.add('floating');
            }
        });

        // Drag для floating-вида: перетаскивание за верхнюю ручку (.media-overlay-drag).
        // Сам оверлей не ловит mousedown — iframe/видео «съедают» события.
        const dragSource = dragHandle || overlay;
        let dragOffX = 0, dragOffY = 0, dragging = false;
        dragSource.addEventListener('mousedown', (e) => {
            if (!overlay.classList.contains('floating')) return;
            // Не стартуем drag от кнопок/инпутов
            if (e.target.closest('button, input, select, a, .media-overlay-close, .media-overlay-minimize')) return;
            dragging = true;
            const rect = overlay.getBoundingClientRect();
            dragOffX = e.clientX - rect.left;
            dragOffY = e.clientY - rect.top;
            overlay.style.left = rect.left + 'px';
            overlay.style.top = rect.top + 'px';
            overlay.style.right = 'auto';
            overlay.style.bottom = 'auto';
            overlay.classList.add('dragging');
            e.preventDefault();
        });
        document.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            let nx = e.clientX - dragOffX;
            let ny = e.clientY - dragOffY;
            const ow = overlay.offsetWidth || 360;
            const oh = overlay.offsetHeight || 240;
            nx = Math.max(0, Math.min(nx, Math.max(0, window.innerWidth - ow)));
            ny = Math.max(0, Math.min(ny, Math.max(0, window.innerHeight - oh)));
            overlay.style.left = nx + 'px';
            overlay.style.top = ny + 'px';
        });
        document.addEventListener('mouseup', () => {
            if (dragging) {
                dragging = false;
                overlay.classList.remove('dragging');
            }
        });
    }
    // Tab switching
    if (playerTabs) {
        playerTabs.querySelectorAll('.player-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                setPlayerTab(tab);
                // Trigger tab-specific init (search/channel tabs will be handled by player-browser.js)
                if (tab === 'search') {
                    if (window.initSearchTab) window.initSearchTab(playerSidebar, playerMain);
                } else if (tab === 'channel') {
                    if (window.initChannelTab) window.initChannelTab(playerSidebar, playerMain);
                }
            });
        });
    }
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !overlay.classList.contains('hidden')) closeOverlay();
    });

    // ===== AUTO-HIDE CONTROLS ON MOUSE IDLE (5s) =====
    // В fullscreen-режиме (или просто при открытом плеере) контроллы
    // (табы, кнопки, фильтры, сайдбар) автоматически скрываются через 5 секунд
    // бездействия мыши. При любом движении мыши/клике/скролле — появляются
    // мгновенно. Это реализовано через CSS-класс .controls-hidden на оверлее.
    let idleTimer = null;
    function resetIdleTimer() {
        overlay.classList.remove('controls-hidden');
        if (idleTimer) clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
            // Скрываем только если оверлей открыт и не в floating-режиме
            if (!overlay.classList.contains('hidden') && !overlay.classList.contains('floating')) {
                overlay.classList.add('controls-hidden');
            }
        }, 5000);
    }
    // События, которые сбрасывают таймер
    ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart'].forEach(ev => {
        overlay.addEventListener(ev, resetIdleTimer, { passive: true });
    });
    // Запускаем таймер при открытии оверлея
    const _origOpen = openOverlay;
    openOverlay = function (type, src, opts) {
        _origOpen(type, src, opts);
        resetIdleTimer();
    };

    // Экспортируем для использования из renderGenInChat
    window.openMediaOverlay = openOverlay;
    window.setPlayerTab = setPlayerTab;
    window.getPlayerMain = () => playerMain;
    window.getPlayerSidebar = () => playerSidebar;
})();
