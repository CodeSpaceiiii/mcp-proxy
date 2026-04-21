"""Apply a safety policy to a bearer token via the Alibaba Cloud OpenAPI.

The safety policy constrains which MCP tools the bearer token is allowed
to invoke.  The API is anonymous (no AK/SK required) and must be called
**before** the proxy connects to the upstream MCP server with that token.
"""

from __future__ import annotations

import logging

from alibabacloud_tea_openapi.client import Client as OpenApiClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

_LOGGER = logging.getLogger(__name__)

_SAFETY_POLICY_ENDPOINT = "openapi-mcp.cn-hangzhou.aliyuncs.com"
_SAFETY_POLICY_ACTION = "UpdateBearerTokenSafetyPolicy"
_SAFETY_POLICY_VERSION = "2024-11-30"
_SAFETY_POLICY_PATHNAME = "/safePolicy/set"


def _create_anonymous_client() -> OpenApiClient:
    """Create an anonymous OpenAPI client (no AK/SK credentials needed)."""
    config = open_api_models.Config(signature_algorithm="v2")
    config.endpoint = _SAFETY_POLICY_ENDPOINT
    return OpenApiClient(config)


def _create_params() -> open_api_models.Params:
    """Build the API params for UpdateBearerTokenSafetyPolicy."""
    return open_api_models.Params(
        action=_SAFETY_POLICY_ACTION,
        version=_SAFETY_POLICY_VERSION,
        protocol="HTTPS",
        method="POST",
        auth_type="Anonymous",
        style="ROA",
        pathname=_SAFETY_POLICY_PATHNAME,
        req_body_type="json",
        body_type="json",
    )


async def apply_safety_policy(bearer_token: str, safety_policy: str) -> None:
    """Set a safety policy on the given bearer token.

    This calls the ``UpdateBearerTokenSafetyPolicy`` API anonymously.
    Must be invoked **before** connecting to the upstream MCP server so
    that the token is constrained to the allowed tool-call scope.

    Raises on API errors so the caller can decide whether to abort or retry.
    """
    _LOGGER.debug(
        "Applying safety policy to bearer token (policy=%r, token=%s...)",
        safety_policy,
        bearer_token[:12] if len(bearer_token) > 12 else "***",
    )

    client = _create_anonymous_client()
    params = _create_params()

    body = {
        "bearerToken": bearer_token,
        "safePolicy": safety_policy,
    }
    runtime = util_models.RuntimeOptions()
    request = open_api_models.OpenApiRequest(body=body)

    response = await client.call_api_async(params, request, runtime)

    _LOGGER.debug(
        "Safety policy applied successfully (status=%s)",
        response.get("statusCode") if isinstance(response, dict) else "unknown",
    )
