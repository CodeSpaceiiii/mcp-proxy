from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl

from aliyun_mcp_proxy.config import AliyunProxyConfig


@dataclass(slots=True)
class StreamableHttpConnection:
    session: ClientSession
    exit_stack: AsyncExitStack

    async def list_prompts(self) -> types.ListPromptsResult:
        return await self.session.list_prompts()

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        return await self.session.get_prompt(name, arguments)

    async def list_resources(self) -> types.ListResourcesResult:
        return await self.session.list_resources()

    async def read_resource(self, uri: AnyUrl) -> types.ReadResourceResult:
        return await self.session.read_resource(uri)

    async def list_tools(self) -> types.ListToolsResult:
        return await self.session.list_tools()

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        return await self.session.call_tool(name, arguments or {})

    async def close(self) -> None:
        await self.exit_stack.aclose()


class StreamableHttpConnectionFactory:
    def __init__(self, config: AliyunProxyConfig) -> None:
        self._config = config

    async def connect(self, *, bearer_token: str) -> StreamableHttpConnection:
        headers = {
            "authorization": f"Bearer {bearer_token}",
            "user-agent": "aliyun-mcp-proxy/0.1.0",
        }
        if self._config.region:
            headers["x-mcp-region-id"] = self._config.region

        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_seconds,
            read=self._config.read_timeout_seconds,
            write=self._config.read_timeout_seconds,
            pool=self._config.connect_timeout_seconds,
        )

        exit_stack = AsyncExitStack()
        client = await exit_stack.enter_async_context(
            httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
        )
        streams = await exit_stack.enter_async_context(
            streamable_http_client(
                self._config.server_url,
                http_client=client,
                terminate_on_close=False,
            )
        )

        read_stream = streams[0]
        write_stream = streams[1]
        session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        return StreamableHttpConnection(session=session, exit_stack=exit_stack)
