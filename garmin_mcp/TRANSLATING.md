# Adding a language

The app is fully available in English and German. Another language only needs a few
files – no code changes. English is the reference: whatever a language does not
translate (yet) is shown in English.

Use the two-letter language code (`fr`, `nl`, `es`, …) in every file name. Replace `xx`
below with it.

| # | File | Shown in | How |
|---|---|---|---|
| 1 | `rootfs/app/i18n/xx.json` | App page, notifications, tool categories and tool descriptions | Copy `en.json`, translate the values, keep the keys and placeholders like `{n}` unchanged. Set `"language"` to the name of the language in that language (e.g. `"Français"`). |
| 2 | `translations/xx.yaml` | *Configuration* and *Network* sections of the app in Home Assistant | Copy `translations/en.yaml`, translate `name` and `description`. |
| 3 | `rootfs/app/integration/garmin_mcp_webhook/translations/xx.json` | Repair notice “restart required” and the notification after uninstalling (helper integration) | Copy `en.json` next to it and translate it. Also raise `version` in `manifest.json` of the integration, so the app installs the new texts (Home Assistant then asks for one restart). |
| 4 | `DOCS.md` *(optional)* | *Documentation* tab of the app and the link on the app page | Home Assistant shows only `DOCS.md`, so all languages are in that one file. Copy the section `## English` to the end, rename the heading (e.g. `## Français`), translate it and rename its table markers to `<!-- tools:xx:start -->` / `<!-- tools:xx:end -->`. Add the language to the links at the top and set `"docs_section"` in `i18n/xx.json` to the heading's anchor (lower case, e.g. `"français"`). Without it the English section is linked. |
| 5 | `README.md` *(optional)* | App store in Home Assistant, GitHub | Same as `DOCS.md`: one more section `## <language>` at the end of the same file and a link at the top. |

Then, in the app folder (`garmin_mcp`):

```sh
python scripts/update_docs.py   # fills the tool table in the documentation
pytest tests                    # checks that every text exists and placeholders match
```

How the language is chosen on the app page: the choice in the footer of the page (kept
in a cookie), otherwise the browser language, otherwise the Home Assistant language,
otherwise English. Notifications always use the Home Assistant language.

Messages the app sends to the AI (e.g. “log in again”) stay in English on purpose – AI
assistants understand them and answer in the user's language anyway.

---

# Weitere Sprache hinzufügen

Die App ist vollständig auf Englisch und Deutsch verfügbar. Eine weitere Sprache braucht
nur ein paar Dateien, keinen Code. Englisch ist die Vorlage: Was (noch) nicht übersetzt
ist, erscheint auf Englisch. Die Schritte stehen in der Tabelle oben – `xx` durch den
zweibuchstabigen Sprachcode ersetzen, danach im App-Ordner (`garmin_mcp`)
`python scripts/update_docs.py` und `pytest tests` ausführen.
