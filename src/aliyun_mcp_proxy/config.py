from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


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
    access_key_id: str | None
    access_key_secret: str | None
    security_token: str | None
    refresh_skew_seconds: int = 60


@dataclass(slots=True, frozen=True)
class AliyunProxyConfig:
    server_url: str
    region: str | None
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
    ) -> "AliyunProxyConfig":
        merged: dict[str, str | None] = {}
        if defaults:
            merged.update(defaults)
        for key, value in values.items():
            if value is not None:
                merged[key] = value

        server_url = (merged.get("server_url") or "").strip()
        if not server_url:
            raise ProxyConfigurationError(
                "Missing upstream MCP server URL. Set --server-url or ALIYUN_MCP_SERVER_URL."
            )

        return cls(
            server_url=server_url,
            region=(merged.get("region") or "").strip() or None,
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
            log_level=(merged.get("log_level") or "INFO").upper(),
            token=TokenSettings(
                bearer_token=(merged.get("bearer_token") or "").strip() or None,
                token_command=(merged.get("token_command") or "").strip() or None,
                access_key_id=(merged.get("access_key_id") or "").strip() or None,
                access_key_secret=(merged.get("access_key_secret") or "").strip() or None,
                security_token=(merged.get("security_token") or "").strip() or None,
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
    def from_env(cls) -> "AliyunProxyConfig":
        return cls.from_mapping(cls.env_values())

    @staticmethod
    def env_values() -> dict[str, str | None]:
        return {
            "server_url": _env("ALIYUN_MCP_SERVER_URL"),
            "region": _env("ALIYUN_MCP_REGION"),
            "connect_timeout_seconds": _env("ALIYUN_MCP_CONNECT_TIMEOUT"),
            "read_timeout_seconds": _env("ALIYUN_MCP_READ_TIMEOUT"),
            "log_level": _env("ALIYUN_MCP_LOG_LEVEL", "INFO"),
            "bearer_token": _env("ALIYUN_MCP_BEARER_TOKEN"),
            "token_command": _env("ALIYUN_MCP_TOKEN_COMMAND"),
            "access_key_id": _env("ALIBABA_CLOUD_ACCESS_KEY_ID"),
            "access_key_secret": _env("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
            "security_token": _env("ALIBABA_CLOUD_SECURITY_TOKEN"),
            "refresh_skew_seconds": _env("ALIYUN_MCP_REFRESH_SKEW_SECONDS"),
            "max_attempts": _env("ALIYUN_MCP_RETRY_MAX_ATTEMPTS"),
            "base_delay_seconds": _env("ALIYUN_MCP_RETRY_BASE_SECONDS"),
            "max_delay_seconds": _env("ALIYUN_MCP_RETRY_MAX_SECONDS"),
        }
