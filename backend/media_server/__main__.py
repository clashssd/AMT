# backend/media_server/__main__.py
"""Entry point: `python -m media_server` (used by AMT's media preset as a STDIO MCP server)."""
from .server import main

main()
