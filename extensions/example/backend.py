"""Пример backend-расширения.

Добавляет endpoint /api/ext/example и регистрирует его в приложении.
Функция init(ctx) вызывается при загрузке расширений.
"""
import json


def init(ctx):
    """ctx = {tools, extensions_dir, ...}. Регистрируем свой endpoint."""
    # ctx['app'] не передаётся намеренно: расширения не трогают корневой app,
    # чтобы не ломать изоляцию. Вместо этого backend-расширение может
    # регистрировать свои функции в ToolSandbox через ctx['tools'].
    #
    # Пример: регистрируем собственную «команду» (инструмент) в песочнице.
    tools = ctx.get("tools")
    if tools and hasattr(tools, "register_custom_tool"):
        tools.register_custom_tool("example_ping", lambda: {"pong": True})
