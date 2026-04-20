from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from alibabacloud_mcp_proxy.cli import default_log_file_path, main, parse_config
from alibabacloud_mcp_proxy.config import DEFAULT_MCP_SERVER_URL
from alibabacloud_mcp_proxy.auth.token_provider import TokenAcquisitionError


def test_default_log_file_path_under_tmp() -> None:
    assert default_log_file_path() == Path("/tmp/alibabacloud-mcp-proxy.log")


def test_parse_config_uses_builtin_defaults_when_no_env(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ALIBABACLOUD_MCP_SERVER_URL", raising=False)

    config = parse_config([])

    assert config.server_url == DEFAULT_MCP_SERVER_URL


def test_parse_config_uses_cli_values() -> None:
    config = parse_config(
        [
            "--server-url",
            "https://example.com/mcp",
            "--retry-max-attempts",
            "5",
        ]
    )

    assert config.server_url == "https://example.com/mcp"
    assert config.retry.max_attempts == 5


def test_parse_config_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("ALIBABACLOUD_MCP_SERVER_URL", "https://env.example/mcp")

    config = parse_config([])

    assert config.server_url == "https://env.example/mcp"


def test_parse_config_ims_client_and_scope_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ALIBABACLOUD_MCP_SERVER_URL", "https://env.example/mcp")
    monkeypatch.setenv("ALIBABACLOUD_MCP_CLIENT_ID", "999")
    monkeypatch.setenv("ALIBABACLOUD_MCP_SCOPE", "/custom/scope")

    config = parse_config([])

    assert config.token.ims_client_id == "999"
    assert config.token.ims_scope == "/custom/scope"


def test_parse_config_cli_overrides_ims_defaults() -> None:
    config = parse_config(
        [
            "--server-url",
            "https://example.com/mcp",
            "--client-id",
            "111",
            "--scope",
            "/cli-scope",
            "--ims-endpoint",
            "ims.cn-hangzhou.aliyuncs.com",
        ]
    )

    assert config.token.ims_client_id == "111"
    assert config.token.ims_scope == "/cli-scope"
    assert config.token.ims_endpoint == "ims.cn-hangzhou.aliyuncs.com"


def test_main_logs_runtime_token_error(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "proxy.log"
    monkeypatch.setattr("alibabacloud_mcp_proxy.cli.default_log_file_path", lambda: log_path)

    with (
        patch("alibabacloud_mcp_proxy.cli.anyio.run", side_effect=TokenAcquisitionError("boom")),
        pytest.raises(SystemExit, match="boom"),
    ):
        main([])

    assert log_path.exists()
    assert "Proxy terminated with configuration/token error: boom" in log_path.read_text()
