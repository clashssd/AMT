/**
 * frontend/js/pages/logsDashboard.js
 * 
 * Dashboard для просмотра логов в реальном времени.
 * Фильтры, виджеты, таблица событий.
 */

class LogsDashboard {
  constructor() {
    this.events = [];
    this.filters = {
      level: [],
      module: 'all',
      timeRange: '24h',
      search: ''
    };
    this.page = 1;
    this.pageSize = 50;
  }
  
  async load() {
    this.element = document.querySelector('[data-page="logs"] .page-content');
    if (!this.element) return;
    
    this.render();
    
    // Загружаем данные
    await this.fetchEvents();
    
    // Автообновление каждые 5 секунд
    this.pollingInterval = setInterval(() => {
      this.fetchEvents();
    }, 5000);
  }
  
  render() {
    this.element.innerHTML = `
      <div class="logs-dashboard">
        <div class="logs-header">
          <h2>Логи и Мониторинг</h2>
          <div class="logs-actions">
            <button id="refreshLogs" class="btn-secondary">Обновить</button>
            <label class="autorefresh-label">
              <input type="checkbox" id="autorefresh" checked> 
              Автообновление
            </label>
          </div>
        </div>
        
        <!-- Виджеты -->
        <div class="logs-widgets">
          <div class="widget">
            <div class="widget-value" id="totalEvents">0</div>
            <div class="widget-label">Событий за 24ч</div>
          </div>
          <div class="widget">
            <div class="widget-value" id="errorCount">0</div>
            <div class="widget-label">Ошибок за 24ч</div>
          </div>
          <div class="widget">
            <div class="widget-value" id="avgResponseTime">0ms</div>
            <div class="widget-label">Среднее время запроса</div>
          </div>
          <div class="widget">
            <div class="widget-value" id="activeMcp">0</div>
            <div class="widget-label">Активных MCP</div>
          </div>
        </div>
        
        <!-- Фильтры -->
        <div class="logs-filters">
          <div class="filter-group">
            <span class="filter-label">Уровень:</span>
            <label><input type="checkbox" data-level="debug"> DEBUG</label>
            <label><input type="checkbox" data-level="info" checked> INFO</label>
            <label><input type="checkbox" data-level="warn" checked> WARN</label>
            <label><input type="checkbox" data-level="error" checked> ERROR</label>
          </div>
          
          <div class="filter-group">
            <span class="filter-label">Модуль:</span>
            <select id="moduleFilter">
              <option value="all">Все</option>
              <option value="api">API</option>
              <option value="mcp">MCP</option>
              <option value="ai">AI Engine</option>
              <option value="orchestrator">Оркестратор</option>
            </select>
          </div>
          
          <div class="filter-group">
            <span class="filter-label">Время:</span>
            <select id="timeRangeFilter">
              <option value="1h">1 час</option>
              <option value="24h" selected>24 часа</option>
              <option value="7d">7 дней</option>
            </select>
          </div>
          
          <div class="filter-group">
            <input type="text" id="searchFilter" placeholder="Поиск по тексту...">
          </div>
        </div>
        
        <!-- Таблица -->
        <div class="logs-table-container">
          <table class="logs-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Уровень</th>
                <th>Модуль</th>
                <th>Событие</th>
                <th>Сообщение</th>
                <th>Длительность</th>
                <th>Данные</th>
              </tr>
            </thead>
            <tbody id="logsTableBody">
              <tr class="loading"><td colspan="7">Загрузка...</td></tr>
            </tbody>
          </table>
        </div>
        
        <!-- Пагинация -->
        <div class="logs-pagination">
          <button id="prevPage" class="btn-secondary">←</button>
          <span id="pageInfo">Стр. 1</span>
          <button id="nextPage" class="btn-secondary">→</button>
        </div>
      </div>
    `;
    
    this._bindEvents();
  }
  
  _bindEvents() {
    // Обновление
    document.getElementById('refreshLogs')?.addEventListener('click', () => {
      this.fetchEvents();
    });

    // Автообновление
    document.getElementById('autorefresh')?.addEventListener('change', (e) => {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
      }
      if (e.target.checked) {
        this.pollingInterval = setInterval(() => this.fetchEvents(), 5000);
      }
    });

    // Coding dashboard filter chip
    document.querySelector('[data-dashfilter="coding"]')?.addEventListener('click', (e) => {
      document.querySelectorAll('[data-dashfilter]').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      this.filters.module = 'coding';
      this._renderCodingDash();
    });
    
    // Фильтры по уровню
    document.querySelectorAll('[data-level]').forEach(checkbox => {
      checkbox.addEventListener('change', () => {
        this.filters.level = Array.from(
          document.querySelectorAll('[data-level]:checked')
        ).map(cb => cb.dataset.level);
        this.fetchEvents();
      });
    });
    
    // Фильтр по модулю
    document.getElementById('moduleFilter')?.addEventListener('change', (e) => {
      this.filters.module = e.target.value;
      this.fetchEvents();
    });
    
    // Фильтр по времени
    document.getElementById('timeRangeFilter')?.addEventListener('change', (e) => {
      this.filters.timeRange = e.target.value;
      this.fetchEvents();
    });
    
    // Поиск
    document.getElementById('searchFilter')?.addEventListener('input', (e) => {
      this.filters.search = e.target.value;
      this.fetchEvents();
    });
    
    // Пагинация
    document.getElementById('prevPage')?.addEventListener('click', () => {
      if (this.page > 1) {
        this.page--;
        this.fetchEvents();
      }
    });
    
    document.getElementById('nextPage')?.addEventListener('click', () => {
      this.page++;
      this.fetchEvents();
    });
  }
  
  async fetchEvents() {
    const params = new URLSearchParams();
    
    // Уровень (endpoint принимает один level, но у нас checkbox'и — берём первый)
    if (this.filters.level.length > 0) {
      params.set('level', this.filters.level[0]);
    }
    // Модуль → category
    if (this.filters.module !== 'all') {
      params.set('category', this.filters.module);
    }
    // Лимит (упрощённая пагинация — берём последние N)
    params.set('limit', this.pageSize * this.page);
    
    try {
      const response = await fetch(`/api/logs/structured?${params.toString()}`);
      const data = await response.json();
      
      this.events = data.events || [];
      this.updateWidgets(data.dashboard || {});
      this._codingDashData = data.dashboard?.coding_dashboard || {};
      this._renderCodingDash();
      this.renderTable();
    } catch (error) {
      console.error('Failed to fetch logs:', error);
      document.getElementById('logsTableBody').innerHTML = `
        <tr class="error"><td colspan="7">Ошибка загрузки логов</td></tr>
      `;
    }
  }
  
  updateWidgets(dashboard) {
    const totalEl = document.getElementById('totalEvents');
    const errorEl = document.getElementById('errorCount');
    const avgTimeEl = document.getElementById('avgResponseTime');
    const mcpEl = document.getElementById('activeMcp');
    
    if (totalEl) totalEl.textContent = dashboard.total_events || 0;
    if (errorEl) {
      const byLevel = dashboard.by_level || {};
      errorEl.textContent = byLevel.ERROR || byLevel.error || 0;
    }
    if (avgTimeEl) {
      // Среднее время из ai_call событий
      const events = this.events || [];
      const aiCalls = events.filter(e => e.category === 'ai_call' && e.duration_ms);
      if (aiCalls.length > 0) {
        const avg = aiCalls.reduce((sum, e) => sum + e.duration_ms, 0) / aiCalls.length;
        avgTimeEl.textContent = Math.round(avg) + 'ms';
      } else {
        avgTimeEl.textContent = '—';
      }
    }
    if (mcpEl) {
      const byCategory = dashboard.by_category || {};
      mcpEl.textContent = byCategory.mcp_call || 0;
    }
  }
  
  _renderCodingDash() {
    const wrap = document.getElementById('codingDash');
    if (!wrap) return;
    const data = this._codingDashData || {};
    if (!data.coding_tool_calls && !data.coding_approvals && !data.coding_mcp_calls) {
      wrap.classList.add('hidden');
      return;
    }
    wrap.classList.remove('hidden');
    const stats = document.getElementById('codingDashStats');
    if (stats) {
      stats.innerHTML = `
        <div class="widget"><div class="widget-value">${data.coding_tool_calls || 0}</div><div class="widget-label">Coding tool calls</div></div>
        <div class="widget"><div class="widget-value">${data.coding_approvals || 0}</div><div class="widget-label">Approvals</div></div>
        <div class="widget"><div class="widget-value">${data.coding_mcp_calls || 0}</div><div class="widget-label">Coding MCP</div></div>
        <div class="widget"><div class="widget-value">${data.coding_errors || 0}</div><div class="widget-label">Errors</div></div>
      `;
    }
    const recent = document.getElementById('codingDashRecent');
    if (recent) {
      const events = data.recent_coding_events || [];
      recent.innerHTML = events.length
        ? events.map((e) => `<div class="coding-dash-row"><span>${e.timestamp?.slice(11,19) || ''}</span><code>${e.category}</code><span>${e.message || ''}</span></div>`).join('')
        : '<div class="coding-dash-empty">Нет coding-событий</div>';
    }
  }

  renderTable() {
    const tbody = document.getElementById('logsTableBody');
    if (!tbody) return;
    
    if (this.events.length === 0) {
      tbody.innerHTML = '<tr class="empty"><td colspan="7">Нет событий</td></tr>';
      return;
    }
    
    tbody.innerHTML = this.events.map(event => {
      const levelClass = {
        'DEBUG': 'level-debug',
        'INFO': 'level-info',
        'WARN': 'level-warn',
        'ERROR': 'level-error'
      }[event.level] || 'level-info';
      
      const timestamp = new Date(event.timestamp);
      const timeStr = timestamp.toLocaleString();
      
      const duration = event.duration_ms 
        ? `${Math.round(event.duration_ms)}ms` 
        : '';
      
      const dataJson = event.metadata && Object.keys(event.metadata).length > 0
        ? `<button class="toggle-data" data-json='${JSON.stringify(event.metadata)}'>JSON</button>`
        : '';
      
      return `
        <tr>
          <td>${timeStr}</td>
          <td><span class="level-badge ${levelClass}">${(event.level || 'INFO').toUpperCase()}</span></td>
          <td>${event.category || 'general'}</td>
          <td><code>${event.category || 'event'}</code></td>
          <td>${event.message || ''}</td>
          <td>${duration}</td>
          <td>${dataJson}</td>
        </tr>
      `;
    }).join('');
    
    // Toggle data buttons
    tbody.querySelectorAll('.toggle-data').forEach(btn => {
      btn.addEventListener('click', () => {
        const json = JSON.parse(btn.dataset.json);
        alert(JSON.stringify(json, null, 2));
      });
    });
    
    // Update pagination
    const pageInfo = document.getElementById('pageInfo');
    if (pageInfo) {
      pageInfo.textContent = `Стр. ${this.page}`;
    }
  }
  
  destroy() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }
  }
}

// Экспорт (vanilla JS — window, не export)
window.LogsDashboard = LogsDashboard;
window.logsDashboard = new LogsDashboard();

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
  // Когда переходим на страницу логов
  const observer = new MutationObserver(() => {
    const logsPage = document.querySelector('[data-page="logs"]');
    if (logsPage && logsPage.classList.contains('active')) {
      logsDashboard.load();
    }
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class']
  });
});
