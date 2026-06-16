from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .auth import EbayTokenManager
from .ebay_client import EbayBrowseClient
from .formatters import format_item_detail, format_search_results

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


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[None]:
    global _token_manager, _client
    _token_manager = EbayTokenManager(
        app_id=os.environ["EBAY_APP_ID"],
        cert_id=os.environ["EBAY_CERT_ID"],
        base_url=_base_url,
    )
    _client = EbayBrowseClient(_token_manager, _marketplace_id, _base_url)
    try:
        yield
    finally:
        if _client:
            await _client.close()


mcp = FastMCP("ebay-browse", lifespan=lifespan)


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
    try:
        raw = await _client.get_item(item_id)
        return json.dumps(format_item_detail(raw), indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def main() -> None:
    mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
