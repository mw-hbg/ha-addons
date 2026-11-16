# Changelog

## 0.2.3

- Switching remote access to `direct` now cleans up: on the next start the add-on removes its
  helper integration from Home Assistant (config entry, files) by itself – no restart needed.
- README: new section on the two remote access modes, how to set up `direct` and what happens
  when switching later; explanation why the helper integration exists.

## 0.2.2

- New page "Choose tools": all tools grouped by category with search, presets (read only /
  create, never delete / everything / nothing), a checkbox per tool and an info box explaining
  what it does and what kind of access it needs. A saved selection replaces the tool options
  from the configuration (can be reset).
- The add-on page shows per category what the AI may do (read / create / change-delete) and
  links to the tool selection and to the add-on configuration.
- German descriptions for all tools.

- The add-on page refreshes itself every few seconds while the server is starting, so the
  status switches to "Ready" without reloading by hand.

## 0.2.1

- Fix: remote access failed to start ("Unexpected method: DELETE"); Home Assistant webhooks
  only accept GET, HEAD, POST and PUT.
- After an update of the helper integration the add-on page now asks for the required
  Home Assistant restart instead of retrying the old code.
- Restart required? A banner at the top of the add-on page now says so, and after updates of
  the helper integration Home Assistant shows a repair notice with a restart button (like HACS).
- Login: the button shows "Please wait …" while Garmin is contacted (can take up to 30 s);
  repeated clicks no longer trigger repeated logins (Garmin rate-limits those).
- Hints on the add-on page and in the docs: Garmin upload consent ("Upload device data"),
  two-factor authentication, and the sign-in prompt that appears when ha-mcp is installed.

## 0.2.0

- New default: remote access through your existing Home Assistant address via a webhook –
  no extra hostname, tunnel or port forwarding needed. Works with Nabu Casa, Cloudflare Tunnel
  and reverse proxies.
- The add-on installs a small helper integration (`garmin_mcp_webhook`) and asks for one
  Home Assistant restart (button on the add-on page).
- New option `remote_access` (`webhook` / `direct`). The previous behaviour is `direct`.
- "Generate new secret URL" now also renews the webhook id.

## 0.1.0

- First release.
- MCP server: Taxuspt/garmin_mcp @ `a2ca5fc` (157 tools), Streamable HTTP, stateless.
- Garmin login in the add-on UI (ingress) with two-factor authentication; only tokens are stored.
- Secret-path protection via nginx, rotatable from the UI.
- Options: tool areas, write access level (`read_only` / `create_only` / `full`), per-tool allow and deny lists.
- English and German UI and option descriptions.
