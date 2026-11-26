/**
 * commands.js — парсер slash-команд на фронтенде
 */
(function() {
  'use strict';
  
  const COMMANDS = {};
  
  // Кэшированный реестр
  let commandRegistry = null;
  
  async function loadCommandRegistry() {
    if (commandRegistry) return commandRegistry;
    
    try {
      const response = await fetch('/api/command-registry');
      commandRegistry = await response.json();
      return commandRegistry;
    } catch (e) {
      console.error('Failed to load command registry:', e);
      return { commands: [] };
    }
  }
  
  /**
   * Парсит строку команд
   * @param {string} input - строка с командами
   * @returns {{commands: Array, text: string}}
   */
  function parseCommands(input) {
    const commands = [];
    let remaining = input;
    
    // Ищем все /command
    while (remaining.includes('/')) {
      const slashPos = remaining.indexOf('/');
      const before = remaining.substring(0, slashPos);
      const after = remaining.substring(slashPos + 1);
      
      // Читаем имя команды
      let cmdName = '';
      let i = 0;
      while (i < after.length && !/\s/.test(after[i])) {
        cmdName += after[i];
        i++;
      }
      
      // Извлекаем аргументы
      let args = {};
      if (i < after.length) {
        const argsStr = after.substring(i).trim();
        const argsWithoutPlus = argsStr.split('+')[0].trim();
        
        if (cmdName === 'gen') {
          args = parseGenArgs(argsWithoutPlus);
        } else if (cmdName === 'agent') {
          const name = argsWithoutPlus.split(' ')[0];
          if (name) args.name = name;
        } else if (cmdName === 'file') {
          const filetype = argsWithoutPlus.split(' ')[0];
          if (filetype) args.filetype = filetype.toLowerCase();
        }
      }
      
      commands.push({ id: cmdName.toLowerCase(), args });
      
      // Удаляем команду
      remaining = before + (i < after.length ? after.substring(i) : '');
      if (remaining && remaining[0] === '+') {
        remaining = remaining.substring(1).trim();
      }
    }
    
    return { commands, text: remaining.trim() };
  }
  
  /**
   * Парсит аргументы /gen
   */
  function parseGenArgs(argsStr) {
    const args = {};
    const parts = argsStr.split(/\s+/).filter(Boolean);
    
    if (parts.length === 0) return args;
    
    const genType = parts[0].toLowerCase();
    args.type = genType;
    
    if (parts.length > 1) {
      const rest = parts.slice(1).join(' ');
      
      if (genType === 'file') {
        const fileParts = rest.split(/\s+/).filter(Boolean);
        if (fileParts.length > 0) {
          args.filetype = fileParts[0].toLowerCase();
          if (fileParts.length > 1) {
            args.description = fileParts.slice(1).join(' ');
          }
        }
      } else if (genType === 'combo') {
        const items = rest.split(',');
        args.items = items.map(item => {
          const [type, prompt] = item.split(':');
          return `${type?.trim() || ''}:${prompt?.trim() || ''}`;
        });
      } else {
        args.prompt = rest;
      }
    }
    
    return args;
  }
  
  /**
   * Показывает подсказки при вводе /
   */
  async function showCommandSuggestions(input) {
    if (!input.startsWith('/')) return [];
    
    const registry = await loadCommandRegistry();
    const suggestions = [];
    
    // Ищем подходящие команды
    for (const cmd of registry.commands) {
      const cmdLower = cmd.id.toLowerCase();
      const aliases = (cmd.aliases || []).map(a => a.toLowerCase());
      
      // Если введён / или /имя — подсказываем
      if (input.length === 1 || cmdLower.startsWith(input.substring(1).toLowerCase())) {
        suggestions.push({
          id: cmd.id,
          label: `/${cmd.id}`,
          description: cmd.description,
          aliases
        });
      }
    }
    
    return suggestions;
  }
  
  /**
   * Генерирует список команд для help
   */
  async function getCommandHelp() {
    const registry = await loadCommandRegistry();
    return registry.commands.map(cmd => ({
      id: cmd.id,
      label: `/${cmd.id}`,
      description: cmd.description,
      syntax: cmd.requires_args ? `/${cmd.id} <аргументы>` : `/${cmd.id}`,
      examples: generateExamples(cmd)
    }));
  }
  
  /**
   * Генерирует примеры для команды
   */
  function generateExamples(cmd) {
    switch(cmd.id) {
      case 'rag':
        return ['Сделай X используя базу знаний', 'Найди в моих документах про Y'];
      case 'agent':
        return ['/agent web найди в интернете', '/agent analyst проанализируй'];
      case 'jailbreak':
        return ['Напиши код RAT (без фильтров)'];
      case 'gen':
        return [
          '/gen photo закат',
          '/gen video кот играет',
          '/gen file xlsx таблица',
          '/gen file py скрипт',
          '/gen combo photo:закат,video:волны'
        ];
      case 'nav_settings':
        return ['Перейти в настройки'];
      default:
        return [cmd.description];
    }
  }
  
  // Навигация на страницу — используем showPage из main.js (обновляет sidebar, URL, page-specific init)
  function navigateTo(page) {
    if (window.showPage) {
      window.showPage(page);
    }
  }
  
  // Показать help overlay
  function showHelp() {
    if (window.AMTHelp) window.AMTHelp.show();
  }
  
  // Переключить toggle в композере
  function toggleAgent(agentType) {
    const toggleMap = {
      'web': 'webAgentToggle',
      'jailbreak': 'jailbreakToggle'
    };
    const btnId = toggleMap[agentType];
    if (btnId) {
      const btn = document.getElementById(btnId);
      if (btn) btn.click();
    }
  }
  
  function toggleJailbreak() {
    toggleAgent('jailbreak');
  }
  
  // Быстрая генерация
  function quickGen(type) {
    const input = document.getElementById('messageInput');
    if (!input) return;
    
    if (type === 'file') {
      // Для файлов — показываем выбор (базовая модель vs MCP Writer)
      // если MCP доступен, иначе просто вставляем команду
      const prefix = '/gen file ';
      input.value = prefix;
      input.focus();
    } else {
      const prefix = '/gen ';
      input.value = prefix;
      input.focus();
    }
  }
  
  // ---- Кодинг-команды (запускают действия на странице «Код») ----

  function currentCodingChat() {
    return (window.chats || []).find(c => c.id === window.currentChatId) || null;
  }

  function setCodingProjectRoot(root) {
    const chat = currentCodingChat();
    if (!chat || !root) return;
    chat.projectRoot = root;
    if (window.saveChats) window.saveChats();
    const input = document.getElementById('codingProjectRoot');
    if (input) input.value = root;
    if (window.rebuildChatMeta) window.rebuildChatMeta();
  }

  function codingSessionAction(action, payload) {
    const base = '/api/sessions/coding';
    const method = action === 'list' ? 'GET' : 'POST';
    const body = action === 'list' ? null : JSON.stringify(payload || {});
    return fetch(base, { method, body, headers: body ? {'Content-Type': 'application/json'} : undefined })
      .then(r => r.json());
  }

  function appendSystemMessage(text) {
    if (!text) return;
    const chat = currentCodingChat();
    if (chat) {
      chat.messages.push({ role: 'system', content: text, ts: Date.now() });
      if (window.saveChats) window.saveChats();
    }
    const host = document.getElementById('chatMessages');
    if (!host) return;
    const el = document.createElement('div');
    el.className = 'message bot';
    el.innerHTML = `<div class="message-content"><pre style="white-space:pre-wrap;margin:0;">${(window.escapeHtml || (s => s))(text)}</pre></div>`;
    host.appendChild(el);
    host.scrollTop = host.scrollHeight;
  }

  async function runCodingTool(tool, args = {}) {
    const chat = currentCodingChat();
    if (!chat || !chat.projectRoot) {
      appendSystemMessage('Сначала укажите проект: /code_project C:\\path');
      return;
    }
    const res = await fetch('/api/coding/tool', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ root: chat.projectRoot, tool, args }),
    }).then(r => r.json()).catch(err => ({ status: 'error', error: String(err) }));
    const preview = res.output || res.error || JSON.stringify(res);
    appendSystemMessage(`/${tool}: ${preview}`.trim());
  }

  async function executeCodingCommand(command, args, raw) {
    const chat = currentCodingChat();
    const [sub, ...rest] = args;
    const restStr = rest.join(' ');
    switch (command) {
      case 'code':
        navigateTo('code');
        break;
      case 'code_project':
        if (restStr) setCodingProjectRoot(restStr);
        else if (window.amtPrompt) await window.amtPrompt('Укажи рабочую директорию проекта', 'C:\\Projects');
        break;
      case 'code_session':
        if (sub === 'list') {
          const data = await codingSessionAction('list');
          if (window.appendChatMessage) window.appendChatMessage('system', JSON.stringify(data.coding_sessions || []));
        } else if (sub === 'create') {
          await codingSessionAction('create', { name: restStr || 'coding', root: chat?.projectRoot || '' });
        } else if (sub === 'continue') {
          await codingSessionAction('continue', { id: restStr, base_chat_id: chat?.id || '' });
        } else if (sub === 'duplicate') {
          await codingSessionAction('duplicate', { id: restStr });
        } else if (sub === 'delete') {
          await codingSessionAction('delete', { id: restStr });
        }
        break;
      case 'code_git':
        await runCodingTool(sub || 'git_status');
        break;
      case 'code_test': {
        const extraArgs = restStr ? restStr.split(/\s+/) : [];
        await runCodingTool('run_tests', { extra_args: extraArgs });
        break;
      }
      case 'code_mcp': {
        const res = await fetch('/api/mcp/coding/recommended').then(r => r.json()).catch(() => ({ items: [] }));
        const lines = (res.items || []).map(item => `• ${item.id}: ${item.name} — ${item.note || ''}`);
        appendSystemMessage(`Рекомендуемые coding MCP-серверы:\n${lines.join('\n')}\nУстановить: /code_mcp install <id>`);
        if (sub === 'install' && restStr) {
          const installRes = await fetch(`/api/mcp/coding/recommended/${encodeURIComponent(restStr)}/install`, { method: 'POST' }).then(r => r.json()).catch(() => ({ ok: false }));
          appendSystemMessage(`MCP install ${restStr}: ${installRes.ok ? (installRes.created ? 'created' : 'already exists') : 'error'}`);
        }
        break;
      }
      case 'code_permissions':
        if (window.amtPrompt) await window.amtPrompt('Разрешения: allow|ask|deny', 'ask');
        break;
      case 'code_orchestrator': {
        if (!chat || !chat.projectRoot) {
          appendSystemMessage('Сначала укажите проект: /code_project C:\\path');
          break;
        }
        const goal = restStr || (await window.amtPrompt?.('Задача для кодинг-оркестратора', 'исправь баг и запусти тесты'));
        if (!goal) break;
        appendSystemMessage('Запускаю кодинг-оркестратор: planner → coder → reviewer…');
        const res = await fetch('/api/coding/orchestrator', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ root: chat.projectRoot, goal, policy: chat.toolPolicy || [] }),
        }).then(r => r.json()).catch(err => ({ status: 'error', error: String(err) }));
        const run = res.run || res;
        appendSystemMessage(`Оркестратор завершён: ${run.status || res.status || 'error'}. Изменено файлов: ${(run.files_changed || []).length}. Раундов: ${run.rounds || 0}.`);
        break;
      }
      default:
        break;
    }
  }

  // Экспорт (два имени для совместимости)
  window.AMTCommands = {
    parseCommands,
    showCommandSuggestions,
    getCommandHelp,
    loadCommandRegistry,
    navigateTo,
    showHelp,
    toggleAgent,
    toggleJailbreak,
    quickGen,
    setCodingProjectRoot,
    codingSessionAction,
    executeCodingCommand,
    currentCodingChat,
    runCodingTool,
    appendSystemMessage
  };
  window.AMTCmds = window.AMTCommands;
})();
