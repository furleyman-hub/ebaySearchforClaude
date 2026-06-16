from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from mcp.server.auth.provider import AccessToken, AuthorizationParams, OAuthAuthorizationServerProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl


@dataclass
class _AuthCode:
    code: str
    client_id: str
    scopes: list[str]
    code_challenge: str
    redirect_uri: str | None
    redirect_uri_provided_explicitly: bool
    expires_at: float


@dataclass
class _RefreshToken:
    token: str
    client_id: str
    scopes: list[str]


class _PermissiveClient(OAuthClientInformationFull):
    """Client that accepts any redirect_uri (needed since we don't know claude.ai's URI in advance)."""

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            return redirect_uri
        if self.redirect_uris:
            return self.redirect_uris[0]
        raise ValueError("No redirect URI provided")


class PersonalOAuthProvider(
    OAuthAuthorizationServerProvider[_AuthCode, _RefreshToken, AccessToken]
):
    """
    In-memory OAuth 2.0 provider that auto-approves all clients.
    Supports both dynamic client registration and a pre-configured static client
    (client_id / client_secret) for use with connectors that require pre-registration.
    State is lost on restart; clients re-authenticate via refresh tokens automatically.
    """

    def __init__(
        self,
        static_client_id: str | None = None,
        static_client_secret: str | None = None,
    ) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, _AuthCode] = {}
        self._refresh_tokens: dict[str, _RefreshToken] = {}
        self._access_tokens: dict[str, AccessToken] = {}

        if static_client_id:
            self._clients[static_client_id] = _PermissiveClient(
                client_id=static_client_id,
                client_secret=static_client_secret,
                redirect_uris=["https://claude.ai"],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                token_endpoint_auth_method="client_secret_post",
            )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Wrap dynamically registered clients as permissive too
        permissive = _PermissiveClient(
            **client_info.model_dump(),
        )
        self._clients[client_info.client_id] = permissive

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = _AuthCode(
            code=code,
            client_id=client.client_id,
            scopes=params.scopes or [],
            code_challenge=params.code_challenge,
            redirect_uri=str(params.redirect_uri) if params.redirect_uri else None,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            expires_at=time.time() + 600,
        )
        redirect = str(params.redirect_uri)
        sep = "&" if "?" in redirect else "?"
        url = f"{redirect}{sep}code={code}"
        if params.state:
            url += f"&state={params.state}"
        return url

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> _AuthCode | None:
        code = self._auth_codes.get(authorization_code)
        if code and code.expires_at > time.time():
            return code
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: _AuthCode
    ) -> OAuthToken:
        self._auth_codes.pop(authorization_code.code, None)

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )
        self._refresh_tokens[refresh_token] = _RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            refresh_token=refresh_token,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> _RefreshToken | None:
        return self._refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: _RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        new_token = secrets.token_urlsafe(32)
        self._access_tokens[new_token] = AccessToken(
            token=new_token,
            client_id=client.client_id,
            scopes=refresh_token.scopes,
        )
        return OAuthToken(
            access_token=new_token,
            token_type="Bearer",
            refresh_token=refresh_token.token,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self._access_tokens.get(token)

    async def revoke_token(
        self, token: AccessToken | _RefreshToken
    ) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        else:
            self._refresh_tokens.pop(token.token, None)
