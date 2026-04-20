from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import anyio

from alibabacloud_mcp_proxy.auth.token_provider import (
    TokenAcquisitionError,
    build_token_provider,
)
from alibabacloud_mcp_proxy.config import AlibabaCloudProxyConfig, ProxyConfigurationError
from alibabacloud_mcp_proxy.proxy.server import AlibabaCloudMcpProxyServer
from alibabacloud_mcp_proxy.session.reconnecting_session import ReconnectingSession
from alibabacloud_mcp_proxy.transport.upstream_http import StreamableHttpConnectionFactory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alibabacloud-mcp-proxy",
        description="Local stdio MCP proxy for Alibaba Cloud OpenAPI MCP servers.",
    )
    parser.add_argument("--server-url", help="Upstream Alibaba Cloud MCP streamable HTTP URL.")
    parser.add_argument("--region", help="Default region injected as x_mcp_region_id.")
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
        "--log-level",
        default=None,
        help="Python logging level. Defaults to ALIBABACLOUD_MCP_LOG_LEVEL or INFO.",
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
        "server_url": args.server_url,
        "region": args.region,
        "connect_timeout_seconds": _stringify(args.connect_timeout_seconds),
        "read_timeout_seconds": _stringify(args.read_timeout_seconds),
        "log_level": args.log_level,
        "bearer_token": args.bearer_token,
        "token_command": args.token_command,
        "max_attempts": _stringify(args.max_attempts),
        "base_delay_seconds": _stringify(args.base_delay_seconds),
        "max_delay_seconds": _stringify(args.max_delay_seconds),
    }
    return AlibabaCloudProxyConfig.from_mapping(
        values,
        defaults=AlibabaCloudProxyConfig.env_values(),
    )


async def run_proxy(config: AlibabaCloudProxyConfig) -> None:
    token_provider = build_token_provider(config.token)
    connection_factory = StreamableHttpConnectionFactory(config)
    session = ReconnectingSession(connection_factory, token_provider, config.retry)
    proxy = AlibabaCloudMcpProxyServer(config, session)

    try:
        await proxy.run()
    finally:
        await proxy.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_config(argv)
    except (ProxyConfigurationError, TokenAcquisitionError) as exc:
        raise SystemExit(str(exc)) from exc

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        anyio.run(run_proxy, config)
    except (ProxyConfigurationError, TokenAcquisitionError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
