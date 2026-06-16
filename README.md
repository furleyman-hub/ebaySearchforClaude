# eBay Search for Claude

An MCP (Model Context Protocol) server that gives Claude native access to the eBay Browse API. Claude can search for listings by keyword or look up a specific item by ID.

## Tools exposed to Claude

| Tool | Description |
|---|---|
| `ebay_search` | Search eBay by keyword with optional price range and condition filters |
| `ebay_get_item` | Fetch full details for a specific listing by item ID |

## Setup

### 1. Get eBay API credentials

Sign up at [developer.ebay.com](https://developer.ebay.com) and create an application to get your **App ID** and **Cert ID**.

### 2. Install dependencies

```bash
pip install -e .
```

### 3. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your EBAY_APP_ID and EBAY_CERT_ID
```

`.env` options:

```
EBAY_APP_ID=your-app-id-here
EBAY_CERT_ID=your-cert-id-here
EBAY_MARKETPLACE_ID=EBAY_US        # optional, defaults to EBAY_US
EBAY_ENVIRONMENT=production        # or 'sandbox' for testing
```

### 4. Use with Claude Code

The `.claude/settings.json` file in this repo already registers the MCP server. Open this directory in Claude Code and the `ebay_search` and `ebay_get_item` tools will be available automatically.

### 5. Use with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ebay": {
      "command": "python3",
      "args": ["-m", "ebay_mcp.server"],
      "cwd": "/path/to/ebaySearchforClaude",
      "env": {
        "PYTHONPATH": "/path/to/ebaySearchforClaude/src",
        "EBAY_APP_ID": "your-app-id",
        "EBAY_CERT_ID": "your-cert-id"
      }
    }
  }
}
```

## Example usage

Once configured, ask Claude:

- "Search eBay for vintage cameras under $200"
- "Find used iPhone 15 Pro listings on eBay"
- "Get details for eBay item 123456789"
- "What's the going price for a Leica M6 on eBay?"

## Project structure

```
src/ebay_mcp/
├── server.py       # MCP entry point, tool definitions
├── auth.py         # OAuth2 token manager with caching
├── ebay_client.py  # eBay Browse API HTTP client
└── formatters.py   # Shapes raw API responses for Claude
```
