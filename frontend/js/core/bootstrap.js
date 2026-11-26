
// ===== Modal accessibility (role, aria-modal, Escape, focus trap, focus return) =====
(function initModalA11y() {
    if (typeof document === 'undefined' || !document.querySelectorAll) return;

    const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function enhance(overlay) {
        if (overlay._amtA11y) return;
        overlay._amtA11y = true;
        const glass = overlay.querySelector('.modal-glass');
        if (!glass) return;
        glass.setAttribute('role', 'dialog');
        glass.setAttribute('aria-modal', 'true');
        const heading = glass.querySelector('h2, h3, [role="heading"], .modal-title');
        if (heading && !glass.getAttribute('aria-labelledby')) {
            if (!heading.id) heading.id = 'amt-modal-title-' + glass.id;
            glass.setAttribute('aria-labelledby', heading.id);
        }

        let lastFocus = null;
        function trapFocus(e) {
            if (e.key === 'Tab') {
                const focusables = Array.from(glass.querySelectorAll(FOCUSABLE)).filter(el => el.offsetParent !== null);
                if (!focusables.length) { e.preventDefault(); glass.focus(); return; }
                const first = focusables[0], last = focusables[focusables.length - 1];
                if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
                else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            }
        }
        function onKeydown(e) {
            if (e.key === 'Escape') {
                const close = glass.querySelector('.modal-close, [data-modal-close], .modal-glass .close, .test-btn.close');
                if (close) { close.click(); return; }
                overlay.classList.add('hidden');
                restore();
            }
            trapFocus(e);
        }
        function restore() {
            document.removeEventListener('keydown', onKeydown, true);
            document.removeEventListener('focusin', onKeydown, true);
            glass.removeEventListener('keydown', trapFocus);
            glass.setAttribute('tabindex', '-1');
            if (lastFocus && lastFocus.focus) lastFocus.focus();
        }
        // Intercept any .modal-overlay that becomes visible (removing .hidden) via MutationObserver.
        new MutationObserver((muts) => {
            for (const m of muts) {
                if (m.attributeName !== 'class') continue;
                const open = !overlay.classList.contains('hidden');
                if (open && !glass._amtTrapped) {
                    lastFocus = document.activeElement;
                    glass._amtTrapped = true;
                    document.addEventListener('keydown', onKeydown, true);
                    // focus first focusable
                    const f = glass.querySelector(FOCUSABLE);
                    (f || glass).focus();
                } else if (!open && glass._amtTrapped) {
                    glass._amtTrapped = false;
                    restore();
                }
            }
        }).observe(overlay, { attributes: true, attributeFilter: ['class'] });
    }

    const start = () => document.querySelectorAll('.modal-overlay').forEach(enhance);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
})();

// ===== Phase 7: scroll-reveal via IntersectionObserver =====
(function initScrollReveal() {
    const prefersReduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced || document.body.classList.contains('no-anim')) return;
    const els = document.querySelectorAll('.reveal:not(.is-visible)');
    if (!els.length) return;
    const io = new IntersectionObserver((entries) => {
        for (const e of entries) {
            if (e.isIntersecting) {
                e.target.classList.add('is-visible');
                io.unobserve(e.target);
            }
        }
    }, { threshold: 0.15 });
    els.forEach((el, i) => {
        el.style.setProperty('--reveal-delay', (i * 60) + 'ms');
        io.observe(el);
    });
    // Cleanup on pagehide
    addEventListener('pagehide', () => io.disconnect());
    // If elements are already in viewport, reveal immediately
    requestAnimationFrame(() => {
        els.forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.top < innerHeight && r.bottom > 0) el.classList.add('is-visible');
        });
    });
})();

