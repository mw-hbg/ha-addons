# Garmin Connect MCP – Home-Assistant-App

[🇬🇧 English version](README.md)

Lass KI-Assistenten wie **Claude** oder **ChatGPT** deine Trainings- und
Gesundheitsdaten aus Garmin Connect lesen – Läufe, Splits, Schlaf, HRV, Body
Battery, Trainingsbelastung – und strukturierte Workouts anlegen, die auf deine
Uhr synchronisiert werden.

Die App betreibt einen [MCP](https://modelcontextprotocol.io)-Server direkt
in deinem Home Assistant. Deine Daten gehen also ohne Drittanbieter dazwischen
von Garmin zu deinem KI-Assistenten.

> **Inoffiziell.** Nicht mit Garmin verbunden oder von Garmin unterstützt. Das
> App nutzt dieselben internen Schnittstellen wie die Garmin-Connect-Website,
> die Garmin jederzeit ändern oder sperren kann. Nutzung auf eigenes Risiko.

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
* **Benachrichtigungen**, wenn ein Neustart nötig ist oder die Garmin-Anmeldung
  abgelaufen ist.
* **Geschützter Endpunkt:** nur über eine lange, zufällige geheime URL
  erreichbar, die du per Klick neu erzeugen kannst.
* **Deutsch und Englisch** – App-Seite, Konfiguration, Benachrichtigungen und Anleitung;
  weitere Sprachen lassen sich ohne Code ergänzen ([TRANSLATING.md](TRANSLATING.md)).
* Funktioniert mit jeder KI-App, die Remote-MCP-Server (Streamable HTTP) unterstützt.
* Fertige Images für `amd64` und `aarch64` (Raspberry Pi 4/5).

## Installation

1. *Einstellungen → Apps → App installieren → ⋮ → Repositories*, dort
   `https://github.com/mw-hbg/ha-apps` eintragen.
2. **Garmin Connect MCP** installieren und starten.
3. In der Seitenleiste **Garmin MCP** öffnen und bei Garmin Connect anmelden.
4. Home Assistant einmal neu starten, wenn die App-Seite darum bittet.
5. Die auf der App-Seite angezeigte Connector-URL in deinem KI-Assistenten eintragen.

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

## Warum installiert die App eine Integration?

KI-Assistenten rufen MCP-Server **aus dem Internet** auf. Von außen ist meist
nur Home Assistant selbst erreichbar (über Nabu Casa, Cloudflare-Tunnel oder
Reverse Proxy), nicht aber die Apps, die in eigenen Containern laufen. Und
nur Code, der *in* Home Assistant läuft, kann dort eine Adresse anlegen.

Deshalb legt die App beim ersten Start eine winzige Hilfs-Integration an
(`custom_components/garmin_mcp_webhook`). Sie richtet einen Home-Assistant-
**Webhook** mit einer langen Zufalls-ID ein (`/api/webhook/garmin_mcp_…`) und
reicht jede Anfrage unverändert an die App in deinem Netz weiter. Sie
speichert nichts, liest sonst nichts und protokolliert nur Fehler.

* Vorteil: kein zusätzlicher Hostname, Tunnel oder Portfreigabe.
* Preis: ein Neustart von Home Assistant nach der Installation (und nach
  Updates der Hilfs-Integration). App-Seite und Reparatur-Hinweis sagen dir,
  wann.
* Sauber deinstallieren: Deinstallierst du die App, merkt die Hilfs-Integration das
  innerhalb von 10–20 Minuten und entfernt sich samt Dateien selbst – ohne Neustart.

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

## Lizenz

MIT-Lizenz, siehe [LICENSE](../LICENSE). Die App wird kostenlos und ohne
Gewähr bereitgestellt. Lizenzen der enthaltenen Software:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
