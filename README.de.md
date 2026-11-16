# Garmin Connect MCP – Home-Assistant-Add-on

[🇬🇧 English version](README.md)

Lass KI-Assistenten wie **Claude** oder **ChatGPT** deine Trainings- und
Gesundheitsdaten aus Garmin Connect lesen – Läufe, Splits, Schlaf, HRV, Body
Battery, Trainingsbelastung – und strukturierte Workouts anlegen, die auf deine
Uhr synchronisiert werden.

Das Add-on betreibt einen [MCP](https://modelcontextprotocol.io)-Server direkt
in deinem Home Assistant. Deine Daten gehen also ohne Drittanbieter dazwischen
von Garmin zu deinem KI-Assistenten.

> **Inoffiziell.** Nicht mit Garmin verbunden oder von Garmin unterstützt. Das
> Add-on nutzt dieselben internen Schnittstellen wie die Garmin-Connect-Website,
> die Garmin jederzeit ändern oder sperren kann. Nutzung auf eigenes Risiko.

## Funktionen

* **Rund 157 Tools** aus [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp):
  Aktivitäten, Gesundheit, Trainingswerte, Workouts, Strecken, Ausrüstung, Ernährung …
* **Anmeldung direkt in Home Assistant**, auch mit Zwei-Faktor-Code.
  Dein Passwort wird nie gespeichert.
* **Du entscheidest, was die KI darf:** nur lesen, anlegen ohne je zu löschen
  oder voller Zugriff – plus Freigabe- und Sperrlisten für einzelne Tools.
* **Geschützter Endpunkt:** nur über eine lange, zufällige geheime URL
  erreichbar, die du per Klick neu erzeugen kannst.
* Funktioniert mit jeder KI-App, die Remote-MCP-Server (Streamable HTTP) unterstützt.
* Fertige Images für `amd64` und `aarch64` (Raspberry Pi 4/5).

## Installation

1. *Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories*, dort
   `https://github.com/OWNER/ha-garmin-mcp` eintragen.
2. **Garmin Connect MCP** installieren und starten.
3. In der Seitenleiste **Garmin MCP** öffnen und bei Garmin Connect anmelden.
4. Das Add-on per HTTPS erreichbar machen (z. B. mit dem Cloudflared-Add-on).
5. Die auf der Add-on-Seite angezeigte Connector-URL in deinem KI-Assistenten eintragen.

Ausführliche Anleitung (Englisch): [garmin_mcp/DOCS.md](garmin_mcp/DOCS.md),
auch im Tab *Dokumentation* des Add-ons.

## Lizenz

MIT-Lizenz, siehe [LICENSE](LICENSE). Das Add-on wird kostenlos und ohne
Gewähr bereitgestellt. Lizenzen der enthaltenen Software:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
