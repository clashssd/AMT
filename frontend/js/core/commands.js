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
        if (window.appendChatMessage) {
          window.appendChatMessage('system', `Git: ${sub || 'status'} ${restStr}`.trim());
        }
        break;
      case 'code_test':
        if (window.appendChatMessage) window.appendChatMessage('system', 'Запуск тестов проекта…');
        break;
      case 'code_mcp':
        if (window.amtPrompt) await window.amtPrompt('MCP-серверы для кодинг-чата (через запятую)', 'amt-coding');
        break;
      case 'code_permissions':
        if (window.amtPrompt) await window.amtPrompt('Разрешения: allow|ask|deny', 'ask');
        break;
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
    currentCodingChat
  };
  window.AMTCmds = window.AMTCommands;
})();
