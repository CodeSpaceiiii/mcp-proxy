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
from alibabacloud_mcp_proxy.proxy.server import AlibabaCloudMcpProxyServer
from alibabacloud_mcp_proxy.session.reconnecting_session import ReconnectingSession
from alibabacloud_mcp_proxy.transport.upstream_http import StreamableHttpConnectionFactory
from alibabacloud_mcp_proxy.transport.upstream_sse import SseConnectionFactory

_LOGGER = logging.getLogger(__name__)

_DEFAULT_LOG_FILENAME = "alibabacloud-mcp-proxy.log"


def default_log_file_path() -> Path:
    """
    Return the fixed default log path under ``/tmp``.
    """
    return Path("/tmp") / _DEFAULT_LOG_FILENAME


def _configure_logging(level_name: str) -> Path:
    """Send all logs to stderr and to the default /tmp log file."""
    level = getattr(logging, level_name, logging.INFO)
    log_path = default_log_file_path()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Could not open log file %s: %s (stderr logging only)",
            log_path,
            exc,
        )

    return log_path


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
        "server_url": args.server_url,
        "region": args.region,
        "connect_timeout_seconds": _stringify(args.connect_timeout_seconds),
        "read_timeout_seconds": _stringify(args.read_timeout_seconds),
        "log_level": args.log_level,
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

async def run_proxy(config: AlibabaCloudProxyConfig) -> None:
    token_provider = build_token_provider(config.token)

    if _is_sse_endpoint(config.server_url):
        connection_factory = SseConnectionFactory(config)
        async with anyio.create_task_group() as background_tasks:
            connection_factory.set_task_group(background_tasks)
            session = ReconnectingSession(connection_factory, token_provider, config.retry)
            proxy = AlibabaCloudMcpProxyServer(config, session)
            try:
                await proxy.run()
            finally:
                await proxy.aclose()
                background_tasks.cancel_scope.cancel()
    else:
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
        _configure_logging("INFO")
        _LOGGER.exception("Proxy failed before startup completed: %s", exc)
        raise SystemExit(str(exc)) from exc

    log_path = _configure_logging(config.log_level)
    # MCP uses stdout for JSON-RPC; logs go to stderr and to log_path.
    _LOGGER.info(
        "stdio MCP server starting — protocol traffic is on stdout; logs on stderr and in %s. "
        "Upstream: %s (region=%s). Process will wait until an MCP client connects.",
        log_path,
        config.server_url,
        config.region,
    )

    try:
        anyio.run(run_proxy, config)
    except (ProxyConfigurationError, TokenAcquisitionError) as exc:
        _LOGGER.exception("Proxy terminated with configuration/token error: %s", exc)
        raise SystemExit(str(exc)) from exc
    return 0


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
