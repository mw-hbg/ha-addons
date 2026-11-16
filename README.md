# Home Assistant apps by mw-hbg

[🇩🇪 Deutsch](#deutsch)

## Apps

| App | Description |
|---|---|
| [Garmin Connect MCP](garmin_mcp/README.md) | Let AI assistants (Claude, ChatGPT, …) read your Garmin Connect training and health data and plan workouts on your watch. |

## Installation

1. *Settings → Apps → Install app → ⋮ → Repositories*, add
   `https://github.com/mw-hbg/ha-apps`
2. The apps appear under *Install app*. New apps in this repository show up
   automatically.

Requires Home Assistant OS or Supervised. Each app has its own
documentation (also shown in the app's *Documentation* tab).

## Adding an app

Every top-level folder with a `config.yaml` is an app. Tests, image builds and
releases pick it up automatically. Checklist for a new app `my_app`:

1. Folder `my_app/` with `config.yaml` (`slug: my_app`,
   `image: ghcr.io/mw-hbg/{arch}-app-my-app`, `version: "0.0.0"`), `Dockerfile`,
   `README.md`, `README.de.md`, `DOCS.md`, `CHANGELOG.md` (with a `## Unreleased`
   section, English then German), `icon.png`, `logo.png`, `translations/en.yaml` and
   `translations/de.yaml`.
2. Optional: `my_app/tests/` (unit tests), `my_app/tests/setup.sh` (installs what they
   need), `my_app/tests/smoke_test.sh` (gets the built image as argument),
   `my_app/upstream.yaml` (weekly check for upstream updates).
3. Add `my_app` to the `app` options in `.github/workflows/release.yaml`, add a bug
   report template `.github/ISSUE_TEMPLATE/my_app_bug.yml` and list the app in the
   table above (English and German).
4. Push – the *Test* workflow checks steps 1 and 3 and fails with a clear message if
   something is missing.
5. Release with *Actions → Release*: choose `my_app`, enter the version. After the
   first release, check once that the new packages are public (GitHub → *Packages*);
   if not: package → *Package settings* → *Change visibility*. Otherwise Home Assistant
   cannot download them.

## License

[MIT](LICENSE). Provided free of charge and without warranty.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled software.

---

## Deutsch

Sammlung von Home-Assistant-Apps.

**Installation:** *Einstellungen → Apps → App installieren → ⋮ → Repositories*,
dort `https://github.com/mw-hbg/ha-apps` eintragen. Neue Apps in diesem
Repository erscheinen danach automatisch unter *App installieren*.

| App | Beschreibung |
|---|---|
| [Garmin Connect MCP](garmin_mcp/README.de.md) | KI-Assistenten (Claude, ChatGPT, …) lesen deine Trainings- und Gesundheitsdaten aus Garmin Connect und planen Workouts auf deiner Uhr. |

Benötigt Home Assistant OS oder Supervised. Jede App hat ihre eigene Anleitung (auch im
Reiter *Dokumentation* der App).

**Neue App hinzufügen:** Jeder Ordner auf oberster Ebene mit einer `config.yaml` ist
eine App; Tests, Images und Releases erkennen ihn automatisch. Die Checkliste steht oben
unter *Adding an app*: Ordner mit den Pflichtdateien anlegen, die App im Release-Ablauf
(`.github/workflows/release.yaml`) und in der Tabelle eintragen, eine Vorlage für
Fehlerberichte anlegen und nach dem ersten Release prüfen, ob die neuen Pakete öffentlich
sind. Der Test-Ablauf meldet klar, wenn etwas fehlt.

**Lizenz:** [MIT](LICENSE). Kostenlos und ohne Gewähr. Enthaltene Software:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
