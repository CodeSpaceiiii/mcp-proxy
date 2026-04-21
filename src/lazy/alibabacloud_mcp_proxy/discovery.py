from __future__ import annotations

import logging
from typing import Any

from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_tea_openapi.client import Client as OpenApiClient
from alibabacloud_tea_openapi.exceptions import ClientException as OpenApiClientException
from alibabacloud_tea_openapi.utils_models import Config, OpenApiRequest, Params
from darabonba.runtime import RuntimeOptions

from lazy.alibabacloud_mcp_proxy.auth.ims_access_token import get_default_credential_client
from lazy.alibabacloud_mcp_proxy.config import (
    DISCOVERY_ENDPOINT_CN,
    DISCOVERY_ENDPOINT_INTL,
    ProxyConfigurationError,
    SiteType,
)

_LOGGER = logging.getLogger(__name__)

LIST_API_MCP_SERVER_CORES_ACTION = "ListApiMcpServerCores"
LIST_API_MCP_SERVER_CORES_VERSION = "2024-11-30"


def _discovery_endpoint(site_type: SiteType) -> str:
    """Return the OpenAPI MCP discovery endpoint for the given site type."""
    if site_type is SiteType.INTL:
        return DISCOVERY_ENDPOINT_INTL
    return DISCOVERY_ENDPOINT_CN


def _extract_mcp_url(response: Any) -> str:
    """
    Extract the first ``urls.mcp`` from a ListApiMcpServerCores response body.

    Raises ``ProxyConfigurationError`` if the response does not contain a usable URL.
    """
    body = response.get("body") if isinstance(response, dict) else None
    if not isinstance(body, dict):
        raise ProxyConfigurationError(
            "ListApiMcpServerCores returned an unexpected response structure."
        )

    cores = body.get("apiMcpServerCores")
    if not isinstance(cores, list) or len(cores) == 0:
        raise ProxyConfigurationError(
            "ListApiMcpServerCores returned no MCP server entries."
        )

    first_core = cores[0]
    urls = first_core.get("urls") if isinstance(first_core, dict) else None
    if not isinstance(urls, dict):
        raise ProxyConfigurationError(
            "ListApiMcpServerCores entry is missing 'urls'."
        )

    mcp_url = urls.get("mcp")
    if not mcp_url or not isinstance(mcp_url, str):
        raise ProxyConfigurationError(
            "ListApiMcpServerCores entry is missing 'urls.mcp'."
        )

    return mcp_url.strip()


async def discover_mcp_server_url(
    site_type: SiteType,
    *,
    credential_client: CredentialClient | None = None,
) -> str:
    """
    Query the Alibaba Cloud OpenAPI to discover the MCP server URL.

    Uses ``ListApiMcpServerCores`` and returns the first ``urls.mcp`` entry.
    Raises ``ProxyConfigurationError`` on any failure so the caller can abort startup.
    """
    endpoint = _discovery_endpoint(site_type)
    _LOGGER.info(
        "Discovering MCP server URL via ListApiMcpServerCores (site=%s, endpoint=%s) ...",
        site_type.value,
        endpoint,
    )

    credential = credential_client or get_default_credential_client()
    config = Config(credential=credential)
    config.endpoint = endpoint
    client = OpenApiClient(config)

    params = Params(
        action=LIST_API_MCP_SERVER_CORES_ACTION,
        version=LIST_API_MCP_SERVER_CORES_VERSION,
        protocol="HTTPS",
        method="GET",
        auth_type="AK",
        style="ROA",
        pathname="/apimcpservercores",
        req_body_type="json",
        body_type="json",
    )
    request = OpenApiRequest()
    runtime = RuntimeOptions()

    try:
        response = await client.call_api_async(params, request, runtime)
    except OpenApiClientException as exc:
        detail = exc.message or exc.code or str(exc)
        raise ProxyConfigurationError(
            f"Failed to discover MCP server URL: {detail}"
        ) from exc
    except Exception as exc:
        raise ProxyConfigurationError(
            f"Failed to discover MCP server URL: {exc}"
        ) from exc

    _LOGGER.debug("ListApiMcpServerCores raw response: %r", response)

    mcp_url = _extract_mcp_url(response)
    _LOGGER.info("Discovered MCP server URL: %s", mcp_url)
    return mcp_url
