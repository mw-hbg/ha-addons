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
| 3 | `rootfs/app/integration/garmin_mcp_webhook/translations/xx.json` | Repair notice “restart required” of the helper integration | Copy `en.json` next to it and translate it. Also raise `version` in `manifest.json` of the integration, so the app installs the new texts (Home Assistant then asks for one restart). |
| 4 | `DOCS.xx.md` *(optional)* | Documentation linked from the app page | Copy `DOCS.md`, translate it and keep the lines `<!-- tools:start -->` / `<!-- tools:end -->`. Set `"docs_file": "DOCS.xx.md"` in `i18n/xx.json`. Without it the English documentation is linked. |
| 5 | `README.xx.md` *(optional)* | GitHub | Copy `README.md` and add a link to it at the top of the other READMEs. |

Then, from the repository folder:

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
zweibuchstabigen Sprachcode ersetzen, danach `python scripts/update_docs.py` und
`pytest tests` ausführen.
