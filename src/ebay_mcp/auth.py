from __future__ import annotations

import asyncio
import base64
import json
import time
from urllib.parse import quote

import httpx

_USER_SCOPES = "https://api.ebay.com/oauth/api_scope/buy.order.readonly"


class EbayUserTokenManager:
    def __init__(
        self,
        app_id: str,
        cert_id: str,
        ru_name: str,
        base_url: str,
        token_file: str = "/tmp/ebay_user_token.json",
    ) -> None:
        self._app_id = app_id
        self._cert_id = cert_id
        self._ru_name = ru_name
        self._base_url = base_url
        self._token_file = token_file
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        try:
            self._load()
        except Exception:
            pass

    def get_auth_url(self, state: str = "") -> str:
        scope_encoded = quote(_USER_SCOPES, safe="")
        return (
            f"https://auth.ebay.com/oauth2/authorize"
            f"?client_id={self._app_id}"
            f"&redirect_uri={self._ru_name}"
            f"&response_type=code"
            f"&scope={scope_encoded}"
            f"&state={state}"
        )

    def _credentials(self) -> str:
        return base64.b64encode(f"{self._app_id}:{self._cert_id}".encode()).decode()

    async def exchange_code(self, code: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {self._credentials()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content=f"grant_type=authorization_code&code={code}&redirect_uri={self._ru_name}",
            )
        if response.status_code != 200:
            raise RuntimeError(f"eBay token exchange failed ({response.status_code}): {response.text}")
        data = response.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expires_at = time.time() + int(data.get("expires_in", 7200))
        self._save()

    async def get_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        await self._do_refresh()
        return self._access_token  # type: ignore[return-value]

    async def _do_refresh(self) -> None:
        async with self._lock:
            if self._access_token and time.time() < self._expires_at - 60:
                return
            if not self._refresh_token:
                raise RuntimeError("No refresh token available; please reconnect your eBay account.")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/identity/v1/oauth2/token",
                    headers={
                        "Authorization": f"Basic {self._credentials()}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content=f"grant_type=refresh_token&refresh_token={self._refresh_token}&scope={quote(_USER_SCOPES, safe='')}",
                )
            if response.status_code != 200:
                raise RuntimeError(f"eBay token refresh failed ({response.status_code}): {response.text}")
            data = response.json()
            self._access_token = data["access_token"]
            self._expires_at = time.time() + int(data.get("expires_in", 7200))
            self._save()

    def _save(self) -> None:
        with open(self._token_file, "w") as f:
            json.dump({
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._expires_at,
            }, f)

    def _load(self) -> None:
        with open(self._token_file) as f:
            data = json.load(f)
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        self._expires_at = float(data.get("expires_at", 0))

    def is_connected(self) -> bool:
        return bool(self._refresh_token)


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
