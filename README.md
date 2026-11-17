# Garmin Connect MCP – Home Assistant app

[English](#english) · [Deutsch](#deutsch)

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmw-hbg%2Fha-garmin-mcp)
[![Test](https://github.com/mw-hbg/ha-garmin-mcp/actions/workflows/build.yaml/badge.svg)](https://github.com/mw-hbg/ha-garmin-mcp/actions/workflows/build.yaml)
[![Release](https://img.shields.io/github/v/release/mw-hbg/ha-garmin-mcp?label=release)](https://github.com/mw-hbg/ha-garmin-mcp/releases)
![Stage: experimental](https://img.shields.io/badge/stage-experimental-orange)

## English

Let AI assistants such as **Claude** or **ChatGPT** read your Garmin Connect
training and health data and create workouts that sync to your watch. The app
runs an [MCP](https://modelcontextprotocol.io) server inside your Home
Assistant – no additional service in between, reachable through the address you
already use for Home Assistant.

* Login with two-factor authentication in the Home Assistant UI; your password is never stored.
* You decide what the AI may do: read only, create without deleting, or full access.
* Security first: no access to the Home Assistant API, AppArmor profile, the
  internet-facing server runs unprivileged and sandboxed.
* English and German; more languages can be added without code.

> **Unofficial** – not affiliated with Garmin. **Experimental** until version 1.0.

**Installation:** click the button above or add
`https://github.com/mw-hbg/ha-garmin-mcp` under *Settings → Apps → Install app →
⋮ → Repositories*, then install **Garmin Connect MCP**. Step by step:
[app README](garmin_mcp/README.md) · full documentation: [DOCS.md](garmin_mcp/DOCS.md)
(also in the app's *Documentation* tab).

> **Moved:** this repository used to be `mw-hbg/ha-apps` (before that
> `mw-hbg/ha-addons`). If you added an old address, **keep it** – it forwards and
> updates keep arriving. Adding the new address in addition would make Home Assistant
> treat it as a different app (new Garmin login and connector URL).

**Help:** [issues](https://github.com/mw-hbg/ha-garmin-mcp/issues) · security
problems please privately, see [SECURITY.md](SECURITY.md) ·
[changelog](garmin_mcp/CHANGELOG.md) · more projects:
[github.com/mw-hbg](https://github.com/mw-hbg)

## Deutsch

KI-Assistenten wie **Claude** oder **ChatGPT** lesen deine Trainings- und
Gesundheitsdaten aus Garmin Connect und legen Workouts an, die auf deine Uhr
synchronisiert werden. Die App betreibt einen
[MCP](https://modelcontextprotocol.io)-Server in deinem Home Assistant – ohne
Dienst dazwischen, erreichbar über die Adresse, die du für Home Assistant schon
nutzt.

* Anmeldung inkl. Zwei-Faktor-Authentifizierung in Home Assistant; dein Passwort wird nie gespeichert.
* Du bestimmst, was die KI darf: nur lesen, anlegen ohne löschen oder alles.
* Sicherheit zuerst: kein Zugriff auf die Home-Assistant-API, AppArmor-Profil, der
  aus dem Internet erreichbare Server läuft eingeschränkt und abgeschottet.
* Deutsch und Englisch; weitere Sprachen ohne Code ergänzbar.

> **Inoffiziell** – keine Verbindung zu Garmin. **Experimentell** bis Version 1.0.

**Installation:** Knopf oben anklicken oder unter *Einstellungen → Apps → App
installieren → ⋮ → Repositories* `https://github.com/mw-hbg/ha-garmin-mcp`
eintragen, dann **Garmin Connect MCP** installieren. Schritt für Schritt:
[App-README](garmin_mcp/README.md#deutsch) · ausführliche Anleitung:
[DOCS.md](garmin_mcp/DOCS.md#deutsch) (auch im Reiter *Dokumentation* der App).

> **Umgezogen:** Dieses Repository hieß früher `mw-hbg/ha-apps` (davor
> `mw-hbg/ha-addons`). Eine alte Adresse **einfach stehen lassen** – sie wird
> weitergeleitet, Updates kommen weiter an. Die neue Adresse zusätzlich einzutragen,
> würde Home Assistant als andere App sehen (neue Garmin-Anmeldung und Connector-URL).

**Hilfe:** [Issues](https://github.com/mw-hbg/ha-garmin-mcp/issues) ·
Sicherheitsprobleme bitte vertraulich, siehe [SECURITY.md](SECURITY.md) ·
[Changelog](garmin_mcp/CHANGELOG.md) · weitere Projekte:
[github.com/mw-hbg](https://github.com/mw-hbg)

## License / Lizenz

[MIT](LICENSE). Free of charge and without warranty / kostenlos und ohne Gewähr.
Bundled software / enthaltene Software: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
