from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aliyun_mcp_proxy.auth.token_provider import (
    BearerToken,
    CachedBearerTokenProvider,
    StaticBearerTokenSource,
    TokenAcquisitionError,
    build_token_provider,
)
from aliyun_mcp_proxy.config import TokenSettings


class FakeTokenSource:
    def __init__(self, tokens: list[BearerToken]) -> None:
        self.tokens = tokens
        self.calls = 0

    async def fetch_token(self) -> BearerToken:
        token = self.tokens[min(self.calls, len(self.tokens) - 1)]
        self.calls += 1
        return token


@pytest.mark.asyncio
async def test_static_token_provider_returns_configured_token() -> None:
    provider = build_token_provider(
        TokenSettings(
            bearer_token="abc123",
            token_command=None,
            access_key_id=None,
            access_key_secret=None,
            security_token=None,
        )
    )

    token = await provider.get_token()

    assert token == "abc123"


@pytest.mark.asyncio
async def test_cached_token_provider_refreshes_expiring_tokens() -> None:
    source = FakeTokenSource(
        [
            BearerToken(
                value="old-token",
                expires_at=datetime.now(UTC) + timedelta(seconds=10),
            ),
            BearerToken(
                value="new-token",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            ),
        ]
    )
    provider = CachedBearerTokenProvider(source, refresh_skew_seconds=30)

    first = await provider.get_token()
    second = await provider.get_token()

    assert first == "old-token"
    assert second == "new-token"
    assert source.calls == 2


def test_build_token_provider_requires_a_source() -> None:
    with pytest.raises(TokenAcquisitionError):
        build_token_provider(
            TokenSettings(
                bearer_token=None,
                token_command=None,
                access_key_id=None,
                access_key_secret=None,
                security_token=None,
            )
        )
