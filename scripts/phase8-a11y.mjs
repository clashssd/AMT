import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const p = path.join(process.cwd(), 'frontend/css/components-v2.css');
let s = readFileSync(p, 'utf8');
const before = s;

s += `

/* ============ FAZA 8: a11y sweep ============ */

/* ---- :focus-visible on ALL interactive elements ---- */
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:focus-visible,
summary:focus-visible,
label:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
}

/* Icon buttons: ensure aria-label is present via CSS :focus-visible ring */
.icon-btn:focus-visible,
.attach-btn:focus-visible,
.home-quickcreate:focus-visible,
.home-reset:focus-visible {
    box-shadow: 0 0 0 3px var(--focus-ring);
    outline: none;
}

/* ---- Touch targets >= 38px ---- */
.icon-btn,
.attach-btn,
.home-quickcreate,
.home-reset,
.test-btn,
.save-btn,
.action-chip,
.filter-btn,
.seg-btn,
.input-btn,
.chip {
    min-height: 38px;
}

/* ---- Prevent horizontal scroll at 760/520 ---- */
body {
    overflow-x: hidden;
}
.home-container,
.settings-layout,
.chat-layout,
.storage-layout {
    max-width: 100%;
}

/* ---- Skip-link for keyboard nav ---- */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}
.sr-only:focus-visible {
    position: fixed;
    top: 8px;
    left: 8px;
    width: auto;
    height: auto;
    margin: 0;
    clip: auto;
    padding: 8px 16px;
    background: var(--accent);
    color: var(--accent-contrast);
    border-radius: var(--radius-sm);
    z-index: 9999;
}

/* ---- details/summary: aria-expanded managed by browser, add focus ring ---- */
details[open] > summary {
    border-bottom: 1px solid var(--divider);
}
summary {
    cursor: pointer;
}
summary:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
}

/* ---- Select: ensure minimum height for touch ---- */
select {
    min-height: 38px;
}
input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]):not([type=color]) {
    min-height: 38px;
}
textarea {
    min-height: 38px;
}

/* ---- Tables: ensure readable ---- */
table {
    width: 100%;
    border-collapse: collapse;
}
th, td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--divider);
}
th {
    color: var(--text-strong);
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .04em;
}
tr:hover td {
    background: var(--table-row-hover);
}

/* ---- Contrast: ensure text on accent is readable ---- */
.btn--primary,
button.primary,
.test-btn.primary,
.save-btn.primary {
    color: var(--accent-contrast);
}

/* ---- Print: no white background on dark themes ---- */
@media print {
    body { background: white !important; color: black !important; }
    .bg-media, .toast-container { display: none !important; }
}
`;

writeFileSync(p, s);
console.log('bytes added:', Buffer.byteLength(s) - Buffer.byteLength(before));
console.log('new total lines:', s.split('\n').length);
