# Changelog

## Unreleased

- Improved: names only from the second account on – with a single account the app page
  and Home Assistant show no name (device again “Garmin Connect MCP”).
- Improved: adding, renaming or removing an account no longer reloads the helper
  integration – the switches of the other accounts stay untouched (before, their
  “last changed” was reset, which could trigger automations).
- Improved: **Remove account** names the account in its question; the page points out when
  the same Garmin account is logged in twice; the note on “Upload device data” is shown
  once instead of in every card.
- Helper integration 0.6.0, so Home Assistant asks for one restart.

---

- Verbessert: Namen erst ab dem zweiten Konto – mit nur einem Konto zeigen App-Seite und
  Home Assistant keinen Namen (Gerät wieder „Garmin Connect MCP“).
- Verbessert: Hinzufügen, Umbenennen oder Entfernen eines Kontos lädt die
  Hilfs-Integration nicht mehr neu – die Schalter der anderen Konten bleiben unberührt
  (bisher wurde ihr „Zuletzt geändert“ zurückgesetzt, was Automationen auslösen konnte).
- Verbessert: **Konto entfernen** nennt das Konto in der Rückfrage; die Seite weist darauf
  hin, wenn dasselbe Garmin-Konto zweimal angemeldet ist; der Hinweis zu „Gerätedaten
  hochladen“ steht einmal statt auf jeder Karte.
- Hilfs-Integration 0.6.0, daher bittet Home Assistant einmal um einen Neustart.

## 0.6.0

- New: **several Garmin accounts** in one app – up to 10, e.g. the whole household. Every
  account has its own Garmin login, connector URL, connection test, device and switch in
  Home Assistant and repair notice, and its own Garmin server running as its own
  unprivileged user (no account can read another one's tokens). Name from the Garmin
  profile, changeable with ✏️. From the 4th account the page warns about the load.
- New: **Same settings for all accounts** (default) – or write access, areas and tools per
  account.
- Updating: your existing login becomes the first account – same connector URL, same switch
  (`switch.garmin_connect_mcp_server`). Helper integration 0.5.0, so Home Assistant asks for
  one restart. Note: every Home Assistant administrator sees all accounts on the app page.

---

- Neu: **mehrere Garmin-Konten** in einer App – bis zu 10, z. B. der ganze Haushalt. Jedes
  Konto hat eine eigene Garmin-Anmeldung, Connector-URL, einen eigenen Verbindungstest,
  ein eigenes Gerät mit Schalter und einen eigenen Reparatur-Hinweis in Home Assistant
  sowie einen eigenen Garmin-Server, der als eigener eingeschränkter Benutzer läuft (kein
  Konto kann die Tokens eines anderen lesen). Name aus dem Garmin-Profil, mit ✏️
  änderbar. Ab dem 4. Konto weist die Seite auf die Last hin.
- Neu: **Gleiche Einstellungen für alle Konten** (Standard) – oder Schreibrechte, Bereiche
  und Tools pro Konto.
- Update: Deine bestehende Anmeldung wird das erste Konto – gleiche Connector-URL, gleicher
  Schalter (`switch.garmin_connect_mcp_server`). Hilfs-Integration 0.5.0, daher bittet Home
  Assistant einmal um einen Neustart. Hinweis: Jeder Administrator in Home Assistant sieht
  auf der App-Seite alle Konten.

## 0.5.6

- Improved: the German documentation is now shown in Home Assistant too – the
  *Documentation* tab and the app store description contain English and German (Home
  Assistant can only show one file each). The *Documentation* link on the app page jumps
  to your language.

---

- Verbessert: Die deutsche Anleitung erscheint jetzt auch in Home Assistant – der Reiter
  *Dokumentation* und die Beschreibung im App-Store enthalten Englisch und Deutsch (Home
  Assistant kann jeweils nur eine Datei anzeigen). Der Link *Dokumentation* auf der App-Seite
  springt direkt zu deiner Sprache.

## 0.5.5

- Fixed: after reinstalling the app without restarting Home Assistant, the old helper
  integration could keep running (e.g. without the new switch) and neither the app page nor
  Home Assistant asked for a restart. The helper now reports the version of the code that
  is actually running, so the restart notice appears right away. Helper integration 0.4.1.
- Docs: Landlock is used only where the Linux kernel offers it – Home Assistant OS
  currently does not (the log line "Landlock is not available here" is expected); the
  unprivileged user and the AppArmor profile always apply.

---

- Behoben: Nach einer Neuinstallation der App ohne Neustart von Home Assistant konnte die
  alte Hilfs-Integration weiterlaufen (z. B. ohne den neuen Schalter), ohne dass App-Seite
  oder Home Assistant einen Neustart verlangten. Die Hilfs-Integration meldet jetzt die
  Version des Codes, der tatsächlich läuft – der Neustart-Hinweis erscheint sofort.
  Hilfs-Integration 0.4.1.
- Anleitung: Landlock wird nur genutzt, wo der Linux-Kernel es anbietet – Home Assistant OS
  tut das derzeit nicht (die Protokollzeile „Landlock is not available here“ ist erwartet);
  eingeschränkter Benutzer und AppArmor-Profil gelten immer.

## 0.5.4

- The repository moved to its own address: `https://github.com/mw-hbg/ha-garmin-mcp`
  (one project per repository). **Existing installations:** keep the old repository
  address in Home Assistant – it forwards and updates keep arriving. Adding the new address
  in addition would install a second, separate app (new Garmin login and connector URL).
- New: switch **Garmin Connect MCP Server** in Home Assistant (device *Garmin Connect MCP*,
  webhook mode). Off means no AI app reaches your Garmin data – Home Assistant answers every
  request itself and the app stops its Garmin server; login and connector URL stay. A normal
  entity, so it also works in automations, dashboards and with voice assistants.
- Helper integration 0.4.0 (switch, links to the new address and the issue tracker). As with
  every update of the helper integration, Home Assistant asks for one restart (repair notice).
- Development: tests, release and checks now use the shared workflows of
  [mw-hbg/workflows](https://github.com/mw-hbg/workflows); release tags are now `v1.2.3`.

---

- Das Repository hat eine eigene Adresse: `https://github.com/mw-hbg/ha-garmin-mcp`
  (ein Projekt pro Repository). **Bestehende Installationen:** die alte Repository-Adresse in
  Home Assistant stehen lassen – sie wird weitergeleitet, Updates kommen weiter an. Die neue
  Adresse zusätzlich einzutragen, würde eine zweite, getrennte App installieren (neue
  Garmin-Anmeldung und Connector-URL).
- Neu: Schalter **Garmin Connect MCP Server** in Home Assistant (Gerät *Garmin Connect MCP*,
  Modus webhook). Aus heißt: keine KI-App erreicht deine Garmin-Daten – Home Assistant
  beantwortet jede Anfrage selbst und die App stoppt ihren Garmin-Server; Anmeldung und
  Connector-URL bleiben. Eine normale Entität, also auch für Automationen, Dashboards und
  Sprachassistenten.
- Hilfs-Integration 0.4.0 (Schalter, Links auf die neue Adresse und den Issue-Tracker). Wie bei
  jedem Update der Hilfs-Integration bittet Home Assistant einmal um einen Neustart
  (Reparatur-Hinweis).
- Entwicklung: Tests, Release und Prüfungen nutzen jetzt die gemeinsamen Workflows aus
  [mw-hbg/workflows](https://github.com/mw-hbg/workflows); Release-Tags heißen jetzt `v1.2.3`.

## 0.5.3

- Improved: if Garmin no longer accepts the login, the app page shows **Log in again** right
  away – no need to log out first. Settings and connector URL stay the same.
- Docs: how to connect Mistral Vibe (formerly Le Chat) – a free alternative to Claude; also
  tested with this app.

---

- Verbessert: Akzeptiert Garmin die Anmeldung nicht mehr, zeigt die App-Seite direkt **Neu
  anmelden** – vorher abmelden ist nicht mehr nötig. Einstellungen und Connector-URL bleiben
  gleich.
- Anleitung: So verbindest du Mistral Vibe (früher Le Chat) – eine kostenlose Alternative zu
  Claude, ebenfalls mit der App getestet.

## 0.5.2

- Fixed: the app page could keep showing "starting …" after logging in, although the
  server was already running. It now updates as soon as the status changes.
- Fixed: if Garmin rejects the login while the app is running (e.g. after changing the
  Garmin password), the app page now shows "login failed" and Home Assistant shows the
  repair notice. Before, only the AI app got an error message.

---

- Behoben: Die App-Seite zeigte nach dem Anmelden manchmal weiter „startet …“, obwohl der
  Server schon lief. Sie aktualisiert sich jetzt, sobald sich der Status ändert.
- Behoben: Lehnt Garmin die Anmeldung im laufenden Betrieb ab (z. B. nach einer Änderung des
  Garmin-Passworts), zeigt die App-Seite jetzt „Anmeldung fehlgeschlagen“ und Home Assistant
  den Reparatur-Hinweis. Vorher bekam nur die KI-App eine Fehlermeldung.

## 0.5.1

- Improved: when the app is not logged in to Garmin (or the login expired), the AI app now
  gets a clear message – "ask the user to open Garmin MCP in Home Assistant and log in" –
  instead of a bare "Service Unavailable".
- Development: the Raspberry Pi image (aarch64) is now built natively on GitHub's arm64
  runners instead of being emulated – releases take about 2 instead of 6 minutes, and the
  image test now also runs for the Raspberry Pi image.

---

- Verbessert: Ist die App nicht bei Garmin angemeldet (oder ist die Anmeldung abgelaufen),
  bekommt die KI-App jetzt eine verständliche Meldung – „bitte in Home Assistant unter Garmin
  MCP anmelden“ – statt nur „Service Unavailable“.
- Entwicklung: Das Raspberry-Pi-Image (aarch64) wird jetzt direkt auf den ARM-Rechnern von
  GitHub gebaut statt nachgeahmt – ein Release dauert etwa 2 statt 6 Minuten, und der
  Image-Test läuft jetzt auch für das Raspberry-Pi-Image.

## 0.5.0

- Security: the app now has its own AppArmor profile (security rating 8 of 8 in Home
  Assistant). The kernel limits every process of the app – including its internal part –
  to what it needs: in the Home Assistant configuration folder only its helper
  integration, no other programs than Python and nginx, no system changes.
- Fixed: the connection test failed with "HTTP 403" behind Cloudflare, because Cloudflare
  blocked its requests as a script. The test now identifies itself properly. If Cloudflare
  (or another proxy) still blocks it, this is shown as a note with a hint instead of an
  error – the AI app is usually not affected.

---

- Sicherheit: Die App hat jetzt ein eigenes AppArmor-Profil (Sicherheitsbewertung 8 von 8
  in Home Assistant). Der Kernel beschränkt jeden Prozess der App – auch ihren internen
  Teil – auf das Nötige: im Home-Assistant-Konfigurationsordner nur ihre
  Hilfs-Integration, keine anderen Programme als Python und nginx, keine Änderungen am
  System.
- Behoben: Der Verbindungstest schlug hinter Cloudflare mit „HTTP 403“ fehl, weil Cloudflare
  seine Anfragen als Skript blockiert hat. Der Test meldet sich jetzt mit einem richtigen
  Namen. Blockiert Cloudflare (oder ein anderer Proxy) trotzdem, erscheint das als Hinweis
  mit Lösungsvorschlag statt als Fehler – die KI-App ist davon meist nicht betroffen.

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
