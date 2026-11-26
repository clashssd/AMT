"""
command_engine.py — парсинг и выполнение slash-команд
"""
import json
import os
from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any
from pathlib import Path

# Загружаем реестр команд — работает и в dev, и в PyInstaller-бандле
def _find_registry_path() -> Path:
    """Ищет command_registry.json в dev и packaged-окружениях."""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller: _internal/ каталог рядом с exe
        base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent / '_internal'))
        candidate = base / 'command_registry.json'
        if candidate.exists():
            return candidate
    # Dev: рядом с модулем
    candidate = Path(__file__).parent / 'command_registry.json'
    if candidate.exists():
        return candidate
    # Fallback: в текущей папке
    candidate = Path.cwd() / 'command_registry.json'
    if candidate.exists():
        return candidate
    raise FileNotFoundError('command_registry.json not found in any known location')

COMMAND_REGISTRY_PATH = _find_registry_path()

def load_command_registry() -> Dict[str, Any]:
    """Загружает реестр команд из JSON."""
    with open(COMMAND_REGISTRY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

REGISTRY = load_command_registry()

@dataclass
class ParsedCommand:
    """Разобранная команда."""
    id: str
    args: Dict[str, Any] = field(default_factory=dict)

@dataclass  
class CommandContext:
    """Контекст выполнения команды (выбрасывается после запроса)."""
    system_prompt_fragments: List[str] = field(default_factory=list)
    enabled_tools: Set[str] = field(default_factory=set)
    enabled_mcp: Set[str] = field(default_factory=set)
    enabled_agents: List[str] = field(default_factory=list)
    enable_memory: bool = False
    enable_orchestrator: bool = False
    enable_jailbreak: bool = False
    
    def add_fragment(self, fragment: str):
        self.system_prompt_fragments.append(fragment)
    
    def add_tools(self, tools: List[str]):
        self.enabled_tools.update(tools)
    
    def add_mcp(self, servers: List[str]):
        self.enabled_mcp.update(servers)
    
    def set_tool(self, tool: str):
        self.enabled_tools.add(tool)

class CommandParser:
    """Парсит строку команд (например, '/rag + /jailbreak сделай X')."""
    
    def __init__(self, registry: Dict[str, Any]):
        self.registry = registry
        self.commands_by_id = {c['id']: c for c in registry['commands']}
        self.aliases_map = {}
        for cmd in registry['commands']:
            self.aliases_map[cmd['id']] = cmd['id']
            for alias in cmd.get('aliases', []):
                self.aliases_map[alias.lower()] = cmd['id']
    
    def parse(self, input_text: str) -> tuple[List[ParsedCommand], str]:
        """
        Парсит строку и возвращает (команды, остаток_текста).
        
        Формат: команды — это /name (опц. аргументы для gen/agent), разделённые '+'.
        Всё что остаётся после последней команды — текст пользователя.
        
        Примеры:
          '/rag + /jailbreak сделай X' -> ([rag, jailbreak], 'сделай X')
          '/rag сделай X' -> ([rag], 'сделай X')
          '/gen file xlsx таблица' -> ([gen{type:file,filetype:xlsx}], 'таблица')
          '/gen photo закат' -> ([gen{type:photo}], 'закат')
        """
        commands = []
        
        # Разбиваем на секции по '+'. Каждая секция может быть:
        #  - командой: '/name' или '/name args'
        #  - текстом (без '/' в начале)
        
        sections = input_text.split('+')
        user_message = ''
        
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            
            # Если секция НЕ начинается с '/' — это текст пользователя
            if not section.startswith('/'):
                user_message = section
                break
            
            # Секция начинается с '/' — это команда
            # Читаем имя команды (до пробела)
            j = 1
            while j < len(section) and section[j] not in ' \t':
                j += 1
            
            cmd_name = section[1:j].lower()
            args_str = section[j:].strip()
            
            # Определяем ID (через алиасы)
            cmd_id = self.aliases_map.get(cmd_name, cmd_name)
            
            # Парсим аргументы и текст
            # Для /gen: первый токен — тип, второй — формат (для file), остаток — промпт
            # Для /agent: первый токен — имя агента, остаток — текст
            # Для остальных: всё после имени команды — текст пользователя
            args = {}
            text_part = ''
            
            if cmd_name == 'gen':
                args = self._parse_gen_args(args_str)
                # Генерация: текст уже внутри args (prompt/filetype/description)
                text_part = args.get('prompt', '') or args.get('description', '')
            elif cmd_name == 'agent':
                if args_str:
                    parts = args_str.split(maxsplit=1)
                    args['name'] = parts[0]
                    text_part = parts[1] if len(parts) > 1 else ''
            else:
                # Обычные команды: всё что после имени — текст пользователя
                text_part = args_str
            
            if cmd_id in self.commands_by_id:
                commands.append(ParsedCommand(id=cmd_id, args=args))
                # Обновляем user_message (последний текст побеждает)
                if text_part:
                    user_message = text_part
        
        return commands, user_message
    
    def _parse_gen_args(self, args_str: str) -> Dict[str, Any]:
        """Парсит аргументы /gen."""
        args = {}
        parts = args_str.split(maxsplit=1)
        
        if not parts:
            return args
        
        # Первый токен — ��ип
        gen_type = parts[0].lower()
        args['type'] = gen_type
        
        if len(parts) > 1:
            rest = parts[1]
            
            # Если тип file — второй токен это формат
            if gen_type == 'file':
                file_parts = rest.split(maxsplit=1)
                if file_parts:
                    args['filetype'] = file_parts[0].lower()
                    if len(file_parts) > 1:
                        args['description'] = file_parts[1]
            
            # Если combo — парсим список
            elif gen_type == 'combo':
                # Формат: "photo:закат,video:волны,audio:рассказ"
                items = rest.split(',')
                args['items'] = []
                for item in items:
                    if ':' in item:
                        item_type, item_prompt = item.split(':', 1)
                        args['items'].append(f"{item_type.strip()}:{item_prompt.strip()}")
            
            # Иначе — просто промпт
            else:
                args['prompt'] = rest
        
        return args

def build_context(commands: List[ParsedCommand], registry: Dict[str, Any]) -> CommandContext:
    """Строит контекст выполнения из списка команд."""
    commands_by_id = {c['id']: c for c in registry['commands']}
    ctx = CommandContext()
    
    for cmd in commands:
        cmd_def = commands_by_id.get(cmd.id)
        if not cmd_def:
            continue
        
        effects = cmd_def.get('effects', {})
        
        # Фрагменты промпта
        if 'system_prompt_fragment' in effects:
            fragment = effects['system_prompt_fragment']
            # Подставляем аргументы
            if cmd.args.get('name'):
                fragment = fragment.replace('{agent_name}', cmd.args['name'])
            ctx.add_fragment(fragment)
        
        # Инструменты
        if 'enable_tools' in effects:
            ctx.add_tools(effects['enable_tools'])
        
        # MCP-серверы
        if 'enable_mcp' in effects:
            ctx.add_mcp(effects['enable_mcp'])
        
        # Агент
        if 'enable_agent' in effects:
            ctx.enabled_agents.append(effects['enable_agent'])
        
        # Флаги
        if effects.get('enable_memory'):
            ctx.enable_memory = True
        if effects.get('enable_orchestrator'):
            ctx.enable_orchestrator = True
        if effects.get('enable_jailbreak'):
            ctx.enable_jailbreak = True
        
        # Специальная обработка для /gen
        if cmd.id == 'gen':
            _handle_gen_specific(cmd.args, ctx)
    
    return ctx

def _handle_gen_specific(args: Dict[str, Any], ctx: CommandContext):
    """Специальная обработка для /gen."""
    gen_type = args.get('type', 'image')
    filetype = args.get('filetype', '')
    reference = args.get('reference', '')
    
    if gen_type in ('photo', 'image'):
        ctx.add_mcp(['media'])
        if reference:
            ctx.set_tool('generate_image_from_reference')
            ctx.add_fragment(f" (по образцу: {reference})")
        else:
            ctx.set_tool('generate_image')
    
    elif gen_type == 'video':
        ctx.add_mcp(['media'])
        if reference:
            ctx.set_tool('generate_video_from_reference')
        else:
            ctx.set_tool('generate_video')
    
    elif gen_type == 'audio':
        ctx.add_mcp(['media'])
        ctx.set_tool('generate_audio')
    
    elif gen_type == 'file':
        mode = args.get('mode', 'mcp')  # 'mcp' (default) or 'base'
        if mode == 'mcp':
            ctx.add_mcp(['writer'])
            tool_map = {
                'xlsx': 'create_office',
                'docx': 'create_office',
                'pptx': 'create_office',
                'pdf': 'create_pdf',
                'csv': 'create_data',
                'json': 'create_data',
                'yaml': 'create_data',
                'py': 'create_code',
                'js': 'create_code',
                'ts': 'create_code',
                'html': 'create_code',
                'css': 'create_code',
                'sh': 'create_code',
                'bat': 'create_code',
                'md': 'create_text',
                'txt': 'create_text'
            }
            ctx.set_tool(tool_map.get(filetype, 'create_text'))
        else:
            # Base mode: use built-in tools without MCP Writer
            ctx.set_tool('create_text')
            ctx.add_fragment(f"Generate a {filetype or 'text'} file using built-in tools.")
    
    elif gen_type == 'combo':
        # Активируем все нужные MCP
        ctx.add_mcp(['media', 'writer'])
        ctx.add_fragment("Генерируй несколько типов контента разом")

def execute_command_request(user_message: str, history: list, settings: dict, mcp_manager, ai_engine) -> str:
    """
    Выполняет запрос со slash-командами.
    
    1. Парсит команды
    2. Строит контекст
    3. Включает MCP-серверы
    4. Выполняет запрос
    5. Выбрасывает контекст
    """
    parser = CommandParser(REGISTRY)
    commands, remaining_text = parser.parse(user_message)
    
    # Если нет команд — обычный запрос
    if not commands:
        return ai_engine.call_api(remaining_text, history, settings)
    
    # Строим контекст
    ctx = build_context(commands, REGISTRY)
    
    # Включаем MCP-серверы
    for server_id in ctx.enabled_mcp:
        try:
            mcp_manager.ensure_connected(server_id)
        except Exception as e:
            print(f"Failed to connect MCP {server_id}: {e}")
    
    # Добавляем системный промпт
    system_prompt = settings.get('system_prompt', '')
    if ctx.system_prompt_fragments:
        system_prompt += '\n' + '\n'.join(ctx.system_prompt_fragments)
    
    # Выполняем запрос
    result = ai_engine.call_api(
        remaining_text,
        history,
        settings,
        extra_system_prompt=system_prompt,
        enabled_tools=list(ctx.enabled_tools) if ctx.enabled_tools else None
    )
    
    return result
