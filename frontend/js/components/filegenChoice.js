/**
 * filegenChoice.js — выбор способа генерации файла (базовая модель vs MCP)
 */
(function() {
  'use strict';
  
  let modalEl = null;
  
  function createModal() {
    if (modalEl) return modalEl;
    
    modalEl = document.createElement('div');
    modalEl.id = 'filegen-choice-modal';
    modalEl.className = 'filegen-choice-modal';
    modalEl.innerHTML = `
      <div class="choice-dialog">
        <h3>Как сгенерировать файл?</h3>
        <div class="choice-list">
          <button class="choice-btn" data-choice="base">
            <strong>Базовая модель</strong>
            <small>Медленнее, но без ограничений. Работает даже без MCP.</small>
          </button>
          <button class="choice-btn" data-choice="mcp">
            <strong>MCP Writer</strong>
            <small>Быстрее, с валидацией. Нужен подключённый MCP-сервер.</small>
          </button>
        </div>
        <div class="modal-actions">
          <button class="btn secondary cancel">Отмена</button>
        </div>
      </div>
    `;
    
    document.body.appendChild(modalEl);
    
    // Обработчики
    modalEl.querySelector('.cancel').addEventListener('click', cancel);
    modalEl.addEventListener('click', (e) => {
      if (e.target === modalEl) cancel();
    });
    
    modalEl.querySelectorAll('.choice-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const choice = btn.dataset.choice;
        resolve(choice);
        cancel();
      });
    });
    
    return modalEl;
  }
  
  let resolveCallback = null;
  
  function show() {
    return new Promise((resolve) => {
      resolveCallback = resolve;
      const modal = createModal();
      modal.classList.add('visible');
    });
  }
  
  function cancel() {
    if (modalEl) {
      modalEl.classList.remove('visible');
      if (resolveCallback) {
        resolveCallback(null);
        resolveCallback = null;
      }
    }
  }
  
  function resolve(choice) {
    if (resolveCallback) {
      resolveCallback(choice);
      resolveCallback = null;
    }
  }
  
  // Экспорт
  window.AMTFileGenChoice = {
    show,
    cancel
  };
})();
