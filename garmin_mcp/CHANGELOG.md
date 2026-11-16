# Changelog

## 0.1.0

- First release.
- MCP server: Taxuspt/garmin_mcp @ `a2ca5fc` (157 tools), Streamable HTTP, stateless.
- Garmin login in the add-on UI (ingress) with two-factor authentication; only tokens are stored.
- Secret-path protection via nginx, rotatable from the UI.
- Options: tool areas, write access level (`read_only` / `create_only` / `full`), per-tool allow and deny lists.
- English and German UI and option descriptions.
