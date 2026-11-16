# Changelog

## Unreleased

Configuration
- Every option now explains each value in the Home Assistant UI (German and English), e.g.
  which tools each area contains.
- New option `keep_downloads_days` (default 7): downloaded FIT/GPX files are deleted after
  that many days. Downloads are no longer part of Home Assistant backups.
- New option `login_notification` (default on) to switch off the notification about login problems.
- `public_url` accepts a copied browser address (only scheme and host are used); the app page
  warns if it is invalid or uses `http://`.
- Typos in `enable_tools` / `disable_tools` are shown as a warning on the app page.
- Area `workouts` now includes `push_workout_to_device` and `reschedule_workout` (still subject
  to `write_access`) – previously workouts could not be sent to the watch without `enable_tools`.
- Texts use the current Home Assistant term "app" instead of "add-on".
- Security: the app page is never cached, sends no referrer and can only be embedded by Home Assistant.

- Security: nginx could write the secret path to the add-on log when the server was not
  reachable for a moment (e.g. during a restart). nginx now only logs critical errors.
  If you shared your add-on log, generate a new secret URL.
- Security: file tools (`upload_course`, `download_course_gpx`, `download_activity_file`,
  `set_fit_download_dir`) can only read and write inside the add-on's download folder.
  Before, an AI could upload any readable file (e.g. from the Home Assistant config folder)
  as a course or write files into it.
- Security: the MCP server no longer receives the Home Assistant Supervisor token or any
  other secret from the environment.
- Security: files with secrets (secret URL, webhook ID, Garmin account, tool selection) are
  written atomically and readable only by the add-on.
- Security: at most 5 login attempts per 15 minutes; a half-finished 2FA login expires.
- Stability: if the Garmin login fails temporarily (e.g. Garmin down), the server retries
  automatically with growing pauses; the notification only appears if it keeps failing.
- Stability: all Python dependencies are pinned, so a rebuild produces the same image.

- Automated tests for every change: unit tests (tool protection, selection, texts, helper
  integration) and a smoke test of the built image.
- New release process: images are published before the version number changes, so Home
  Assistant never offers an update whose image is not available yet.
- Weekly check for new versions of the Garmin server; Dependabot keeps build tools up to date.
- SECURITY.md and issue templates.

## 0.3.0

Fixes
- Tool protection now covers every tool the server registers. Tools without an access
  classification (e.g. added by a future server update) count as change/delete and are never
  enabled by `read_only` or `create_only`.
- Messages to the AI no longer point to the `garmin-mcp-auth` command line tool; when the
  Garmin login is invalid they ask the user to log in again on the add-on page.
- Home Assistant notification when the Garmin login stops working (dismissed automatically
  after logging in again).

Changes
- Requires Home Assistant 2026.2 or newer; marked as experimental until 1.0.
- `log_level` now also applies to the MCP server (per-request lines only with `debug`).
- Consistent wording "change/delete"; docs explain that logging out does not revoke tokens at Garmin.

New
- "Test connection": checks the server, the Garmin login and the connector URL from the internet.
- Health check: the add-on is restarted if its web UI stops answering.
- Add-on version and documentation link on the add-on page.
- After updates, new tools are switched off in a saved selection and marked "new".

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
