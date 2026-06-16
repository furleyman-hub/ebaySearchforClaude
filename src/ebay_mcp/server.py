from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .auth import EbayTokenManager, EbayUserTokenManager
from .ebay_client import EbayBrowseClient, EbayOrderClient
from .formatters import format_item_detail, format_order_detail, format_orders, format_search_results
from .oauth import PersonalOAuthProvider

load_dotenv()

_REQUIRED_VARS = ["EBAY_APP_ID", "EBAY_CERT_ID"]
for _var in _REQUIRED_VARS:
    if not os.getenv(_var):
        raise EnvironmentError(f"Missing required environment variable: {_var}")

_BASE_URLS = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}

_env = os.getenv("EBAY_ENVIRONMENT", "production").lower()
_base_url = _BASE_URLS.get(_env, _BASE_URLS["production"])
_marketplace_id = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")

_token_manager: EbayTokenManager | None = None
_client: EbayBrowseClient | None = None
_user_token_manager: EbayUserTokenManager | None = None
_order_client: EbayOrderClient | None = None


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[None]:
    global _token_manager, _client, _user_token_manager, _order_client
    _token_manager = EbayTokenManager(
        app_id=os.environ["EBAY_APP_ID"],
        cert_id=os.environ["EBAY_CERT_ID"],
        base_url=_base_url,
    )
    _client = EbayBrowseClient(_token_manager, _marketplace_id, _base_url)
    _user_token_manager = EbayUserTokenManager(
        app_id=os.environ["EBAY_APP_ID"],
        cert_id=os.environ["EBAY_CERT_ID"],
        ru_name=os.getenv("EBAY_RU_NAME", ""),
        base_url=_base_url,
    )
    _order_client = EbayOrderClient(_user_token_manager, _base_url)
    try:
        yield
    finally:
        if _client:
            await _client.close()


_server_url = os.getenv("SERVER_URL", "https://ebaysearchforclaude-production.up.railway.app")

mcp = FastMCP(
    "ebay-browse",
    lifespan=lifespan,
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8000")),
    auth_server_provider=PersonalOAuthProvider(
        static_client_id=os.getenv("OAUTH_CLIENT_ID"),
        static_client_secret=os.getenv("OAUTH_CLIENT_SECRET"),
    ),
    auth=AuthSettings(
        issuer_url=_server_url,
        resource_server_url=_server_url,
    ),
)


async def ebay_callback(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    if error:
        desc = request.query_params.get("error_description", error)
        return HTMLResponse(f"<h1>Access denied</h1><p>{desc}</p><p>You can close this tab.</p>", status_code=200)
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h1>Error: no code received</h1>", status_code=400)
    if _user_token_manager is None:
        return HTMLResponse("<h1>Server not ready</h1>", status_code=503)
    try:
        await _user_token_manager.exchange_code(code)
        return HTMLResponse("<h1>eBay account connected!</h1><p>You can close this tab and return to Claude.</p>")
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{e}</p>", status_code=500)


mcp._custom_starlette_routes.append(Route("/ebay/callback", endpoint=ebay_callback, methods=["GET"]))


@mcp.tool()
async def ebay_get_auth_url() -> str:
    """Get the eBay authorization URL to connect your eBay account.
    Visit this URL in your browser, log in to eBay, and approve access.
    After approval eBay will redirect you — copy the full redirect URL or just the 'code' parameter and pass it to ebay_connect.
    """
    assert _user_token_manager is not None
    return _user_token_manager.get_auth_url()


@mcp.tool()
async def ebay_connect(code: str) -> str:
    """Connect your eBay account by providing the authorization code from the eBay redirect.
    Get the code by first calling ebay_get_auth_url and completing the authorization flow.
    """
    assert _user_token_manager is not None
    if "?" in code:
        from urllib.parse import urlparse, parse_qs
        parsed = parse_qs(urlparse(code).query)
        code = parsed.get("code", [code])[0]
    try:
        await _user_token_manager.exchange_code(code)
        return json.dumps({"status": "connected", "message": "eBay account connected successfully."})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def ebay_get_orders(limit: int = 20, days_back: int = 90) -> str:
    """List your recent eBay purchases with shipping and delivery status.
    Returns order IDs, items, prices, and tracking information.
    """
    if _user_token_manager is None or not _user_token_manager.is_connected():
        return json.dumps({"error": "eBay account not connected. Call ebay_get_auth_url to start the connection flow."})
    assert _order_client is not None
    try:
        raw = await _order_client.get_orders(limit, days_back)
        return json.dumps(format_orders(raw), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def ebay_get_order(order_id: str) -> str:
    """Get full details for a specific eBay order including tracking numbers and delivery status."""
    if _user_token_manager is None or not _user_token_manager.is_connected():
        return json.dumps({"error": "eBay account not connected. Call ebay_get_auth_url to start the connection flow."})
    assert _order_client is not None
    try:
        raw = await _order_client.get_order(order_id)
        return json.dumps(format_order_detail(raw), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def ebay_search(
    query: str,
    limit: int = 10,
    min_price: float | None = None,
    max_price: float | None = None,
    condition: str | None = None,
) -> str:
    """Search eBay listings by keyword.

    Returns structured JSON with title, price, condition, seller info, and item URL.
    condition can be 'new', 'used', or omitted for all.
    """
    assert _client is not None
    try:
        raw = await _client.search(query, limit, min_price, max_price, condition)
        return json.dumps(format_search_results(raw), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def ebay_get_item(item_id: str) -> str:
    """Fetch full details for a specific eBay listing by item ID.

    Returns price, shipping options, return policy, item specifics (brand, model, etc.),
    categories, description, and seller info.
    """
    assert _client is not None
    if item_id.isdigit():
        item_id = f"v1|{item_id}|0"
    try:
        raw = await _client.get_item(item_id)
        return json.dumps(format_item_detail(raw), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
