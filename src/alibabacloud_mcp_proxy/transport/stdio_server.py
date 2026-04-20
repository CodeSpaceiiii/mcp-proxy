from __future__ import annotations

from mcp.server import Server
from mcp.server.stdio import stdio_server


async def run_stdio_server(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
