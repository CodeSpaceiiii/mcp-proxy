from __future__ import annotations

from aliyun_mcp_proxy.cli import parse_config


def test_parse_config_uses_cli_values() -> None:
    config = parse_config(
        [
            "--server-url",
            "https://example.com/mcp",
            "--region",
            "cn-hangzhou",
            "--retry-max-attempts",
            "5",
        ]
    )

    assert config.server_url == "https://example.com/mcp"
    assert config.region == "cn-hangzhou"
    assert config.retry.max_attempts == 5


def test_parse_config_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("ALIYUN_MCP_SERVER_URL", "https://env.example/mcp")
    monkeypatch.setenv("ALIYUN_MCP_REGION", "cn-beijing")

    config = parse_config([])

    assert config.server_url == "https://env.example/mcp"
    assert config.region == "cn-beijing"
