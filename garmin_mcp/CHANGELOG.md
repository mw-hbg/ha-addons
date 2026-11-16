# Changelog

## 0.4.2

- The repository is now ready for more apps: tests, image builds and releases work for
  every app folder automatically. When releasing, you choose the app; tags are now named
  `garmin_mcp-v<version>` (earlier tags keep their names).
- Development: tests and the documentation script moved into the app folder
  (`garmin_mcp/tests`, `garmin_mcp/scripts`). Nothing changes for users.

---

- Das Repository ist jetzt für weitere Apps vorbereitet: Tests, Images und Releases
  funktionieren automatisch für jeden App-Ordner. Beim Veröffentlichen wählst du die App
  aus; Tags heißen jetzt `garmin_mcp-v<Version>` (frühere Tags behalten ihren Namen).
- Entwicklung: Tests und das Skript für die Anleitung liegen jetzt im App-Ordner
  (`garmin_mcp/tests`, `garmin_mcp/scripts`). Für Nutzer ändert sich nichts.

## 0.4.1

- Fixed: the app page reloaded itself every few seconds while remote access was being set
  up, so you could not log in. It now only reloads when the status actually changes and
  never while you are typing.
- Fixed: after the helper integration was updated, the app page now asks for the Home
  Assistant restart right away.
- Docs: the first restart after installing is announced only on the app page, not as a
  Home Assistant notification.

---

- Behoben: Die App-Seite lud sich alle paar Sekunden neu, solange der Fernzugriff
  eingerichtet wurde – dadurch konnte man sich nicht anmelden. Sie lädt jetzt nur neu, wenn
  sich der Status wirklich ändert, und nie, während du etwas eintippst.
- Behoben: Nach einem Update der Hilfs-Integration fordert die App-Seite den Neustart von
  Home Assistant jetzt sofort an.
- Anleitung: Den ersten Neustart nach der Installation kündigt nur die App-Seite an, nicht
  Home Assistant per Benachrichtigung.

## 0.4.0

**After updating:** restart Home Assistant once (the app page and a repair notice ask for it)
and generate a new secret URL on the app page (**Generate new secret URL**), then replace it
in your AI app.

Security
- The app no longer has any access to the Home Assistant API. The helper integration is
  set up through the Supervisor's official discovery service; Home Assistant removes it
  by itself when the app is uninstalled. Notices (restart required, Garmin login invalid)
  now come from the integration as repair notices; the restart button on the app page is
  gone (use *Settings → System → Restart* or the repair notice).
- The MCP server additionally locks itself in with Linux Landlock: it can only reach its
  own folders and can no longer even read the Home Assistant configuration folder.
- The internet-facing MCP server now runs as an unprivileged user. Even if the Garmin
  server had a vulnerability, it could not write to the Home Assistant configuration
  folder, read the app's secrets or use the app page – only its tokens and downloads
  are writable for it.
- The app page only answers Home Assistant (ingress); the container itself only gets the
  health check.
- File tools (`upload_course`, `download_course_gpx`, `download_activity_file`,
  `set_fit_download_dir`) can only read and write inside the app's download folder. Before,
  an AI could upload any readable file (e.g. from the Home Assistant config folder) as a
  course or write files into it.
- The MCP server no longer receives the Home Assistant Supervisor token or any other secret.
- nginx could write the secret path to the app log when the server was briefly unreachable
  (e.g. during a restart). nginx now only logs critical errors.
- Files with secrets (secret URL, webhook ID, Garmin account, tool selection) are written
  atomically and are readable only by the app.
- At most 5 login attempts per 15 minutes; a half-finished 2FA login expires.
- The app page is never cached, sends no referrer and can only be embedded by Home Assistant.

Stability
- If the Garmin login fails temporarily (e.g. no internet after a power cut, Garmin down),
  the app retries by itself with growing pauses; the repair notice only appears if it keeps failing.
- All Python dependencies are pinned, so every build produces the same app.

Configuration
- Every option explains each value in the Home Assistant UI (English and German), e.g. which
  tools each area contains.
- New option `keep_downloads_days` (default 7): downloaded FIT/GPX files are deleted after that
  many days. Downloads are no longer part of Home Assistant backups.
- New option `login_notification` (default on) to switch off the repair notice about login problems.
- `public_url` accepts a copied browser address (only scheme and host are used); the app page
  warns if it is invalid or uses `http://`.
- Typos in `enable_tools` / `disable_tools` are shown as a warning on the app page.
- Area `workouts` now includes `push_workout_to_device` and `reschedule_workout` (still subject
  to `write_access`) – before, workouts could not be sent to the watch without `enable_tools`.

Uninstalling
- Uninstalling the app now also removes its helper integration: Home Assistant removes the
  entry by itself, the integration then deletes its files and shows a notification (no
  restart needed). If Home Assistant was off during the uninstall, the integration notices
  it within 10–20 minutes after the next start. Nothing is removed while the app is only
  stopped.

Languages
- Everything is available in English and German: app page, configuration, repair notices
  and documentation (`DOCS.de.md`). The page follows the browser language (otherwise the
  Home Assistant language) and can be switched at the bottom of the page. Notices use the
  Home Assistant language instead of showing both languages.
- New languages can be added without code changes – see `TRANSLATING.md`.

Other
- Called "app" everywhere, like Home Assistant since 2026.2 – including
  the repository (now `https://github.com/mw-hbg/ha-apps`; the old address forwards) and
  the image names. The helper integration was updated (version 0.3.0), hence the one-time
  restart.
- Automated tests for every change and a test run of the built app; new release process that
  publishes the app before Home Assistant offers the update; weekly check for new versions of
  the Garmin server; SECURITY.md and issue templates.

## 0.3.0

Fixes
- Tool protection now covers every tool the server registers. Tools without an access
  classification (e.g. added by a future server update) count as change/delete and are never
  enabled by `read_only` or `create_only`.
- Messages to the AI no longer point to the `garmin-mcp-auth` command line tool; when the
  Garmin login is invalid they ask the user to log in again on the app page.
- Home Assistant notification when the Garmin login stops working (dismissed automatically
  after logging in again).

Changes
- Requires Home Assistant 2026.2 or newer; marked as experimental until 1.0.
- `log_level` now also applies to the MCP server (per-request lines only with `debug`).
- Consistent wording "change/delete"; docs explain that logging out does not revoke tokens at Garmin.

New
- "Test connection": checks the server, the Garmin login and the connector URL from the internet.
- Health check: the app is restarted if its web UI stops answering.
- App version and documentation link on the app page.
- After updates, new tools are switched off in a saved selection and marked "new".

## 0.2.3

- Switching remote access to `direct` now cleans up: on the next start the app removes its
  helper integration from Home Assistant (config entry, files) by itself – no restart needed.
- README: new section on the two remote access modes, how to set up `direct` and what happens
  when switching later; explanation why the helper integration exists.

## 0.2.2

- New page "Choose tools": all tools grouped by category with search, presets (read only /
  create, never delete / everything / nothing), a checkbox per tool and an info box explaining
  what it does and what kind of access it needs. A saved selection replaces the tool options
  from the configuration (can be reset).
- The app page shows per category what the AI may do (read / create / change-delete) and
  links to the tool selection and to the app configuration.
- German descriptions for all tools.

- The app page refreshes itself every few seconds while the server is starting, so the
  status switches to "Ready" without reloading by hand.

## 0.2.1

- Fix: remote access failed to start ("Unexpected method: DELETE"); Home Assistant webhooks
  only accept GET, HEAD, POST and PUT.
- After an update of the helper integration the app page now asks for the required
  Home Assistant restart instead of retrying the old code.
- Restart required? A banner at the top of the app page now says so, and after updates of
  the helper integration Home Assistant shows a repair notice with a restart button (like HACS).
- Login: the button shows "Please wait …" while Garmin is contacted (can take up to 30 s);
  repeated clicks no longer trigger repeated logins (Garmin rate-limits those).
- Hints on the app page and in the docs: Garmin upload consent ("Upload device data"),
  two-factor authentication, and the sign-in prompt that appears when ha-mcp is installed.

## 0.2.0

- New default: remote access through your existing Home Assistant address via a webhook –
  no extra hostname, tunnel or port forwarding needed. Works with Nabu Casa, Cloudflare Tunnel
  and reverse proxies.
- The app installs a small helper integration (`garmin_mcp_webhook`) and asks for one
  Home Assistant restart (button on the app page).
- New option `remote_access` (`webhook` / `direct`). The previous behaviour is `direct`.
- "Generate new secret URL" now also renews the webhook id.

## 0.1.0

- First release.
- MCP server: Taxuspt/garmin_mcp @ `a2ca5fc` (157 tools), Streamable HTTP, stateless.
- Garmin login in the app UI (ingress) with two-factor authentication; only tokens are stored.
- Secret-path protection via nginx, rotatable from the UI.
- Options: tool areas, write access level (`read_only` / `create_only` / `full`), per-tool allow and deny lists.
- English and German UI and option descriptions.
