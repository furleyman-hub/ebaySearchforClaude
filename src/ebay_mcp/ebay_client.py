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


class EbayOrderClient:
    def __init__(self, user_token_manager: EbayUserTokenManager, base_url: str) -> None:
        self._user_token_manager = user_token_manager
        self._base_url = base_url

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._user_token_manager.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Language": "en-US",
        }

    async def get_orders(self, limit: int = 20, days_back: int = 90) -> dict:
        from datetime import datetime, timezone, timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        iso_date = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/buy/order/v2/order",
                params={"limit": limit, "filter": f"creationdate:[{iso_date}..]"},
                headers=await self._auth_headers(),
            )
        response.raise_for_status()
        return response.json()

    async def get_order(self, order_id: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/buy/order/v2/order/{order_id}",
                headers=await self._auth_headers(),
            )
        response.raise_for_status()
        return response.json()
