from __future__ import annotations

import base64
import logging
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, INTERNAL_ERROR
from pydantic import AnyUrl

from lazy.alibabacloud_mcp_proxy.config import AlibabaCloudProxyConfig
from lazy.alibabacloud_mcp_proxy.session.reconnecting_session import ReconnectingSession
from lazy.alibabacloud_mcp_proxy.transport.stdio_server import run_stdio_server

_LOGGER = logging.getLogger(__name__)


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
        try:
            return await self._session.list_prompts()
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream prompts/list failed: %s", exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc

    async def _handle_get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None,
    ) -> types.GetPromptResult:
        try:
            return await self._session.get_prompt(name, arguments)
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream prompts/get:%s failed: %s", name, exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc

    async def _handle_list_resources(self) -> types.ListResourcesResult:
        try:
            return await self._session.list_resources()
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream resources/list failed: %s", exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc

    async def _handle_read_resource(self, uri: AnyUrl) -> list[ReadResourceContents]:
        try:
            result = await self._session.read_resource(uri)
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream resources/read:%s failed: %s", uri, exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc

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
        try:
            return await self._session.list_tools()
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream tools/list failed: %s", exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc

    async def _handle_call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> types.CallToolResult:
        try:
            return await self._session.call_tool(name, arguments)
        except McpError:
            raise
        except Exception as exc:
            _LOGGER.error("Upstream tools/call:%s failed: %s", name, exc, exc_info=True)
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc
