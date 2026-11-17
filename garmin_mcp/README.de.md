# Garmin Connect MCP – Home-Assistant-App

[🇬🇧 English version](README.md)

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

## Funktionen

* **Rund 157 Tools** aus [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp):
  Aktivitäten, Gesundheit, Trainingswerte, Workouts, Strecken, Ausrüstung, Ernährung …
* **Anmeldung direkt in Home Assistant**, auch mit Zwei-Faktor-Code.
  Dein Passwort wird nie gespeichert.
* **Du entscheidest, was die KI darf:** nur lesen, anlegen ohne je zu löschen
  oder voller Zugriff – plus Freigabe- und Sperrlisten für einzelne Tools.
* **Kein zusätzlicher Fernzugriff nötig:** erreichbar über die Adresse, mit der du
  Home Assistant ohnehin von außen nutzt – per Webhook.
* **Verbindungstest** per Klick – Server, Garmin-Anmeldung und Connector-URL
  aus dem Internet.
* **Kein Zugriff auf die Home-Assistant-API**, ein AppArmor-Profil für die ganze App
  (Sicherheitsbewertung 8/8) und der MCP-Server in seine eigenen Ordner eingesperrt
  (eingeschränkter Benutzer + Linux-Landlock) – über diese App lässt sich von außen nichts
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

## Installation

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

Ausführliche Anleitung: [DOCS.de.md](DOCS.de.md). Der Tab *Dokumentation* der App zeigt
sie auf Englisch (Home Assistant kann dort nur eine Sprache anzeigen); ganz oben steht
der Link zur deutschen Fassung.

## Deine Daten und Sicherheit

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
  erreichbare Teil – läuft als eingeschränkter Benutzer und ist mit Linux-Landlock in
  seine eigenen Ordner eingesperrt.

Details: *Sicherheit* in [DOCS.de.md](DOCS.de.md). Eine Sicherheitslücke gefunden? Bitte
vertraulich melden – siehe [SECURITY.md](../SECURITY.md).

## Warum installiert die App eine Integration?

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

## Fernzugriff: webhook oder direct

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

## Voraussetzungen

* Home Assistant OS oder Supervised, Version 2026.2 oder neuer, auf `amd64` oder
  `aarch64` (z. B. Raspberry Pi 4/5)
* Ein Garmin-Connect-Konto
* Home Assistant per HTTPS aus dem Internet erreichbar (Nabu Casa, Cloudflare-Tunnel,
  Reverse Proxy …)
* Eine KI-App, die Remote-MCP-Server (Streamable HTTP) unterstützt, z. B. Claude, Mistral Vibe
  oder ChatGPT (ab Plus)

## Updates und Deinstallieren

* **Updates** erscheinen in Home Assistant wie bei jeder anderen App. Was sich geändert
  hat, steht im [Changelog](CHANGELOG.md) (auf Englisch und Deutsch). Bringt ein Update
  eine neue Version der Hilfs-Integration mit, bittet ein Reparatur-Hinweis um einen
  Neustart von Home Assistant.
* **Deinstallieren:** einfach die App deinstallieren – die Hilfs-Integration entfernt
  sich selbst (siehe oben). Die Garmin-Tokens werden mit der App gelöscht.

## Hilfe und Rückmeldungen

Probleme oder Ideen: [Issue anlegen](https://github.com/mw-hbg/ha-garmin-mcp/issues). Bitte das
Ergebnis von **Verbindung testen** und das App-Protokoll (Reiter *Protokoll*) mitschicken
– vorher die Connector-URL daraus entfernen. Tipps zur Fehlersuche:
[DOCS.de.md](DOCS.de.md).

## Entwicklung

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
* **Releases:** *Actions → Release → Run workflow* und die neue Version eintragen. Der
  Ablauf baut und veröffentlicht zuerst die Images, setzt dann die Version, schließt den
  Changelog ab, setzt den Tag (`v1.2.3`) und veröffentlicht das Release – Home Assistant
  bietet ein Update also erst an, wenn die Images existieren.
* **Updates des Garmin-Servers:** Eine wöchentliche Prüfung (eingestellt in
  `upstream.yaml`) legt ein Issue an, wenn
  [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) neue Commits hat.
  `UPSTREAM_REF` im `Dockerfile` bewusst anheben und die Tests laufen lassen.
* **Gemeinsame Workflows:** Tests, Release, Übersetzungs- und Upstream-Prüfung kommen aus
  [mw-hbg/.github](https://github.com/mw-hbg/.github); dieses Repository ruft sie nur auf.

## Dank und Lizenz

* MCP-Server: [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT)
* Garmin-Client: [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT)

Diese App steht unter der [MIT-Lizenz](../LICENSE). Sie wird kostenlos und ohne Gewähr
bereitgestellt. Lizenzen der enthaltenen Software:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
