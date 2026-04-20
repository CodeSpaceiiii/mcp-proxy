from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping

from alibabacloud_mcp_proxy.auth.ims_access_token import (
    DEFAULT_IMS_CLIENT_ID,
    DEFAULT_IMS_ENDPOINT,
    DEFAULT_IMS_SCOPE,
)

# Built-in upstream for Alibaba Cloud OpenAPI MCP (streamable HTTP), Hangzhou.
DEFAULT_MCP_SERVER_URL = "https://openapi-mcp.cn-hangzhou.aliyuncs.com/mcp"


class ProxyConfigurationError(ValueError):
    """Raised when the proxy is missing required configuration."""


def _env(name: str, default: str | None = None) -> str | None:
    value = environ.get(name, default)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or default


def _parse_float(raw: str | None, *, default: float, field_name: str) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ProxyConfigurationError(f"{field_name} must be a number.") from exc
    if value <= 0:
        raise ProxyConfigurationError(f"{field_name} must be greater than zero.")
    return value


def _parse_int(raw: str | None, *, default: int, field_name: str) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProxyConfigurationError(f"{field_name} must be an integer.") from exc
    if value <= 0:
        raise ProxyConfigurationError(f"{field_name} must be greater than zero.")
    return value


@dataclass(slots=True, frozen=True)
class RetrySettings:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0


@dataclass(slots=True, frozen=True)
class TokenSettings:
    bearer_token: str | None
    token_command: str | None
    ims_client_id: str
    ims_scope: str
    ims_endpoint: str
    refresh_skew_seconds: int = 60


@dataclass(slots=True, frozen=True)
class AlibabaCloudProxyConfig:
    server_url: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    log_level: str
    token: TokenSettings
    retry: RetrySettings

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, str | None],
        *,
        defaults: Mapping[str, str | None] | None = None,
    ) -> "AlibabaCloudProxyConfig":
        merged: dict[str, str | None] = {}
        if defaults:
            merged.update(defaults)
        for key, value in values.items():
            if value is not None:
                merged[key] = value

        server_url = (merged.get("server_url") or "").strip() or DEFAULT_MCP_SERVER_URL

        return cls(
            server_url=server_url,
            connect_timeout_seconds=_parse_float(
                merged.get("connect_timeout_seconds"),
                default=10.0,
                field_name="connect timeout",
            ),
            read_timeout_seconds=_parse_float(
                merged.get("read_timeout_seconds"),
                default=120.0,
                field_name="read timeout",
            ),
            log_level=(merged.get("log_level") or "ERROR").upper(),
            token=TokenSettings(
                bearer_token=(merged.get("bearer_token") or "").strip() or None,
                token_command=(merged.get("token_command") or "").strip() or None,
                ims_client_id=(merged.get("ims_client_id") or "").strip() or DEFAULT_IMS_CLIENT_ID,
                ims_scope=(merged.get("ims_scope") or "").strip() or DEFAULT_IMS_SCOPE,
                ims_endpoint=(merged.get("ims_endpoint") or "").strip() or DEFAULT_IMS_ENDPOINT,
                refresh_skew_seconds=_parse_int(
                    merged.get("refresh_skew_seconds"),
                    default=60,
                    field_name="refresh skew",
                ),
            ),
            retry=RetrySettings(
                max_attempts=_parse_int(
                    merged.get("max_attempts"),
                    default=3,
                    field_name="retry max attempts",
                ),
                base_delay_seconds=_parse_float(
                    merged.get("base_delay_seconds"),
                    default=1.0,
                    field_name="retry base delay",
                ),
                max_delay_seconds=_parse_float(
                    merged.get("max_delay_seconds"),
                    default=8.0,
                    field_name="retry max delay",
                ),
            ),
        )

    @classmethod
    def from_env(cls) -> "AlibabaCloudProxyConfig":
        return cls.from_mapping(cls.env_values())

    @staticmethod
    def env_values() -> dict[str, str | None]:
        return {
            "server_url": _env("ALIBABACLOUD_MCP_SERVER_URL"),
            "connect_timeout_seconds": _env("ALIBABACLOUD_MCP_CONNECT_TIMEOUT"),
            "read_timeout_seconds": _env("ALIBABACLOUD_MCP_READ_TIMEOUT"),
            "log_level": _env("ALIBABACLOUD_MCP_LOG_LEVEL", "ERROR"),
            "bearer_token": _env("ALIBABACLOUD_MCP_BEARER_TOKEN"),
            "token_command": _env("ALIBABACLOUD_MCP_TOKEN_COMMAND"),
            "ims_client_id": _env("ALIBABACLOUD_MCP_CLIENT_ID"),
            "ims_scope": _env("ALIBABACLOUD_MCP_SCOPE"),
            "ims_endpoint": _env("ALIBABACLOUD_MCP_IMS_ENDPOINT"),
            "refresh_skew_seconds": _env("ALIBABACLOUD_MCP_REFRESH_SKEW_SECONDS"),
            "max_attempts": _env("ALIBABACLOUD_MCP_RETRY_MAX_ATTEMPTS"),
            "base_delay_seconds": _env("ALIBABACLOUD_MCP_RETRY_BASE_SECONDS"),
            "max_delay_seconds": _env("ALIBABACLOUD_MCP_RETRY_MAX_SECONDS"),
        }
