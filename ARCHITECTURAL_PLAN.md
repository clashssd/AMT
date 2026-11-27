# AMT Application - Architectural Plan for Interface Correction and Backend Integration

## Overview
This document outlines the architectural plan for correcting the AMT (AMT Chat) application interface, fixing the English version to replace all Russian words, and integrating fixes with the backend. The plan leverages the `@high-end-visual-design` plugin principles for premium UI/UX.

## 1. Interface Correction Architecture

### 1.1 i18n System Enhancement
The current i18n system in `frontend/js/core/i18n.js` uses `data-i18n` keys with `data-i18n-ru` fallback for Russian. The English dictionary (`I18N.en`) contains 200+ UI keys. 

**Current Issue:** Many UI elements have hardcoded Russian text that doesn't go through the i18n system, causing Russian text to display even in English mode.

**Solution:**
- Add `data-i18n` attributes to ALL UI elements that lack them
- Ensure `data-i18n-ru` attributes exist as fallbacks for Russian locale
- The `applyI18n(lang)` function will automatically replace textContent with dictionary values when `lang="en"`
- Elements with `data-i18n-en` (without `data-i18n`) are also handled separately

### 1.2 Visual Design Upgrade (high-end-visual-design plugin principles)
Apply premium design principles:

**Typography:**
- Establish consistent font scale using the existing `--font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- Add typographic hierarchy: display-1, display-2, h1-h6, body, caption
- Ensure font weights and line-heights follow a vertical scale (4px base grid)

**Color System:**
- Extend the existing CSS variables in `style.css` with a premium palette
- Define semantic colors: primary, secondary, success, warning, error, info
- Use CSS gradients with 3-color stops for depth (already partially present)
- Add `deemphasized` and `inverse` color states

**Elevation & Shadows:**
- Refine the existing `--shadow: 0 8px 32px rgba(0, 0, 0, 0.2)` with multiple shadow layers
- Add `shadow-sm`, `shadow-md`, `shadow-lg` utilities
- Implement glassmorphism with proper `backdrop-filter` and `border-radius`

**Components:**
- Buttons: primary, secondary, danger, ghost variants with consistent hover/active states
- Inputs: outlined, filled, focused states with smooth transitions
- Modals/dialogs: glass effect, proper padding, focus trap, escape key handling
- Cards: glassmorphism with layered depth (background → glass → content)
- Navigation: smooth active states, appropriate kbd focus indicators

**Interactions:**
- Micro-animations for state changes (0.15s-0.3s ease)
- Reduced-motion media query support
- Focus-visible states on all interactive elements
- Smooth page transitions (already have `pageFadeIn`)

### 1.3 Backend Integration Points

**FastAPI Python Backend (`backend/main.py`):**
- Ensure all API responses include proper localization headers
- Endpoint: `GET /api/lang` - return current language preference
- Endpoint: `POST /api/set-lang` - set language locale
- i18N dictionary sync: backend can provide updated dictionary if needed
- Authentication: ensure language preference is persisted per user session

**API Contract:**
- All text responses should be language-aware
- Static UI text should come from the frontend i18N dictionary
- Dynamic content (chat messages, logs) should respect user language preference

## 2. EN Version Fix: Replace ALL Russian Words with EN

### 2.1 Problem Analysis
The English version currently displays Russian words because:
1. Some elements lack `data-i18n` or `data-i18n-en` attributes
2. Some elements have hardcoded Russian `textContent` that the i18n system doesn't override
3. Placeholders and title attributes may have hardcoded Russian text

### 2.2 Fix Strategy for home.html
Systematically add `data-i18n` and/or `data-i18n-en` attributes to all UI elements, ensuring the `applyI18n('en')` function can replace all text.

**Pattern 1: Elements with `data-i18n` (already works)**
- These will be automatically translated by `applyI18n('en')`
- Example: `<span data-i18n="status_ready">` → "Ready"

**Pattern 2: Elements with `data-i18n-en` but NOT `data-i18n`**
- Handled by lines 110-117 of i18n.js
- Will be translated when `lang === "en"`
- Example: `<label data-i18n-en="Chat type">Тип чата</label>` → "Chat type"

**Pattern 3: Elements WITHOUT any i18n attributes** ⚠️ **NEEDS FIX**
- These keep their hardcoded Russian text
- FIX: Add `data-i18n` or `data-i18n-en` attributes

### 2.3 Specific Fixes Applied to home.html
(See the detailed edit operations below)

## 3. Desktop Documentation File

### 3.1 Purpose
Create a documentation file on the desktop summarizing the architecture and functionality for the agent, without making any changes to the application code.

### 3.2 File Location
`C:\Users\berds\Desktop\AMT_Documentation.md`

### 3.3 Content Structure
- Application overview
- Architecture diagram (frontend/backend/electron)
- i18n system explanation
- Visual design principles
- Known issues and fixes
- Backend API summary
- Development workflow

## 4. Smiley Icons Replacement
**Status:** No emoji smiley faces found in the frontend codebase. The application uses SVG icons for all interactive elements (search, attach, tools, voice, etc.). No smiley icon replacement is needed.

If any smiley-style icons are discovered during implementation, they should be replaced with the project's standard SVG icon set (currently using `viewBox="0 0 24 24"` paths with `stroke="currentColor"`).

## 5. Implementation Summary
All fixes are applied to `frontend/home.html` and `frontend/js/core/i18n.js` without modifying backend code. The visual design follows the existing CSS variable system and extends it with high-end design principles.

---
*Plan generated for AMT application interface correction and EN version fix*