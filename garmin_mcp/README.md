# Garmin Connect MCP – Home Assistant app

[English](#english) · [Deutsch](#deutsch)

## English

Let AI assistants such as **Claude** or **ChatGPT** read your Garmin Connect
training and health data – runs, splits, sleep, HRV, Body Battery, training
load – and create structured workouts that sync to your watch.

The app runs an [MCP](https://modelcontextprotocol.io) server inside your
Home Assistant, so your data goes straight from Garmin to your AI assistant
without any additional service in between.

> **Unofficial.** Not affiliated with or endorsed by Garmin. It uses the same
> private endpoints as the Garmin Connect website, which Garmin may change or
> block at any time. Use at your own risk.

> **Experimental** until version 1.0 – it works, but details may still change.

### Features

* **~157 tools** from [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp):
  activities, health, training metrics, workouts, courses, gear, nutrition, …
* **Login in the Home Assistant UI**, including two-factor authentication.
  Your password is never stored.
* **You decide what the AI may do:** read only, create without ever deleting,
  or full access – plus per-tool allow/deny lists.
* **No extra remote setup:** reachable through the address you already use for
  Home Assistant (Nabu Casa, Cloudflare Tunnel, reverse proxy …) via a webhook.
* **Several Garmin accounts** (up to 10, e.g. the whole household) – each with its own
  login, connector URL, rights and switch.
* **On/off switch in Home Assistant** per account – a normal switch entity, also for
  automations: off means no AI app reaches that data; login and connector URL stay.
* **Connection test** with one click – server, Garmin login and connector URL
  from the internet.
* **Repair notices** in Home Assistant when the Garmin login expired or an update of the
  helper integration needs a restart (the very first restart after installing is only
  shown on the app page).
* **No access to the Home Assistant API**, an AppArmor profile for the whole app
  (security rating 8/8) and the MCP server running as an unprivileged user (plus Linux Landlock where the kernel
  offers it) – nothing in Home Assistant can be changed from outside through this
  app.
* **Protected endpoint:** only reachable via a long random secret URL, which you
  can rotate with one click.
* **English and German** – app page, configuration, repair notices and documentation;
  more languages can be added without code ([TRANSLATING.md](TRANSLATING.md)).
* Works with any AI app that supports remote MCP servers (Streamable HTTP) – tested with
  Claude and Mistral Vibe, both usable for free.
* Pre-built images for `amd64` and `aarch64` (Raspberry Pi 4/5).

### Installation

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmw-hbg%2Fha-garmin-mcp)

1. *Settings → Apps → Install app → ⋮ → Repositories*, add
   `https://github.com/mw-hbg/ha-garmin-mcp`.
2. Install **Garmin Connect MCP** and start it.
3. **Restart Home Assistant once** (*Settings → System → Restart*). There is **no
   notification** for this first restart – only the app page shows the hint. The app
   has no access to the Home Assistant API, and its helper integration only runs after
   this restart. Later updates of the helper integration show a repair notice.
4. Open **Garmin MCP** in the sidebar and log in to Garmin Connect. *Remote access*
   should show **Active** about a minute after the restart.
5. Click **Test connection**, then add the connector URL shown on the app page to your
   AI assistant.

> **Moved:** this repository used to be `mw-hbg/ha-apps` (and before that
> `mw-hbg/ha-addons`). If you added one of the old addresses, **keep it** – GitHub
> forwards it and updates keep arriving. Do not add the new address in addition: Home
> Assistant would treat it as a different app, and you would have to log in to Garmin
> again and replace the connector URL.

Requirement: Home Assistant is already reachable from the internet over HTTPS (Nabu
Casa, Cloudflare Tunnel, reverse proxy …). No extra hostname or tunnel is needed.

Good to know:

* **Two-factor authentication** on your Garmin account is supported – the app
  asks for the code during login.
* **Workouts on your watch (EU accounts):** Garmin needs your consent to data
  uploads: Garmin Connect → *Settings → Privacy settings → Data → Upload device
  data* must be on.
* **Using ha-mcp too?** Your AI app may then ask you to log in to Home Assistant
  when adding the connector. That comes from ha-mcp and is harmless.

Full instructions: [DOCS.md](DOCS.md) (also shown in the
app's *Documentation* tab).

### Your data and security

* **What the AI reads goes to your AI provider.** When your AI assistant uses a tool,
  the result (e.g. sleep or heart rate data) is sent to that provider (Anthropic,
  OpenAI, …) and handled under its privacy terms. Only enable what you want to share:
  *Choose tools* on the app page, or the *Configuration* tab.
* **Write access is limited by default** (`create_only`): the AI may create and
  schedule workouts and add entries, but never delete or overwrite anything.
  `read_only` and `full` are available.
* **Treat the connector URL like a password.** Anyone who knows it can use the enabled
  tools. Don't share screenshots or logs that contain it; if it leaks, click
  **Generate new secret URL** on the app page.
* **Your Garmin password is never stored** – only the tokens Garmin issues after login
  (valid for about six months), kept in the app's private storage and in your Home
  Assistant backups. *Log out and delete tokens* removes them from the app; to revoke
  them at Garmin, change your Garmin password.
* **The app cannot change Home Assistant:** no access to the Home Assistant API. Its only
  access is the configuration folder, and its AppArmor profile allows only the helper
  integration's own folder there. The MCP
  server – the only part reachable from the internet – runs as an unprivileged user (and,
  where the kernel offers Linux Landlock, locks itself into its own folders).

Details: *Security* in [DOCS.md](DOCS.md). Found a vulnerability? Please report it
privately – see [SECURITY.md](../SECURITY.md).

### Why does the app install an integration?

AI assistants call MCP servers **from the internet**. From outside, usually only
Home Assistant itself is reachable (via Nabu Casa, Cloudflare Tunnel or a
reverse proxy) – not the apps, which run in their own containers. And only
code running *inside* Home Assistant can add an address there.

So on first start the app copies a tiny helper integration into Home Assistant
(`custom_components/garmin_mcp_webhook`) and announces its settings through Home
Assistant's official app discovery – Home Assistant then sets the integration up by
itself. The integration registers a **webhook** with a long random id
(`/api/webhook/garmin_mcp_…`) and passes each request on, unchanged, to the app inside
your network. Once a minute it tells the app your external address and language (for
the app page) and asks for the Garmin login state (for the repair notice). It stores
nothing and logs nothing but errors.

* Benefit: no extra hostname, tunnel or port forwarding.
* Cost: one Home Assistant restart after installing (shown only on the app page) and
  after updates of the helper (shown as a repair notice).
* Clean uninstall: uninstall the app and Home Assistant removes the integration's entry
  by itself; the helper then deletes its files – no restart needed. If Home Assistant
  was off during the uninstall, this happens within 10–20 minutes after the next start.

### Remote access: webhook or direct

| | `webhook` (default) | `direct` |
|---|---|---|
| Reached via | your existing Home Assistant address | your own hostname, e.g. `garmin.example.com` |
| Helper integration in Home Assistant | yes | no |
| Home Assistant restart | once after installing (and after helper updates) | never |
| You set up | nothing | a hostname in your tunnel / reverse proxy |

Use `direct` only if you don't want an extra integration in Home Assistant,
don't want restarts after updates, your reverse proxy blocks `/api/webhook/`,
or you want to secure Garmin access separately from Home Assistant.

**Setting up `direct`** – best before the first start:

1. Install the app, but don't start it yet.
2. *Configuration* tab: **Remote access** = `direct`, **Public address** =
   your hostname (e.g. `https://garmin.example.com`). Save.
3. Start the app. It installs nothing in Home Assistant.
4. The app page shows a *target for your tunnel / reverse proxy*
   (e.g. `http://abcd1234-garmin-mcp:8100`). Route your hostname there
   (Cloudflared app: `additional_hosts`).
5. Use the connector URL shown on the app page.

**Switching later** is fine too:

* `webhook` → `direct`: on the next start the app removes its helper
  integration from Home Assistant by itself (no restart needed). Then continue
  with steps 4–5.
* `direct` → `webhook`: on the next start the app installs the helper again
  and asks for one Home Assistant restart.

The connector URL changes when you switch – update it in your AI app.

### Requirements

* Home Assistant OS or Supervised, version 2026.2 or newer, on `amd64` or `aarch64`
  (e.g. Raspberry Pi 4/5)
* A Garmin Connect account
* Home Assistant reachable over HTTPS from the internet (Nabu Casa, Cloudflare
  Tunnel, reverse proxy, …)
* An AI app that supports remote MCP servers (Streamable HTTP), e.g. Claude, Mistral Vibe or ChatGPT (Plus)

### Updates and uninstalling

* **Updates** appear in Home Assistant like for any other app. What changed is in the
  [changelog](CHANGELOG.md). If an update brings a new version of the helper
  integration, a repair notice asks for one Home Assistant restart.
* **Uninstalling:** just uninstall the app – the helper integration removes itself (see
  above). Garmin tokens are deleted together with the app.

### Help and feedback

Problems or ideas: [open an issue](https://github.com/mw-hbg/ha-garmin-mcp/issues). Please add
the result of **Test connection** and the app log (*Log* tab) – but remove the connector
URL from it first. Troubleshooting tips: [DOCS.md](DOCS.md).

### Development

* **Local testing:** copy the `garmin_mcp` folder into the local apps folder of your
  Home Assistant host (Samba or SSH), remove the `image:` line from `config.yaml` and install it
  from *Local apps* – Home Assistant then builds the image itself.
* **Tests:** `bash garmin_mcp/tests/setup.sh` once, then `pytest garmin_mcp/tests` from
  the repository root (unit tests for the app and the helper integration); every push
  also builds both images and runs a smoke test of the container
  (`garmin_mcp/tests/smoke_test.sh`).
* **Changes:** add an entry under `## Unreleased` in `CHANGELOG.md` – English first,
  then the same in German below a `---` line. Never change `version` in `config.yaml`
  by hand.
* **Translations:** see [TRANSLATING.md](TRANSLATING.md).
* **Releases:** *Actions → Release → Run workflow* and enter the new version. Needs the
  repository secret `RELEASE_TOKEN` (fine-grained token of the owner, only this repository,
  *Contents: read and write*), so that release commit, tag and release appear under the
  owner's name. The workflow builds and pushes the images first, then sets the version,
  finishes the changelog, tags (`v1.2.3`) and publishes the release – so
  Home Assistant only offers an update once its images exist.
* **Garmin server updates:** a weekly check (configured in `upstream.yaml`) opens an
  issue when [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) has new
  commits. Update `UPSTREAM_REF` in the `Dockerfile` deliberately and let the tests run.
* **Shared workflows:** tests, release, translation and upstream checks come from
  [mw-hbg/workflows](https://github.com/mw-hbg/workflows); this repository only calls them.

### Credits and license

* MCP server: [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT)
* Garmin client: [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT)

This app is released under the [MIT License](../LICENSE). It is provided free of
charge and without warranty. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
for the licenses of bundled software.

## Deutsch

Lass KI-Assistenten wie **Claude** oder **ChatGPT** deine Trainings- und
Gesundheitsdaten aus Garmin Connect lesen – Läufe, Splits, Schlaf, HRV, Body
Battery, Trainingsbelastung – und strukturierte Workouts anlegen, die auf deine
Uhr synchronisiert werden.

Die App betreibt einen [MCP](https://modelcontextprotocol.io)-Server direkt
in deinem Home Assistant. Deine Daten gehen also ohne zusätzlichen Dienst dazwischen
von Garmin zu deinem KI-Assistenten.

> **Inoffiziell.** Nicht mit Garmin verbunden oder von Garmin unterstützt. Die
> App nutzt dieselben internen Schnittstellen wie die Garmin-Connect-Website,
> die Garmin jederzeit ändern oder sperren kann. Nutzung auf eigenes Risiko.

> **Experimentell** bis Version 1.0 – sie funktioniert, Details können sich aber noch ändern.

### Funktionen

* **Rund 157 Tools** aus [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp):
  Aktivitäten, Gesundheit, Trainingswerte, Workouts, Strecken, Ausrüstung, Ernährung …
* **Anmeldung direkt in Home Assistant**, auch mit Zwei-Faktor-Code.
  Dein Passwort wird nie gespeichert.
* **Du entscheidest, was die KI darf:** nur lesen, anlegen ohne je zu löschen
  oder voller Zugriff – plus Freigabe- und Sperrlisten für einzelne Tools.
* **Kein zusätzlicher Fernzugriff nötig:** erreichbar über die Adresse, mit der du
  Home Assistant ohnehin von außen nutzt – per Webhook.
* **Mehrere Garmin-Konten** (bis zu 10, z. B. der ganze Haushalt) – jedes mit eigener
  Anmeldung, Connector-URL, eigenen Rechten und eigenem Schalter.
* **Ein/Aus-Schalter in Home Assistant** pro Konto – eine normale Schalter-Entität, auch
  für Automationen: aus heißt, keine KI-App erreicht diese Daten; Anmeldung und
  Connector-URL bleiben.
* **Verbindungstest** per Klick – Server, Garmin-Anmeldung und Connector-URL
  aus dem Internet.
* **Kein Zugriff auf die Home-Assistant-API**, ein AppArmor-Profil für die ganze App
  (Sicherheitsbewertung 8/8) und der MCP-Server als eingeschränkter Benutzer
  (plus Linux-Landlock, wo der Kernel es anbietet) – über diese App lässt sich von außen nichts
  in Home Assistant ändern.
* **Reparatur-Hinweise**, wenn die Garmin-Anmeldung abgelaufen ist oder ein Update der
  Hilfs-Integration einen Neustart braucht (den allerersten Neustart nach der
  Installation zeigt nur die App-Seite an).
* **Geschützter Endpunkt:** nur über eine lange, zufällige geheime URL
  erreichbar, die du per Klick neu erzeugen kannst.
* **Deutsch und Englisch** – App-Seite, Konfiguration, Reparatur-Hinweise und Anleitung;
  weitere Sprachen lassen sich ohne Code ergänzen ([TRANSLATING.md](TRANSLATING.md)).
* Funktioniert mit jeder KI-App, die Remote-MCP-Server (Streamable HTTP) unterstützt –
  getestet mit Claude und Mistral Vibe, beide auch kostenlos nutzbar.
* Fertige Images für `amd64` und `aarch64` (Raspberry Pi 4/5).

### Installation

[![Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmw-hbg%2Fha-garmin-mcp)

1. *Einstellungen → Apps → App installieren → ⋮ → Repositories*, dort
   `https://github.com/mw-hbg/ha-garmin-mcp` eintragen.
2. **Garmin Connect MCP** installieren und starten.
3. **Home Assistant einmal neu starten** (*Einstellungen → System → Neu starten*). Für
   diesen ersten Neustart kommt **keine Benachrichtigung** – nur die App-Seite weist
   darauf hin. Die App hat keinen Zugriff auf die Home-Assistant-API, und ihre
   Hilfs-Integration läuft erst nach diesem Neustart. Spätere Updates der
   Hilfs-Integration melden sich als Reparatur-Hinweis.
4. In der Seitenleiste **Garmin MCP** öffnen und bei Garmin Connect anmelden. Etwa eine
   Minute nach dem Neustart sollte bei *Fernzugriff* **Aktiv** stehen.
5. **Verbindung testen** drücken, dann die auf der App-Seite angezeigte Connector-URL in
   deinem KI-Assistenten eintragen.

> **Umgezogen:** Dieses Repository hieß früher `mw-hbg/ha-apps` (davor
> `mw-hbg/ha-addons`). Wer eine der alten Adressen eingetragen hat, **lässt sie stehen** –
> GitHub leitet weiter, und Updates kommen weiter an. Die neue Adresse bitte nicht
> zusätzlich eintragen: Home Assistant hielte sie für eine andere App, und du müsstest
> dich neu bei Garmin anmelden und die Connector-URL ersetzen.

Voraussetzung: Home Assistant ist bereits von außen per HTTPS erreichbar
(Nabu Casa, Cloudflare-Tunnel, Reverse Proxy …). Einen zusätzlichen Hostnamen
oder Tunnel braucht es nicht.

Gut zu wissen:

* **Zwei-Faktor-Anmeldung** bei Garmin wird unterstützt – die App fragt beim
  Anmelden nach dem Code.
* **Workouts auf die Uhr (EU-Konten):** Garmin braucht deine Zustimmung zum
  Hochladen: Garmin Connect → *Einstellungen → Datenschutzeinstellungen → Daten →
  Gerätedaten hochladen* muss aktiv sein.
* **Nutzt du auch ha-mcp?** Dann fragt deine KI-App beim Hinzufügen des
  Connectors eventuell nach einer Anmeldung bei Home Assistant. Das kommt von
  ha-mcp und ist unbedenklich.

Ausführliche Anleitung: [DOCS.md](DOCS.md#deutsch) – auch im Reiter *Dokumentation* der
App; der deutsche Teil steht dort nach dem englischen (ganz oben auf „Deutsch“ klicken).

### Deine Daten und Sicherheit

* **Was die KI liest, geht an deinen KI-Anbieter.** Nutzt dein KI-Assistent ein Tool,
  wird das Ergebnis (z. B. Schlaf- oder Herzfrequenzdaten) an diesen Anbieter (Anthropic,
  OpenAI …) geschickt und nach dessen Datenschutzbedingungen verarbeitet. Gib nur frei,
  was du teilen willst: *Tools auswählen* auf der App-Seite oder Reiter *Konfiguration*.
* **Schreibrechte sind standardmäßig begrenzt** (`create_only`): Die KI darf Workouts
  anlegen und einplanen und Einträge hinzufügen, aber nie etwas löschen oder
  überschreiben. `read_only` und `full` sind wählbar.
* **Behandle die Connector-URL wie ein Passwort.** Wer sie kennt, kann die freigegebenen
  Tools nutzen. Keine Screenshots oder Protokolle teilen, in denen sie steht; ist sie
  bekannt geworden: **Neue geheime URL erzeugen** auf der App-Seite.
* **Dein Garmin-Passwort wird nie gespeichert** – nur die Tokens, die Garmin nach der
  Anmeldung ausstellt (etwa sechs Monate gültig), im privaten Speicher der App und in
  deinen Home-Assistant-Backups. *Abmelden und Tokens löschen* entfernt sie aus der App;
  um sie bei Garmin ungültig zu machen, änderst du dein Garmin-Passwort.
* **Die App kann Home Assistant nicht verändern:** kein Zugriff auf die
  Home-Assistant-API. Ihr einziger Zugriff ist der Konfigurationsordner, und ihr
  AppArmor-Profil erlaubt dort nur den Ordner der Hilfs-Integration. Der MCP-Server – der einzige von außen
  erreichbare Teil – läuft als eingeschränkter Benutzer (und sperrt sich, wo der Kernel
  Linux-Landlock anbietet, zusätzlich in seine eigenen Ordner ein).

Details: *Sicherheit* in [DOCS.md](DOCS.md#deutsch). Eine Sicherheitslücke gefunden? Bitte
vertraulich melden – siehe [SECURITY.md](../SECURITY.md).

### Warum installiert die App eine Integration?

KI-Assistenten rufen MCP-Server **aus dem Internet** auf. Von außen ist meist
nur Home Assistant selbst erreichbar (über Nabu Casa, Cloudflare-Tunnel oder
Reverse Proxy), nicht aber die Apps, die in eigenen Containern laufen. Und
nur Code, der *in* Home Assistant läuft, kann dort eine Adresse anlegen.

Deshalb kopiert die App beim ersten Start eine winzige Hilfs-Integration in Home
Assistant (`custom_components/garmin_mcp_webhook`) und meldet ihre Einstellungen über die
offizielle App-Erkennung von Home Assistant – Home Assistant richtet die Integration
damit selbst ein. Die Integration legt einen **Webhook** mit einer langen Zufalls-ID an
(`/api/webhook/garmin_mcp_…`) und reicht jede Anfrage unverändert an die App in deinem
Netz weiter. Einmal pro Minute teilt sie der App deine externe Adresse und Sprache mit
(für die App-Seite) und fragt den Garmin-Anmeldestatus ab (für den Reparatur-Hinweis).
Sie speichert nichts und protokolliert nur Fehler.

* Vorteil: kein zusätzlicher Hostname, Tunnel oder Portfreigabe.
* Preis: ein Neustart von Home Assistant nach der Installation (nur auf der App-Seite
  angezeigt) und nach Updates der Hilfs-Integration (als Reparatur-Hinweis).
* Sauber deinstallieren: App deinstallieren, und Home Assistant entfernt den Eintrag der
  Integration selbst; danach löscht sie ihre Dateien – ohne Neustart. War Home Assistant
  dabei aus, passiert das innerhalb von 10–20 Minuten nach dem nächsten Start.

### Fernzugriff: webhook oder direct

| | `webhook` (Standard) | `direct` |
|---|---|---|
| Erreichbar über | deine bestehende Home-Assistant-Adresse | einen eigenen Hostnamen, z. B. `garmin.example.com` |
| Hilfs-Integration in Home Assistant | ja | nein |
| Neustart von Home Assistant | einmal nach der Installation (und nach Updates der Hilfs-Integration) | nie |
| Du richtest ein | nichts | einen Hostnamen in Tunnel / Reverse Proxy |

`direct` brauchst du nur, wenn du keine zusätzliche Integration in Home
Assistant willst, keine Neustarts nach Updates, dein Reverse Proxy
`/api/webhook/` sperrt oder du den Garmin-Zugang getrennt von Home Assistant
absichern willst.

**`direct` einrichten** – am besten vor dem ersten Start:

1. App installieren, aber noch nicht starten.
2. Reiter *Konfiguration*: **Fernzugriff** = `direct`, **Öffentliche Adresse** =
   dein Hostname (z. B. `https://garmin.example.com`). Speichern.
3. App starten. Sie installiert nichts in Home Assistant.
4. Die App-Seite zeigt ein *Ziel für deinen Tunnel / Reverse Proxy*
   (z. B. `http://abcd1234-garmin-mcp:8100`). Leite deinen Hostnamen dorthin
   (Cloudflared-App: `additional_hosts`).
5. Die auf der App-Seite angezeigte Connector-URL verwenden.

**Später umstellen** geht auch:

* `webhook` → `direct`: Beim nächsten Start entfernt die App ihre
  Hilfs-Integration selbst aus Home Assistant (kein Neustart nötig). Danach
  weiter mit Schritt 4–5.
* `direct` → `webhook`: Beim nächsten Start installiert die App die
  Hilfs-Integration wieder und bittet um einen Neustart von Home Assistant.

Beim Umstellen ändert sich die Connector-URL – trag die neue in deiner KI-App ein.

### Voraussetzungen

* Home Assistant OS oder Supervised, Version 2026.2 oder neuer, auf `amd64` oder
  `aarch64` (z. B. Raspberry Pi 4/5)
* Ein Garmin-Connect-Konto
* Home Assistant per HTTPS aus dem Internet erreichbar (Nabu Casa, Cloudflare-Tunnel,
  Reverse Proxy …)
* Eine KI-App, die Remote-MCP-Server (Streamable HTTP) unterstützt, z. B. Claude, Mistral Vibe
  oder ChatGPT (ab Plus)

### Updates und Deinstallieren

* **Updates** erscheinen in Home Assistant wie bei jeder anderen App. Was sich geändert
  hat, steht im [Changelog](CHANGELOG.md) (auf Englisch und Deutsch). Bringt ein Update
  eine neue Version der Hilfs-Integration mit, bittet ein Reparatur-Hinweis um einen
  Neustart von Home Assistant.
* **Deinstallieren:** einfach die App deinstallieren – die Hilfs-Integration entfernt
  sich selbst (siehe oben). Die Garmin-Tokens werden mit der App gelöscht.

### Hilfe und Rückmeldungen

Probleme oder Ideen: [Issue anlegen](https://github.com/mw-hbg/ha-garmin-mcp/issues). Bitte das
Ergebnis von **Verbindung testen** und das App-Protokoll (Reiter *Protokoll*) mitschicken
– vorher die Connector-URL daraus entfernen. Tipps zur Fehlersuche:
[DOCS.md](DOCS.md#deutsch).

### Entwicklung

* **Lokal testen:** den Ordner `garmin_mcp` in den lokalen App-Ordner deines
  Home-Assistant-Hosts kopieren (Samba oder SSH), in `config.yaml` die Zeile `image:`
  entfernen und unter *Lokale Apps* installieren – Home Assistant baut das Image dann
  selbst.
* **Tests:** einmal `bash garmin_mcp/tests/setup.sh`, dann `pytest garmin_mcp/tests` im
  Repository-Ordner (Unit-Tests für die App und die Hilfs-Integration); jeder Push baut
  außerdem beide Images und testet den fertigen Container
  (`garmin_mcp/tests/smoke_test.sh`).
* **Änderungen:** Eintrag unter `## Unreleased` in `CHANGELOG.md` – erst Englisch, dann
  dasselbe auf Deutsch unter einer `---`-Linie. `version` in `config.yaml` nie von Hand
  ändern.
* **Übersetzungen:** siehe [TRANSLATING.md](TRANSLATING.md).
* **Releases:** *Actions → Release → Run workflow* und die neue Version eintragen. Braucht
  das Repository-Secret `RELEASE_TOKEN` (feingranularer Token des Besitzers, nur dieses
  Repository, *Contents: read and write*), damit Release-Commit, Tag und Release unter dem
  Namen des Besitzers erscheinen. Der
  Ablauf baut und veröffentlicht zuerst die Images, setzt dann die Version, schließt den
  Changelog ab, setzt den Tag (`v1.2.3`) und veröffentlicht das Release – Home Assistant
  bietet ein Update also erst an, wenn die Images existieren.
* **Updates des Garmin-Servers:** Eine wöchentliche Prüfung (eingestellt in
  `upstream.yaml`) legt ein Issue an, wenn
  [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) neue Commits hat.
  `UPSTREAM_REF` im `Dockerfile` bewusst anheben und die Tests laufen lassen.
* **Gemeinsame Workflows:** Tests, Release, Übersetzungs- und Upstream-Prüfung kommen aus
  [mw-hbg/workflows](https://github.com/mw-hbg/workflows); dieses Repository ruft sie nur auf.

### Dank und Lizenz

* MCP-Server: [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT)
* Garmin-Client: [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT)

Diese App steht unter der [MIT-Lizenz](../LICENSE). Sie wird kostenlos und ohne Gewähr
bereitgestellt. Lizenzen der enthaltenen Software:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
