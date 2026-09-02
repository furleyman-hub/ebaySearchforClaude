# eBay MCP Server — Project Context

## What This Is
A Python MCP (Model Context Protocol) server that wraps the eBay Browse API and exposes two tools to Claude:
- `ebay_search(query, limit, min_price, max_price, condition)` — keyword search
- `ebay_get_item(item_id)` — full listing details by ID

Deployed on Railway at `https://ebaysearchforclaude-production.up.railway.app`. Claude connects via OAuth 2.0 over HTTP (Streamable HTTP transport, endpoint at `/mcp`).

---

## Repository
- GitHub: `furleyman-hub/ebaySearchforClaude`
- Main branch: `main` (Railway deploys from this)
- Feature branch: `claude/ebay-search-tool-9qcb75` (active development)
- **Changes to the feature branch do NOT auto-deploy on Railway — must be merged to `main`**

---

## File Structure
```
src/ebay_mcp/
├── server.py      # FastMCP entry point: tools, lifespan, OAuth config
├── oauth.py       # PersonalOAuthProvider (in-memory OAuth 2.0 server)
├── auth.py        # EbayTokenManager (eBay client-credentials OAuth, with asyncio.Lock)
├── ebay_client.py # EbayBrowseClient: search() and get_item() via httpx
├── formatters.py  # format_search_results(), format_item_detail()
└── __init__.py

railway.toml       # build: pip install -e .  deploy: python3 -m ebay_mcp.server
pyproject.toml     # mcp>=1.27.0, httpx>=0.28.0, python-dotenv>=1.1.0
.claude/settings.json  # CLI MCP config: url = .../mcp
```

---

## Architecture

### Transport
- FastMCP 1.27.2, `transport="streamable-http"` — endpoint at `/mcp`
- Previously SSE (`/sse`) — switched to Streamable HTTP to fix Railway proxy 502s

### OAuth
`PersonalOAuthProvider` (in `oauth.py`) is a fully in-memory OAuth 2.0 authorization server:
- Supports both dynamic client registration AND a pre-registered static client
- `_PermissiveClient` subclass overrides `validate_redirect_uri` to accept any redirect URI (needed because claude.ai's callback URL isn't known at registration time)
- State is lost on server restart — claude.ai re-authenticates via refresh tokens automatically
- Static client credentials (set in Railway Variables AND claude.ai connector):
  - Client ID: `ebay-mcp-client`
  - Client Secret: `l0EGWxy73GHVqxSB2Pe0AojMjjc_DnwvREcgwgl_WCI`

### eBay API
- Client credentials flow: app-level token, no user auth needed
- Token cached in memory, refreshed 60s before expiry, protected by `asyncio.Lock`
- Production API: `https://api.ebay.com`

---

## Environment Variables (Railway → Variables tab)

| Variable | Value |
|---|---|
| `EBAY_APP_ID` | From eBay Developer account → My Keys |
| `EBAY_CERT_ID` | From eBay Developer account → My Keys |
| `OAUTH_CLIENT_ID` | `ebay-mcp-client` |
| `OAUTH_CLIENT_SECRET` | `l0EGWxy73GHVqxSB2Pe0AojMjjc_DnwvREcgwgl_WCI` |
| `SERVER_URL` | `https://ebaysearchforclaude-production.up.railway.app` |

**Do NOT manually set `PORT`** — Railway injects this automatically and routes to that value. If you override PORT in Variables with a different value than what Railway expects, you get 502.

---

## Claude.ai Connector Settings
Go to claude.ai → Settings → Integrations → Add MCP Server:
- **Server URL**: `https://ebaysearchforclaude-production.up.railway.app/mcp`
- **OAuth Client ID**: `ebay-mcp-client`
- **OAuth Client Secret**: `l0EGWxy73GHVqxSB2Pe0AojMjjc_DnwvREcgwgl_WCI`

---

## Current Status: 502 Bad Gateway

### Symptom
All HTTP endpoints return 502 in ~5ms despite Railway logs showing `Uvicorn running on http://0.0.0.0:8080`. Affected endpoints:
```
POST /mcp → 502 (5ms)
GET /.well-known/oauth-authorization-server → 502 (5ms)
GET /.well-known/oauth-protected-resource → 502 (5ms)
GET /authorize → 502 (5ms)
```

### "5ms 502" Diagnosis
502 in under 10ms means Railway's load balancer **cannot reach the backend at all** (connection refused). The server appears to start (Uvicorn log) but something prevents Railway from routing traffic to it.

### Most Likely Causes (in priority order)

1. **PORT mismatch** — If `PORT=8080` is manually set in Railway Variables, Railway might route to a different port than 8080. Fix: **Remove the `PORT` variable from Railway Variables** and let Railway inject it automatically.

2. **Railway deploying from wrong branch** — Railway is probably configured to deploy from `main`. The feature branch changes (`streamable-http` transport, `oauth.py`) need to be merged to `main`. Fix: Merge `claude/ebay-search-tool-9qcb75` into `main`.

3. **ASGI lifespan crash** — The Streamable HTTP session manager's lifespan (`session_manager.run()`) could be crashing silently after Uvicorn logs "running". Fix: Check Railway **application logs** (Python stdout, not HTTP request logs) for tracebacks.

### What Was Already Fixed
- Added `oauth.py` to the feature branch (it was missing, causing ImportError on startup)
- Switched from SSE to Streamable HTTP transport
- Added `SERVER_URL` env var to Railway

### Next Steps To Try
1. In Railway → Variables: **remove `PORT`** if it's manually set there
2. Merge feature branch to main: `git checkout main && git merge claude/ebay-search-tool-9qcb75 && git push`
3. Watch Railway **application logs** (not HTTP logs) for Python errors after "Uvicorn running"
4. If still failing: temporarily add a `GET /health` route returning 200 to test basic connectivity

---

## Development Notes

### Running locally
```bash
cp .env.example .env  # fill in EBAY_APP_ID, EBAY_CERT_ID
pip install -e .
python3 -m ebay_mcp.server
# Server at http://localhost:8000/mcp
```

### Key design decisions
- `asyncio.Lock` in `EbayTokenManager` prevents concurrent token refresh race conditions
- `_PermissiveClient.validate_redirect_uri` accepts any redirect URI so claude.ai's dynamic callback URL works
- `format_item_detail` keeps output lean (~5KB per item) to preserve Claude context window
- No persistent storage: tokens, OAuth state all in-memory — acceptable for personal single-user tool
