from __future__ import annotations

import base64
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from pydantic import AnyUrl

from alibabacloud_mcp_proxy.config import AlibabaCloudProxyConfig
from alibabacloud_mcp_proxy.session.reconnecting_session import ReconnectingSession
from alibabacloud_mcp_proxy.transport.stdio_server import run_stdio_server


class AlibabaCloudMcpProxyServer:
    def __init__(self, config: AlibabaCloudProxyConfig, session: ReconnectingSession) -> None:
        self._config = config
        self._session = session
        self._server = Server("alibabacloud-mcp-proxy")
        self._register_handlers()

    async def run(self) -> None:
        await run_stdio_server(self._server)

    async def aclose(self) -> None:
        await self._session.aclose()

    def _register_handlers(self) -> None:
        self._server.list_prompts()(self._handle_list_prompts)
        self._server.get_prompt()(self._handle_get_prompt)
        self._server.list_resources()(self._handle_list_resources)
        self._server.read_resource()(self._handle_read_resource)
        self._server.list_tools()(self._handle_list_tools)
        self._server.call_tool()(self._handle_call_tool)

    async def _handle_list_prompts(self) -> types.ListPromptsResult:
        return await self._session.list_prompts()

    async def _handle_get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None,
    ) -> types.GetPromptResult:
        return await self._session.get_prompt(name, arguments)

    async def _handle_list_resources(self) -> types.ListResourcesResult:
        return await self._session.list_resources()

    async def _handle_read_resource(self, uri: AnyUrl) -> list[ReadResourceContents]:
        result = await self._session.read_resource(uri)
        contents: list[ReadResourceContents] = []
        for item in result.contents:
            if hasattr(item, "text"):
                contents.append(
                    ReadResourceContents(
                        content=item.text,
                        mime_type=item.mimeType,
                        meta=getattr(item, "meta", None),
                    )
                )
            else:
                contents.append(
                    ReadResourceContents(
                        content=base64.b64decode(item.blob),
                        mime_type=item.mimeType,
                        meta=getattr(item, "meta", None),
                    )
                )
        return contents

    async def _handle_list_tools(self) -> types.ListToolsResult:
        return await self._session.list_tools()

    async def _handle_call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        return await self._session.call_tool(name, self._inject_region(arguments))

    def _inject_region(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(arguments or {})
        if self._config.region and "x_mcp_region_id" not in payload:
            payload["x_mcp_region_id"] = self._config.region
        return payload
