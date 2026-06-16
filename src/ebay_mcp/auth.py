import asyncio
import base64
import time

import httpx


class EbayTokenManager:
    def __init__(self, app_id: str, cert_id: str, base_url: str) -> None:
        self._app_id = app_id
        self._cert_id = cert_id
        self._base_url = base_url
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        await self._refresh_token()
        return self._access_token  # type: ignore[return-value]

    async def _refresh_token(self) -> None:
        async with self._lock:
            # Re-check inside lock in case another coroutine already refreshed
            if self._access_token and time.time() < self._token_expiry - 60:
                return

            credentials = base64.b64encode(
                f"{self._app_id}:{self._cert_id}".encode()
            ).decode()

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self._base_url}/identity/v1/oauth2/token",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content="grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
                )

            if response.status_code != 200:
                raise RuntimeError(
                    f"eBay OAuth failed ({response.status_code}): {response.text}"
                )

            data = response.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + int(data["expires_in"])
