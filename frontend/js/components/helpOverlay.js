/**
 * helpOverlay.js — модальная справка по командам
 */
(function() {
  'use strict';
  
  let overlayEl = null;
  
  function createOverlay() {
    if (overlayEl) return overlayEl;
    
    overlayEl = document.createElement('div');
    overlayEl.id = 'command-help-overlay';
    overlayEl.className = 'command-help-overlay';
    overlayEl.innerHTML = `
      <div class="command-help-modal">
        <div class="modal-header">
          <h2>Справка по командам</h2>
          <button class="close-btn" title="Закрыть">&times;</button>
        </div>
        <div class="modal-body">
          <div class="command-list"></div>
        </div>
        <div class="modal-footer">
          <button class="btn secondary copy-all">Скопировать все</button>
          <button class="btn primary close">Закрыть</button>
        </div>
      </div>
    `;
    
    document.body.appendChild(overlayEl);
    
    // Кнопки закрытия
    overlayEl.querySelector('.close-btn').addEventListener('click', close);
    overlayEl.querySelector('.close').addEventListener('click', close);
    overlayEl.addEventListener('click', (e) => {
      if (e.target === overlayEl) close();
    });
    
    // Копировать все
    overlayEl.querySelector('.copy-all').addEventListener('click', () => {
      const commands = getCommandsText();
      navigator.clipboard.writeText(commands).then(() => {
        alert('Скопировано в буфер обмена');
      });
    });
    
    return overlayEl;
  }
  
  function getCommandsText() {
    const commands = overlayEl?.querySelectorAll('.command-item');
    if (!commands) return '';
    
    let text = 'Список команд AMT Chat:\n\n';
    commands.forEach(cmd => {
      const id = cmd.querySelector('code')?.textContent;
      const desc = cmd.querySelector('.desc')?.textContent;
      const examples = cmd.querySelector('.examples')?.textContent;
      
      text += `/${id}\n${desc}\n`;
      if (examples) text += `Примеры: ${examples}\n`;
      text += '\n';
    });
    
    return text;
  }
  
  async function show() {
    const overlay = createOverlay();
    
    // Загружаем реестр команд и генерируем примеры
    let commands;
    try {
      if (window.AMTCmds && window.AMTCmds.getCommandHelp) {
        commands = await window.AMTCmds.getCommandHelp();
      } else {
        const response = await fetch('/api/command-registry');
        const registry = await response.json();
        commands = registry.commands.map(cmd => ({
          id: cmd.id,
          label: '/' + cmd.id,
          description: cmd.description,
          examples: []
        }));
      }
    } catch (e) {
      console.error('Failed to load registry:', e);
      commands = [];
    }
    
    // Рендерим список
    const listEl = overlay.querySelector('.command-list');
    let html = '';
    
    for (const cmd of commands) {
      const examplesBlock = cmd.examples && cmd.examples.length > 0
        ? `<div class="examples">${cmd.examples.map(ex => '• ' + ex).join('<br>')}</div>`
        : '';
      
      html += `
        <div class="command-item" data-cmd="${cmd.id}">
          <div class="cmd-header">
            <code>${cmd.label || '/' + cmd.id}</code>
            ${(cmd.aliases && cmd.aliases.length > 0) ? `<small>алиасы: ${cmd.aliases.map(a => '/' + a).join(', ')}</small>` : ''}
          </div>
          <div class="desc">${cmd.description}</div>
          ${examplesBlock}
        </div>
      `;
    }
    
    listEl.innerHTML = html;
    
    // Показываем
    overlay.classList.add('visible');
  }
  
  function close() {
    if (overlayEl) {
      overlayEl.classList.remove('visible');
    }
  }
  
  // Экспорт
  window.AMTHelp = {
    show,
    close,
    createOverlay
  };
})();
