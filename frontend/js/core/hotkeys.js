/**
 * hotkeys.js — система хоткеев (по умолчанию не назначены)
 */
(function() {
  'use strict';
  
  const HOTKEYS_STORAGE = 'amt_hotkeys';
  
  // Все доступные хоткеи (по умолчанию пустые)
  const AVAILABLE_HOTKEYS = {
    'nav_home': { description: 'Перейти на главную' },
    'nav_chat': { description: 'Перейти в чат' },
    'nav_settings': { description: 'Перейти в настройки' },
    'nav_docs': { description: 'Открыть документацию' },
    'nav_storage': { description: 'Открыть хранилище' },
    'nav_logs': { description: 'Открыть логи' },
    'command_help': { description: 'Показать помощь' },
    'toggle_web_agent': { description: 'Переключить веб-агента' },
    'toggle_jailbreak': { description: 'Переключить jailbreak' },
    'toggle_system': { description: 'Переключить системный агент' },
    'quick_file': { description: 'Быстрый ген файл' },
    'quick_media': { description: 'Быстрый ген медиа' }
  };
  
  let hotkeys = {};
  let recording = false;
  let currentTarget = null;
  
  // Загружаем из localStorage
  function loadHotkeys() {
    try {
      const saved = localStorage.getItem(HOTKEYS_STORAGE);
      hotkeys = saved ? JSON.parse(saved) : {};
    } catch (e) {
      hotkeys = {};
    }
  }
  
  // Сохраняем в localStorage
  function saveHotkeys() {
    localStorage.setItem(HOTKEYS_STORAGE, JSON.stringify(hotkeys));
  }
  
  // Инициализация
  function init() {
    loadHotkeys();
    setupGlobalKeydown();
  }
  
  // Глобальный обработчик нажатий
  function setupGlobalKeydown() {
    document.addEventListener('keydown', (e) => {
      // Если сейчас записываем новый хоткей
      if (recording && currentTarget) {
        e.preventDefault();
        e.stopPropagation();
        
        // Формируем комбинацию
        let combo = '';
        if (e.ctrlKey) combo += 'Ctrl+';
        if (e.altKey) combo += 'Alt+';
        if (e.shiftKey) combo += 'Shift+';
        if (e.metaKey) combo += 'Meta+';
        
        // Добавляем саму клавишу
        const key = e.key === ' ' ? 'Space' : e.key;
        combo += key.toUpperCase();
        
        // Если комбинация уже назначена — предупреждаем
        const existing = findHotkeyForCombo(combo);
        if (existing && existing !== currentTarget) {
          alert(`Комбинация ${combo} уже назначена на "${AVAILABLE_HOTKEYS[existing].description}"`);
          recording = false;
          return;
        }
        
        // Записываем
        hotkeys[currentTarget] = combo;
        saveHotkeys();
        
        // Обновляем UI
        updateHotkeyDisplay(currentTarget, combo);
        
        // Останавливаем запись
        recording = false;
        currentTarget = null;
        document.body.classList.remove('recording-hotkey');
        return;
      }
      
      // Проверяем назначенные хоткеи
      if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        const combo = getComboString(e);
        for (const [id, assigned] of Object.entries(hotkeys)) {
          if (assigned && assigned === combo) {
            e.preventDefault();
            triggerHotkey(id);
            return;
          }
        }
      }
    });
  }
  
  // Получает строку комбинации
  function getComboString(e) {
    let combo = '';
    if (e.ctrlKey) combo += 'Ctrl+';
    if (e.altKey) combo += 'Alt+';
    if (e.shiftKey) combo += 'Shift+';
    if (e.metaKey) combo += 'Meta+';
    
    const key = e.key === ' ' ? 'Space' : e.key;
    combo += key.toUpperCase();
    
    return combo;
  }
  
  // Ищет хоткей по комбинации
  function findHotkeyForCombo(combo) {
    for (const [id, assigned] of Object.entries(hotkeys)) {
      if (assigned === combo) return id;
    }
    return null;
  }
  
  // Запускает действие хоткея
  function triggerHotkey(hotkeyId) {
    switch(hotkeyId) {
      case 'nav_home':
        navigateTo('home');
        break;
      case 'nav_chat':
        navigateTo('chat');
        break;
      case 'nav_settings':
        navigateTo('settings');
        break;
      case 'nav_docs':
        navigateTo('docs');
        break;
      case 'nav_storage':
        navigateTo('storage');
        break;
      case 'nav_logs':
        navigateTo('logs');
        break;
      case 'command_help':
        showHelpOverlay();
        break;
      case 'toggle_web_agent':
        toggleAgent('web');
        break;
      case 'toggle_jailbreak':
        toggleJailbreak();
        break;
      case 'toggle_system':
        toggleAgent('system');
        break;
      case 'quick_file':
        quickGen('file');
        break;
      case 'quick_media':
        quickGen('media');
        break;
    }
  }
  
  // Навигация
  function navigateTo(page) {
    if (window.AMTCmds && window.AMTCmds.navigateTo) {
      window.AMTCmds.navigateTo(page);
    } else {
      // Фолбэк: просто переключаем страницы через UI
      document.querySelectorAll('[data-page]').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
      });
    }
  }
  
  // Показ помощи
  function showHelpOverlay() {
    if (window.AMTCmds && window.AMTCmds.showHelp) {
      window.AMTCmds.showHelp();
    } else {
      alert('Помошь: /help');
    }
  }
  
  // Переключение агента
  function toggleAgent(agentType) {
    if (window.AMTCmds && window.AMTCmds.toggleAgent) {
      window.AMTCmds.toggleAgent(agentType);
    }
  }
  
  // Переключение jailbreak
  function toggleJailbreak() {
    if (window.AMTCmds && window.AMTCmds.toggleJailbreak) {
      window.AMTCmds.toggleJailbreak();
    }
  }
  
  // Быстрая генерация
  function quickGen(type) {
    if (window.AMTCmds && window.AMTCmds.quickGen) {
      window.AMTCmds.quickGen(type);
    }
  }
  
  // UI для записи нового хоткея
  function startRecording(hotkeyId) {
    recording = true;
    currentTarget = hotkeyId;
    document.body.classList.add('recording-hotkey');
    updateHotkeyDisplay(hotkeyId, 'Нажми клавишу...');
  }
  
  function cancelRecording() {
    recording = false;
    currentTarget = null;
    document.body.classList.remove('recording-hotkey');
  }
  
  // Обновляет отображение
  function updateHotkeyDisplay(hotkeyId, text) {
    const el = document.getElementById(`hotkey-${hotkeyId}`);
    if (el) {
      el.textContent = text;
      el.dataset.assigned = text;
    }
  }
  
  // UI для настроек хоткеев
  function renderHotkeySettings(container) {
    loadHotkeys();
    
    let html = '<h3>Хоткеи</h3><p>Нажми "Назначить" и затем клавишу. По умолчанию все не назначены.</p>';
    
    for (const [id, info] of Object.entries(AVAILABLE_HOTKEYS)) {
      const current = hotkeys[id] || '';
      html += `
        <div class="hotkey-row">
          <div class="hotkey-info">
            <strong>${info.description}</strong>
            <code class="hotkey-combo">${current || '—'}</code>
          </div>
          <div class="hotkey-actions">
            <button class="btn small" data-action="assign" data-hotkey="${id}">Назначить</button>
            ${current ? `<button class="btn small" data-action="clear" data-hotkey="${id}">Сбросить</button>` : ''}
          </div>
        </div>
      `;
    }
    
    container.innerHTML = html;
    
    // Обработчики
    container.querySelectorAll('[data-action="assign"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const hotkeyId = btn.dataset.hotkey;
        startRecording(hotkeyId);
      });
    });
    
    container.querySelectorAll('[data-action="clear"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const hotkeyId = btn.dataset.hotkey;
        hotkeys[hotkeyId] = '';
        saveHotkeys();
        updateHotkeyDisplay(hotkeyId, '—');
        renderHotkeySettings(container);
      });
    });
  }
  
  // Экспорт
  window.AMTHotkeys = {
    init,
    loadHotkeys,
    saveHotkeys,
    startRecording,
    cancelRecording,
    renderHotkeySettings,
    triggerHotkey,
    AVAILABLE_HOTKEYS
  };
  
  // Авто-инициализация
  document.addEventListener('DOMContentLoaded', () => {
    init();
  });
})();
