from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import anyio

from alibabacloud_mcp_proxy.auth.ims_access_token import DEFAULT_IMS_CLIENT_ID
from alibabacloud_mcp_proxy.auth.token_provider import (
    TokenAcquisitionError,
    build_token_provider,
)
from alibabacloud_mcp_proxy.config import AlibabaCloudProxyConfig, ProxyConfigurationError
from alibabacloud_mcp_proxy.discovery import discover_mcp_server_url
from alibabacloud_mcp_proxy.proxy.server import AlibabaCloudMcpProxyServer
from alibabacloud_mcp_proxy.session.reconnecting_session import ReconnectingSession
from alibabacloud_mcp_proxy.transport.upstream_http import StreamableHttpConnectionFactory
from alibabacloud_mcp_proxy.transport.upstream_sse import SseConnectionFactory

_LOGGER = logging.getLogger(__name__)


def _configure_logging(*, debug: bool, log_file: str | None) -> Path | None:
    """Configure logging based on the --debug flag.

    When *debug* is ``False`` (default), logging is effectively silenced
    (level ``CRITICAL``) so that nothing leaks into stderr — MCP uses
    stdout for JSON-RPC and any stray output would corrupt the protocol
    stream.

    When *debug* is ``True``, the level is set to ``DEBUG`` and logs are
    written to the user-specified *log_file*.  The caller must ensure
    *log_file* is not ``None`` before calling with ``debug=True``.
    """
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.handlers.clear()

    if not debug:
        root.setLevel(logging.CRITICAL)
        return None

    level = logging.DEBUG
    root.setLevel(level)

    log_path = Path(log_file)  # type: ignore[arg-type]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:
        print(
            f"Error: cannot open log file {log_path}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    return log_path

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alibabacloud-mcp-proxy",
        description="Local stdio MCP proxy for Alibaba Cloud OpenAPI MCP servers.",
    )
    parser.add_argument("--server-url", help="Upstream Alibaba Cloud MCP streamable HTTP URL.")
    parser.add_argument(
        "--site-type",
        dest="site_type",
        choices=["CN", "INTL"],
        default=None,
        help="Alibaba Cloud site type: CN (China, default) or INTL (International).",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        dest="connect_timeout_seconds",
        help="HTTP connect timeout in seconds.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        dest="read_timeout_seconds",
        help="HTTP read timeout in seconds.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=None,
        help="Enable debug logging. Requires --log-file to be set.",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        default=None,
        help="Path to the log file. Required when --debug is enabled.",
    )
    parser.add_argument(
        "--bearer-token",
        dest="bearer_token",
        help="Explicit bearer token for the upstream MCP server.",
    )
    parser.add_argument(
        "--token-command",
        dest="token_command",
        help="Command that prints a bearer token or JSON with access_token.",
    )
    parser.add_argument(
        "--client-id",
        dest="ims_client_id",
        help="IMS GenerateAccessToken ClientId. "
        f"Default {DEFAULT_IMS_CLIENT_ID} or ALIBABACLOUD_MCP_CLIENT_ID.",
    )
    parser.add_argument(
        "--scope",
        dest="ims_scope",
        help="IMS GenerateAccessToken Scope. "
        "Default /internal/acs/openapi or ALIBABACLOUD_MCP_SCOPE.",
    )
    parser.add_argument(
        "--ims-endpoint",
        dest="ims_endpoint",
        help="IMS API endpoint hostname. Default ims.aliyuncs.com or ALIBABACLOUD_MCP_IMS_ENDPOINT.",
    )
    parser.add_argument(
        "--retry-max-attempts",
        dest="max_attempts",
        type=int,
        help="Maximum attempts per upstream request before surfacing an error.",
    )
    parser.add_argument(
        "--retry-base-seconds",
        dest="base_delay_seconds",
        type=float,
        help="Initial retry delay in seconds.",
    )
    parser.add_argument(
        "--retry-max-seconds",
        dest="max_delay_seconds",
        type=float,
        help="Maximum retry delay in seconds.",
    )
    return parser


def parse_config(argv: Sequence[str] | None = None) -> AlibabaCloudProxyConfig:
    args = build_parser().parse_args(argv)
    values = {
        "site_type": args.site_type,
        "server_url": args.server_url,
        "connect_timeout_seconds": _stringify(args.connect_timeout_seconds),
        "read_timeout_seconds": _stringify(args.read_timeout_seconds),
        "debug": _stringify(args.debug),
        "log_file": args.log_file,
        "bearer_token": args.bearer_token,
        "token_command": args.token_command,
        "ims_client_id": args.ims_client_id,
        "ims_scope": args.ims_scope,
        "ims_endpoint": args.ims_endpoint,
        "max_attempts": _stringify(args.max_attempts),
        "base_delay_seconds": _stringify(args.base_delay_seconds),
        "max_delay_seconds": _stringify(args.max_delay_seconds),
    }
    return AlibabaCloudProxyConfig.from_mapping(
        values,
        defaults=AlibabaCloudProxyConfig.env_values(),
    )


def _is_sse_endpoint(server_url: str) -> bool:
    """Return True if the server URL indicates an SSE transport (ends with /sse)."""
    return server_url.rstrip("/").endswith("/sse")

async def _resolve_server_url(config: AlibabaCloudProxyConfig) -> str:
    """Return the MCP server URL, discovering it via OpenAPI if not explicitly set."""
    if config.server_url:
        _LOGGER.info("Using user-specified server URL: %s", config.server_url)
        return config.server_url

    return await discover_mcp_server_url(config.site_type)


async def run_proxy(config: AlibabaCloudProxyConfig) -> None:
    server_url = await _resolve_server_url(config)
    token_provider = build_token_provider(config.token)

    if _is_sse_endpoint(server_url):
        connection_factory = SseConnectionFactory(config, server_url)
    else:
        connection_factory = StreamableHttpConnectionFactory(config, server_url)

    async with anyio.create_task_group() as background_tasks:
        connection_factory.set_task_group(background_tasks)
        session = ReconnectingSession(connection_factory, token_provider, config.retry)
        proxy = AlibabaCloudMcpProxyServer(config, session)
        try:
            await proxy.run()
        finally:
            await proxy.aclose()
            background_tasks.cancel_scope.cancel()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_config(argv)
    except (ProxyConfigurationError, TokenAcquisitionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(str(exc)) from exc

    if config.debug and not config.log_file:
        print(
            "Error: --debug requires --log-file to be specified.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    log_path = _configure_logging(debug=config.debug, log_file=config.log_file)

    if config.debug:
        _LOGGER.info(
            "stdio MCP server starting — debug logging enabled, writing to %s. "
            "Site type: %s. Process will wait until an MCP client connects.",
            log_path,
            config.site_type.value,
        )

    try:
        anyio.run(run_proxy, config)
    except (ProxyConfigurationError, TokenAcquisitionError) as exc:
        if config.debug:
            _LOGGER.exception("Proxy terminated with configuration/token error: %s", exc)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(str(exc)) from exc
    return 0


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
