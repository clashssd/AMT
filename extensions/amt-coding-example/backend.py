"""AMT coding extension example backend.

This extension demonstrates how a coding extension can register hooks into
the backend extension context.  It is intentionally minimal and safe: it does
not perform file writes or command execution.
"""


def init(ctx):
    # ctx['tools'] is the legacy ToolSandbox; coding extensions should prefer
    # CodingToolset for project-scoped operations.
    tools = ctx.get("tools")
    if tools is None:
        raise RuntimeError("amt-coding-example: ctx['tools'] is missing")
    # Register a no-op marker so the extension is observable in logs.
    import logging
    logging.getLogger("amt-chat.extensions").info("amt-coding-example backend initialized")
