## Alibaba Cloud MCP Proxy

A local stdio MCP (Model Context Protocol) proxy for Alibaba Cloud OpenAPI MCP servers. It bridges MCP clients (such as Claude Desktop, Cursor, or other AI-powered IDEs) with Alibaba Cloud's upstream MCP services, handling authentication, connection management, retries, and safety policies transparently.

### Prerequisites

The RAM user or role running the proxy **must** have the following permissions. Attach this policy in the [RAM Console](https://ram.console.aliyun.com/):

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ram:GenerateAccessToken",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "openapiexplorer:*",
      "Resource": "*"
    }
  ]
}
```

- **`ram:GenerateAccessToken`** — Required for the proxy to obtain bearer tokens via IMS.
- **`openapiexplorer:*`** — Required for MCP server discovery and tool invocation.

### Quick Start

Run the proxy with `uvx` (always fetches the latest version, no install needed):

```bash
uvx lazy.alibabacloud-mcp-proxy@latest
```

If you have a custom MCP server URL, you can specify it explicitly:

```bash
uvx lazy.alibabacloud-mcp-proxy@latest --server-url <YOUR_MCP_SERVER_URL>
```

#### MCP Client Configuration (Claude Desktop / Cursor)

Add the following to your MCP client configuration file (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "alibabacloud": {
      "command": "uvx",
      "args": ["lazy.alibabacloud-mcp-proxy@latest"]
    }
  }
}
```

### Debugging

To enable debug logging, use `--debug` together with `--log-file` to write detailed logs to a file:

```bash
uvx lazy.alibabacloud-mcp-proxy@latest --debug --log-file=/tmp/a.log --safety-policy "ecs:describe-*=allow,*=deny"
```

### Safety Policy

You can constrain which MCP tools the proxy is allowed to invoke by specifying a **safety policy**. This is applied to the bearer token before connecting to the upstream MCP server, ensuring the token is scoped to only the allowed tool calls.

#### Example: Allow only ECS describe operations

```bash
uvx lazy.alibabacloud-mcp-proxy@latest --safety-policy "ecs:describe-*=allow,*=deny"
```

#### MCP Client Configuration with Safety Policy

```json
{
  "mcpServers": {
    "alibabacloud": {
      "command": "uvx",
      "args": [
        "lazy.alibabacloud-mcp-proxy@latest",
        "--safety-policy", "ecs:describe-*=allow,*=deny"
      ]
    }
  }
}
```

You can also set the safety policy via environment variable:

```bash
export ALIBABACLOUD_MCP_SAFETY_POLICY="ecs:describe-*=allow,*=deny"
uvx lazy.alibabacloud-mcp-proxy@latest
```

### Pre-check

Before connecting to the upstream MCP server, you can verify that your local OAuth application is properly installed and authorized by running the **pre-check** command. This starts a lightweight local HTTP server, opens your browser to the Alibaba Cloud OAuth authorization page, and waits for the callback.

```bash
uvx lazy.alibabacloud-mcp-proxy@latest pre-check
```

For international sites:

```bash
uvx lazy.alibabacloud-mcp-proxy@latest pre-check --site-type INTL
```

With a custom OAuth client ID:

```bash
uvx lazy.alibabacloud-mcp-proxy@latest pre-check --client-id YOUR_OAUTH_CLIENT_ID
```

If the pre-check passes, you will see:

```
✓ Pre-check passed! You can connect via local static credentials.
```

### Configuration Reference

Every CLI flag has a corresponding environment variable. **CLI flags take precedence** over environment variables.

#### Connection Settings

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--server-url` | `ALIBABACLOUD_MCP_SERVER_URL` | *(auto-discover)* | Upstream Alibaba Cloud MCP streamable HTTP URL. If not set, the proxy discovers it via the `ListApiMcpServerCores` OpenAPI. |
| `--site-type` | `ALIBABACLOUD_MCP_SITE_TYPE` | `CN` | Alibaba Cloud site type: `CN` (China) or `INTL` (International). |
| `--connect-timeout` | `ALIBABACLOUD_MCP_CONNECT_TIMEOUT` | `10.0` | HTTP connect timeout in seconds. |
| `--read-timeout` | `ALIBABACLOUD_MCP_READ_TIMEOUT` | `120.0` | HTTP read timeout in seconds. |

#### Authentication Settings

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--bearer-token` | `ALIBABACLOUD_MCP_BEARER_TOKEN` | — | Explicit bearer token for the upstream MCP server. |
| `--token-command` | `ALIBABACLOUD_MCP_TOKEN_COMMAND` | — | Shell command that prints a bearer token or JSON with `access_token`. |
| `--client-id` | `ALIBABACLOUD_MCP_CLIENT_ID` | *(per site type)* | IMS `GenerateAccessToken` ClientId. Defaults to `4071151845732613353` (CN) or `4195410055503316452` (INTL). |
| `--scope` | `ALIBABACLOUD_MCP_SCOPE` | `/internal/acs/openapi` | IMS `GenerateAccessToken` Scope. |
| `--ims-endpoint` | `ALIBABACLOUD_MCP_IMS_ENDPOINT` | `ramoauth.aliyuncs.com` (CN) / `ramoauth.alibabacloudcs.com` (INTL) | IMS API endpoint hostname. Auto-selected based on `--site-type`. |

#### Safety Policy

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--safety-policy` | `ALIBABACLOUD_MCP_SAFETY_POLICY` | — | Safety policy expression to constrain allowed MCP tool calls (e.g. `ecs:describe-*=allow,*=deny`). Applied to the bearer token before connecting. |

#### Retry Settings

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--retry-max-attempts` | `ALIBABACLOUD_MCP_RETRY_MAX_ATTEMPTS` | `3` | Maximum attempts per upstream request before surfacing an error. |
| `--retry-base-seconds` | `ALIBABACLOUD_MCP_RETRY_BASE_SECONDS` | `1.0` | Initial retry delay in seconds (exponential backoff). |
| `--retry-max-seconds` | `ALIBABACLOUD_MCP_RETRY_MAX_SECONDS` | `8.0` | Maximum retry delay in seconds. |

#### Token Refresh

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| — | `ALIBABACLOUD_MCP_REFRESH_SKEW_SECONDS` | `60` | Seconds before token expiry to trigger a proactive refresh. |

#### Debug / Logging

| CLI Flag | Environment Variable | Default | Description |
|---|---|---|---|
| `--debug` | `ALIBABACLOUD_MCP_DEBUG` | `false` | Enable debug logging. Requires `--log-file` to be set. |
| `--log-file` | `ALIBABACLOUD_MCP_LOG_FILE` | — | Path to the log file. Required when `--debug` is enabled. |

#### Pre-check Sub-command

| CLI Flag | Default | Description |
|---|---|---|
| `--site-type` | `CN` | Alibaba Cloud site type: `CN` or `INTL`. |
| `--client-id` | *(per site type)* | Custom OAuth application Client ID for the pre-check flow. |

### Requirements

- Python >= 3.13

### License

Apache-2.0
