from __future__ import annotations

import httpx

from .auth import EbayTokenManager, EbayUserTokenManager


class EbayBrowseClient:
    def __init__(
        self,
        token_manager: EbayTokenManager,
        marketplace_id: str,
        base_url: str,
    ) -> None:
        self._token_manager = token_manager
        self._marketplace_id = marketplace_id
        self._base_url = base_url
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._token_manager.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self._marketplace_id,
        }

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_price: float | None = None,
        max_price: float | None = None,
        condition: str | None = None,
    ) -> dict:
        params: dict[str, str | int] = {
            "q": query,
            "limit": min(limit, 200),
        }

        filters: list[str] = []
        if min_price is not None and max_price is not None:
            filters.append(f"price:[{min_price}..{max_price}],priceCurrency:USD")
        elif min_price is not None:
            filters.append(f"price:[{min_price}..],priceCurrency:USD")
        elif max_price is not None:
            filters.append(f"price:[..{max_price}],priceCurrency:USD")

        if condition is not None:
            normalized = condition.upper()
            if normalized in ("NEW", "USED", "UNSPECIFIED"):
                filters.append(f"conditions:{{{normalized}}}")

        if filters:
            params["filter"] = ",".join(filters)

        response = await self._http.get(
            f"{self._base_url}/buy/browse/v1/item_summary/search",
            params=params,
            headers=await self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def get_item(self, item_id: str) -> dict:
        response = await self._http.get(
            f"{self._base_url}/buy/browse/v1/item/{item_id}",
            headers=await self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._http.aclose()


class EbayTradingClient:
    """Uses eBay Trading API (SOAP) with user OAuth token to fetch buyer orders."""

    _TRADING_URL = "https://api.ebay.com/ws/api.dll"
    _COMPAT_LEVEL = "967"

    def __init__(self, user_token_manager: "EbayUserTokenManager", site_id: str = "0") -> None:
        self._user_token_manager = user_token_manager
        self._site_id = site_id
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _headers(self, call_name: str) -> dict[str, str]:
        token = await self._user_token_manager.get_token()
        return {
            "X-EBAY-API-SITEID": self._site_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": self._COMPAT_LEVEL,
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-IAF-TOKEN": token,
            "Content-Type": "text/xml",
        }

    async def get_orders(self, days_back: int = 60, page: int = 1) -> str:
        """Returns raw XML response string from GetOrders Trading API call."""
        from datetime import datetime, timezone, timedelta
        create_time_from = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials/>
  <CreateTimeFrom>{create_time_from}</CreateTimeFrom>
  <CreateTimeTo>{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}</CreateTimeTo>
  <OrderRole>Buyer</OrderRole>
  <OrderStatus>All</OrderStatus>
  <Pagination>
    <EntriesPerPage>25</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
</GetOrdersRequest>"""
        response = await self._http.post(
            self._TRADING_URL,
            headers=await self._headers("GetOrders"),
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        return response.text

    async def close(self) -> None:
        await self._http.aclose()
