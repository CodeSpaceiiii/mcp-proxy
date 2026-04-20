from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import anyio
import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl

from alibabacloud_mcp_proxy.config import AlibabaCloudProxyConfig

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamableHttpConnection:
    """A single-use upstream connection that creates a fresh session per RPC call.

    The MCP SDK's ``streamable_http_client`` starts a background GET SSE stream
    after the ``initialized`` notification.  When the remote server does not
    support GET (responds with 405), the background task eventually fails and
    tears down the entire ``ClientSession`` – including the POST channel that
    was working fine.

    To work around this, we treat each upstream call as an independent
    short-lived session: connect → initialize → call → close.  This avoids
    the GET-stream crash and keeps the proxy's stdio server alive between
    requests.
    """

    config: AlibabaCloudProxyConfig
    bearer_token: str

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self.bearer_token}",
            "user-agent": "alibabacloud-mcp-proxy/0.1.0",
        }
        if self.config.region:
            headers["x-mcp-region-id"] = self.config.region
        return headers

    def _build_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.config.connect_timeout_seconds,
            read=self.config.read_timeout_seconds,
            write=self.config.read_timeout_seconds,
            pool=self.config.connect_timeout_seconds,
        )

    async def _open_session(self) -> tuple[ClientSession, AsyncExitStack]:
        """Create a fresh upstream session (connect + initialize)."""
        exit_stack = AsyncExitStack()
        try:
            client = await exit_stack.enter_async_context(
                httpx.AsyncClient(
                    headers=self._build_headers(),
                    timeout=self._build_timeout(),
                    follow_redirects=True,
                )
            )
            streams = await exit_stack.enter_async_context(
                streamable_http_client(
                    self.config.server_url,
                    http_client=client,
                    terminate_on_close=False,
                )
            )
            session = await exit_stack.enter_async_context(
                ClientSession(streams[0], streams[1])
            )
            await session.initialize()
            return session, exit_stack
        except BaseException:
            await exit_stack.aclose()
            raise

    async def _run_single_call(
        self,
        caller: Any,
    ) -> Any:
        """Open a session, execute *caller*, then close the session."""
        session, exit_stack = await self._open_session()
        try:
            return await caller(session)
        finally:
            await exit_stack.aclose()

    async def list_prompts(self) -> types.ListPromptsResult:
        return await self._run_single_call(lambda s: s.list_prompts())

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        return await self._run_single_call(lambda s: s.get_prompt(name, arguments))

    async def list_resources(self) -> types.ListResourcesResult:
        return await self._run_single_call(lambda s: s.list_resources())

    async def read_resource(self, uri: AnyUrl) -> types.ReadResourceResult:
        return await self._run_single_call(lambda s: s.read_resource(uri))

    async def list_tools(self) -> types.ListToolsResult:
        return await self._run_single_call(lambda s: s.list_tools())

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        return await self._run_single_call(
            lambda s: s.call_tool(name, arguments or {})
        )

    async def close(self) -> None:
        """No-op: each call manages its own session lifecycle."""


class StreamableHttpConnectionFactory:
    def __init__(self, config: AlibabaCloudProxyConfig) -> None:
        self._config = config

    async def connect(self, *, bearer_token: str) -> StreamableHttpConnection:
        return StreamableHttpConnection(
            config=self._config,
            bearer_token=bearer_token,
        )