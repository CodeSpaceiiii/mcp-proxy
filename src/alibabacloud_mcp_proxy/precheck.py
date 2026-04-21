"""OAuth pre-check: verify that the user has an OAuth app installed and assigned.

Starts a lightweight local HTTP server on a random port, opens the browser to
the Alibaba Cloud OAuth authorization endpoint, and waits for the callback.
If the callback arrives successfully the user is informed that local credential
based connection is ready.
"""

from __future__ import annotations

import hashlib
import html
import secrets
import socket
import base64
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Event, Thread
from urllib.parse import urlencode, urlparse, parse_qs

from alibabacloud_mcp_proxy.config import SiteType

# ---------------------------------------------------------------------------
# OAuth endpoint per site type
# ---------------------------------------------------------------------------
OAUTH_ENDPOINT_CN = "https://signin.aliyun.com/oauth2/v1/auth"
OAUTH_ENDPOINT_INTL = "https://signin.alibabacloud.com/oauth2/v1/auth"

# Default OAuth application client IDs (distinct from IMS client IDs)
DEFAULT_OAUTH_CLIENT_ID_CN = "4071151845732613353"
DEFAULT_OAUTH_CLIENT_ID_INTL = "4195410055503316452"

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    """Generate a random PKCE code_verifier (43-128 chars, URL-safe)."""
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(verifier: str) -> str:
    """Derive the S256 code_challenge from a code_verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Pre-check Passed</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; margin: 0;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
    }}
    .card {{
      background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);
      border-radius: 16px; padding: 48px; text-align: center;
      max-width: 520px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);
    }}
    .icon {{ font-size: 64px; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    p {{ margin: 0; opacity: 0.9; line-height: 1.6; }}
    .hint {{ margin-top: 24px; font-size: 13px; opacity: 0.7; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10004;&#65039;</div>
    <h1>Pre-check Passed!</h1>
    <p>
      OAuth authorization completed successfully.<br>
      You can now connect via <strong>local static credentials</strong>.
    </p>
    <p class="hint">You may close this page.</p>
  </div>
</body>
</html>
"""

_ERROR_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Pre-check Failed</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex; justify-content: center; align-items: center;
      min-height: 100vh; margin: 0;
      background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
      color: #fff;
    }}
    .card {{
      background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);
      border-radius: 16px; padding: 48px; text-align: center;
      max-width: 520px; box-shadow: 0 8px 32px rgba(0,0,0,0.2);
    }}
    .icon {{ font-size: 64px; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    p {{ margin: 0; opacity: 0.9; line-height: 1.6; }}
    .detail {{ margin-top: 16px; font-size: 13px; opacity: 0.8;
               background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px;
               word-break: break-all; text-align: left; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10060;</div>
    <h1>Pre-check Failed</h1>
    <p>OAuth authorization did not complete successfully.</p>
    <div class="detail">{error_detail}</div>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Callback HTTP handler
# ---------------------------------------------------------------------------

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle the OAuth redirect callback on ``/oauth/callback``."""

    # Shared across requests via the server instance
    server: _CallbackHTTPServer  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802 – required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)

        if parsed.path != "/oauth/callback":
            self._respond(404, "Not Found")
            return

        query_params = parse_qs(parsed.query)
        error = query_params.get("error")

        if error:
            error_description = query_params.get("error_description", ["unknown error"])[0]
            detail = html.escape(f"{error[0]}: {error_description}")
            body = _ERROR_HTML.format(error_detail=detail)
            self._respond(200, body, content_type="text/html")
            self.server.precheck_error = f"{error[0]}: {error_description}"
            self.server.callback_received.set()
            return

        # Success – we received the authorization code (we don't need to use it)
        body = _SUCCESS_HTML
        self._respond(200, body, content_type="text/html")
        self.server.precheck_error = None
        self.server.callback_received.set()

    def _respond(self, status: int, body: str, *, content_type: str = "text/plain") -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default stderr logging."""


class _CallbackHTTPServer(HTTPServer):
    """HTTPServer subclass carrying shared state for the callback handler."""

    callback_received: Event
    precheck_error: str | None

    def __init__(self, port: int) -> None:
        self.callback_received = Event()
        self.precheck_error = None
        super().__init__(("127.0.0.1", port), _OAuthCallbackHandler)


# ---------------------------------------------------------------------------
# Port selection
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------------------
# OAuth URL construction
# ---------------------------------------------------------------------------

def _oauth_endpoint(site_type: SiteType) -> str:
    if site_type is SiteType.INTL:
        return OAUTH_ENDPOINT_INTL
    return OAUTH_ENDPOINT_CN


def _default_oauth_client_id(site_type: SiteType) -> str:
    if site_type is SiteType.INTL:
        return DEFAULT_OAUTH_CLIENT_ID_INTL
    return DEFAULT_OAUTH_CLIENT_ID_CN


def build_oauth_url(
    site_type: SiteType,
    redirect_uri: str,
    *,
    client_id: str | None = None,
) -> str:
    """Build the full OAuth authorization URL for the given site and redirect URI."""
    endpoint = _oauth_endpoint(site_type)
    resolved_client_id = client_id or _default_oauth_client_id(site_type)

    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_hex(32)

    scope = "openid /acs/mcp-server" if client_id else "/internal/acs/openapi"

    params = {
        "response_type": "code",
        "client_id": resolved_client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
    }
    return f"{endpoint}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_precheck(
    site_type: SiteType,
    *,
    client_id: str | None = None,
) -> int:
    """Run the OAuth pre-check flow.

    1. Start a local HTTP server on a random free port.
    2. Open the browser to the OAuth authorization page.
    3. Wait for the callback.
    4. Print the result and return an exit code (0 = success).
    """
    port = _find_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"
    oauth_url = build_oauth_url(site_type, redirect_uri, client_id=client_id)

    server = _CallbackHTTPServer(port)

    # Run the HTTP server in a daemon thread so it can handle requests
    # while the main thread waits for the callback event.
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print(f"Starting OAuth pre-check server on http://127.0.0.1:{port}")
    print(f"Callback URL: {redirect_uri}")
    print()
    print("Opening browser for OAuth authorization...")
    print(f"If the browser does not open automatically, visit:\n  {oauth_url}")
    print()

    webbrowser.open(oauth_url)

    # Block until the callback is received or the user interrupts
    try:
        server.callback_received.wait()
    except KeyboardInterrupt:
        print("\nPre-check cancelled by user.")
        return 1
    finally:
        server.shutdown()
        server.server_close()

    if server.precheck_error:
        print(f"\n✗ Pre-check failed: {server.precheck_error}")
        return 1

    print("\n✓ Pre-check passed! You can connect via local static credentials.")
    return 0
