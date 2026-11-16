# Garmin Connect MCP

[🇬🇧 English documentation](https://github.com/mw-hbg/ha-apps/blob/main/garmin_mcp/DOCS.md)

Diese App betreibt einen [MCP](https://modelcontextprotocol.io)-Server für dein
Garmin-Connect-Konto direkt in Home Assistant. KI-Assistenten, die Remote-MCP-Server
unterstützen – Claude, ChatGPT und viele andere –, können damit deine Trainings- und
Gesundheitsdaten lesen und, wenn du es erlaubst, Workouts anlegen und auf deiner Uhr
einplanen.

> **Inoffiziell.** Dieses Projekt ist nicht mit Garmin verbunden und wird nicht von
> Garmin unterstützt. Garmin bietet keine öffentliche Schnittstelle für Privatpersonen,
> deshalb nutzt die App dieselben internen Schnittstellen wie die Garmin-Connect-Webseite
> (über [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)).
> Garmin kann das jederzeit ändern oder sperren. Nutzung auf eigenes Risiko.

## So funktioniert es

```
KI-Assistent ──HTTPS──► deine Home-Assistant-Adresse ──► /api/webhook/<geheime ID> ──► App ──► Garmin Connect
                        (Nabu Casa, Cloudflare-Tunnel,    (Hilfs-Integration)
                         Reverse Proxy …)
```

* Standardmäßig ist die App über die Adresse erreichbar, mit der du Home Assistant
  ohnehin von unterwegs nutzt – **kein zusätzlicher Hostname, kein Tunnel, keine
  Portfreigabe**. Eine kleine Hilfs-Integration (`garmin_mcp_webhook`), die die App
  selbst installiert, stellt einen Home-Assistant-Webhook mit langer Zufalls-ID bereit
  und leitet die Anfragen an die App weiter.
* Alternativ (`remote_access: direct`) leitest du einen eigenen HTTPS-Hostnamen auf
  Port 8100 der App.
* Der MCP-Server selbst lauscht nur intern. Ein vorgeschaltetes nginx leitet nur
  Anfragen mit einem langen, zufälligen **geheimen Pfad** weiter; alles andere bekommt `404`.
* Die App-Seite (Seitenleiste → **Garmin MCP**) ist nur über Home Assistant und nur
  für Administratoren erreichbar.
* Dein Garmin-Passwort wird nie gespeichert. Nach der Anmeldung liegen nur die
  OAuth-Tokens, die Garmin ausstellt, im privaten Speicher der App (gültig etwa sechs Monate).
* **Abmelden und Tokens löschen** entfernt die Tokens aus der App. Garmin selbst
  erfährt davon nichts – irgendwo anders kopierte Tokens blieben bis zum Ablauf gültig.
  Um sie überall ungültig zu machen, änderst du dein Garmin-Passwort.

## Einrichtung

Benötigt Home Assistant **2026.2** oder neuer (OS oder Supervised). Bis Version 1.0 ist
die App als *experimentell* gekennzeichnet.

### 1. Installieren und starten

*Einstellungen → Apps → App installieren → ⋮ → Repositories*, dort
`https://github.com/mw-hbg/ha-apps` eintragen. Dann **Garmin Connect MCP** installieren,
starten und in der Seitenleiste **Garmin MCP** öffnen (oder **Weboberfläche öffnen**
auf der App-Seite).

### 2. Bei Garmin Connect anmelden

Garmin-E-Mail und Passwort eingeben.

**Zwei-Faktor-Anmeldung** wird unterstützt. Ist sie für dein Garmin-Konto aktiv, schickt
Garmin dir einen Code (App, E-Mail oder SMS) und die App fragt im nächsten Schritt danach.
Den Code brauchst du nur bei der Anmeldung, nicht bei jeder Anfrage. Nach etwa sechs
Monaten laufen die Tokens ab; dann einfach neu anmelden.

**Zustimmung zum Daten-Upload (EU-Konten):** Damit Workouts angelegt und an die Uhr
geschickt werden können, verlangt Garmin deine Zustimmung zum Hochladen von Daten. In
Garmin Connect unter *Einstellungen → Datenschutzeinstellungen → Daten* muss
**Gerätedaten hochladen** eingeschaltet sein (die Menünamen können je nach App-Version
leicht abweichen). Wenn deine Uhr schon Aktivitäten zu Garmin Connect synchronisiert,
ist das meist bereits der Fall. Ohne Zustimmung schlägt das Schreiben mit HTTP 412 fehl.

### 3. Home Assistant einmal neu starten

Beim ersten Start installiert die App ihre Hilfs-Integration. Die App-Seite zeigt dann
**„Home Assistant muss einmal neu gestartet werden“** mit einem Knopf dafür (zusätzlich
erscheint eine Benachrichtigung). Nach dem Neustart steht der Status auf **Aktiv** –
sonst ist nichts einzurichten. Bringt ein späteres App-Update eine neue Version der
Hilfs-Integration mit, zeigt Home Assistant einen **Reparatur-Hinweis**
(*Einstellungen → Reparaturen*) mit Knopf zum Neustarten – wie bei HACS.

Voraussetzung: Home Assistant ist bereits per HTTPS aus dem Internet erreichbar (Nabu
Casa, Cloudflare-Tunnel, Reverse Proxy …). Die App nimmt die externe Adresse aus
*Einstellungen → System → Netzwerk* (oder deine Nabu-Casa-Adresse). Findet sie keine,
trägst du sie in der App-Konfiguration als **Öffentliche Adresse** ein.

<details>
<summary>Alternative: eigener Hostname (<code>remote_access: direct</code>)</summary>

`remote_access: direct` einstellen und einen öffentlichen **HTTPS**-Hostnamen auf die
Zieladresse leiten, die die App-Seite anzeigt (z. B. mit `additional_hosts` in der
Cloudflared-App):

```yaml
additional_hosts:
  - hostname: garmin.example.com
    service: http://abcd1234-garmin-mcp:8100
```

Diesen Hostnamen als **Öffentliche Adresse** eintragen. Port 8100 nie ohne HTTPS am
Router freigeben.

Am besten stellst du `direct` vor dem ersten Start ein. Stellst du später um, entfernt
die App ihre Hilfs-Integration beim nächsten Start selbst (kein Neustart nötig). Zurück
auf `webhook` installiert sie wieder und bittet um einen Neustart. Beim Umstellen ändert
sich die Connector-URL.
</details>

### 4. KI-Assistenten verbinden

Die **Connector-URL** von der App-Seite kopieren. Sie sieht so aus:
`https://home.example.com/api/webhook/garmin_mcp_<geheim>` (bzw.
`https://garmin.example.com/<geheim>/mcp` bei `direct`).

* **Claude** (claude.ai, Desktop, Mobil): *Einstellungen → Konnektoren → Benutzerdefinierten
  Konnektor hinzufügen*, URL einfügen, keine Authentifizierung.
* **ChatGPT**: als benutzerdefinierten Connector / Remote-MCP-Server hinzufügen (Entwicklermodus).
* **Andere Programme** (Cursor, VS Code, Gemini CLI, Open WebUI …): einen Remote-MCP-Server
  mit dem Transport *Streamable HTTP* und der URL anlegen.

> **Nutzt du zusätzlich ha-mcp?** Läuft die [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)-App
> mit ihrem Webhook-Proxy (OAuth) auf demselben Home Assistant, fragt deine KI-App beim
> Hinzufügen dieses Connectors eventuell nach einer Anmeldung bei deinem Home Assistant
> und einer Zugriffsfreigabe. Das kommt von der Anmeldung von ha-mcp für deine Domain und
> ist unbedenklich – einfach bestätigen. Diese App selbst braucht keine Anmeldung.

## Sicherheit

* **Behandle die Connector-URL wie ein Passwort.** Wer sie kennt, kann dein Garmin-Konto
  über die freigegebenen Tools nutzen. Keine Screenshots oder Protokolle teilen, in denen
  sie steht. Ist sie bekannt geworden: **Neue geheime URL erzeugen** auf der App-Seite.
* **Worauf die App in Home Assistant zugreift:** Sie schreibt nur die Hilfs-Integration
  (`custom_components/garmin_mcp_webhook`) und deren Einstellungsdatei
  (`.garmin_mcp_webhook.json`) in den Konfigurationsordner und nutzt die
  Home-Assistant-API nur, um diese Integration einzurichten, die Neustart-Benachrichtigung
  anzuzeigen und – wenn du den Knopf drückst – Home Assistant neu zu starten. Sonst liest
  oder ändert sie nichts. Die Hilfs-Integration fragt zusätzlich alle 10 Minuten beim
  Supervisor nach, ob die App noch installiert ist, um sich nach dem Deinstallieren selbst
  zu entfernen. Mit `remote_access: direct` fasst sie den Konfigurationsordner
  gar nicht an.
* **Die KI kommt nicht an deine Dateien:** Datei-Tools (Strecke hochladen, Aktivität
  herunterladen) arbeiten nur im eigenen Download-Ordner der App. Der MCP-Server bekommt
  keinen Zugang zu Home Assistant und läuft als eingeschränkter Benutzer: Schreiben darf
  er nur seine Garmin-Tokens und Downloads – nicht den Home-Assistant-Konfigurationsordner,
  nicht die Geheimnisse der App und nicht die App-Seite.
* **Schreibrechte bewusst wählen** (siehe unten). `read_only` ist am sichersten;
  `create_only` (Standard) löscht oder überschreibt nie etwas.
* **Zusätzliche Absicherung – IP-Freigabeliste:** Nutzt du nur einen KI-Dienst, kannst du
  den Webhook-Pfad (`/api/webhook/garmin_mcp_*`) oder deinen eigenen Hostnamen auf dessen
  IP-Bereiche beschränken, z. B. mit einer Cloudflare-WAF-Regel. Claude verbindet sich aus
  `160.79.104.0/21` (siehe die von Anthropic veröffentlichten IP-Adressen). Andere
  KI-Dienste nutzen andere Bereiche und würden von so einer Regel ausgesperrt. Nach dem
  Einschalten testen.

## Verbindungstest

Der Knopf **Verbindung testen** auf der App-Seite prüft nacheinander:

1. ob der MCP-Server antwortet (und wie viele Tools er anbietet),
2. ob dein Garmin-Konto mit der gespeicherten Anmeldung erreichbar ist,
3. ob die Connector-URL **aus dem Internet** funktioniert – die App ruft ihre eigene
   öffentliche Adresse genau so auf wie deine KI-App.

Zu jedem fehlgeschlagenen Punkt steht ein Hinweis, was zu tun ist.

## Benachrichtigungen

* **Neustart nötig** – nach der Installation und nach Updates der Hilfs-Integration
  (Hinweis auf der App-Seite, Benachrichtigung, Reparatur-Hinweis).
* **Garmin-Anmeldung nicht mehr gültig** – z. B. wenn die Tokens nach etwa sechs Monaten
  abgelaufen sind oder widerrufen wurden. Vorübergehende Fehler (kein Internet nach einem
  Stromausfall, Garmin gestört) behebt die App selbst durch erneute Versuche; erst wenn das
  nicht klappt, zeigt Home Assistant eine Benachrichtigung (abschaltbar mit
  `login_notification`). Dann auf der App-Seite neu anmelden. Die KI-App bekommt in dem
  Fall eine verständliche Meldung statt eines Fehlers.

Benachrichtigungen erscheinen in der Sprache von Home Assistant
(*Einstellungen → System → Allgemein*).

## Sprache

Die App-Seite erscheint in der Sprache deines Browsers, sonst in der Sprache von Home
Assistant, sonst auf Englisch. Unten auf der Seite kannst du die Sprache umstellen; die
Wahl merkt sich dein Browser. Derzeit gibt es Deutsch und Englisch – eine weitere Sprache
hinzuzufügen ist einfach, siehe
[TRANSLATING.md](https://github.com/mw-hbg/ha-apps/blob/main/garmin_mcp/TRANSLATING.md).

## Tools auswählen

Die App-Seite zeigt pro Kategorie, was die KI darf. **Tools auswählen** öffnet eine Liste
aller Tools nach Kategorien mit Suchfeld, Vorlagen (*nur lesen*, *anlegen, nie löschen*,
*alles*, *nichts*), einem Häkchen pro Tool und einem **i**-Knopf, der erklärt, was das
Tool tut und welchen Zugriff es braucht (lesen / anlegen / ändern-löschen). Speichern
startet den Server neu.

Eine gespeicherte Auswahl ersetzt `tool_areas`, `write_access`, `enable_tools` und
`disable_tools` aus der Konfiguration.

**Nach Updates:** Tools, die eine neue Version mitbringt, sind in einer gespeicherten
Auswahl **ausgeschaltet**. App-Seite und Tool-Liste weisen darauf hin (markiert als
„neu“), damit du entscheiden kannst. Tools, die der Server nicht einstuft, gelten immer
als *ändern/löschen* – `read_only` und `create_only` schalten sie nie frei.
**Auf Konfiguration zurücksetzen** auf dieser Seite lässt wieder die Optionen gelten.

## Konfiguration

Alle Optionen stehen im Reiter **Konfiguration** der App. Änderungen gelten nach einem
Neustart der App; die App-Seite zeigt dann, wie viele Tools aktiv sind.

| Option | Beschreibung |
|---|---|
| `tool_areas` | Welche Teile von Garmin Connect die KI nutzen darf (mehrere kombinierbar): `all` (Standard) – alle Tools. `minimal` – kleiner Tagesüberblick (Aktivitäten, Schlaf, Stress, Body Battery, Trainingszustand). `health` – Schlaf, Herzfrequenz, Stress, Body Battery, Schritte, Gewicht, Blutdruck, Trinken, Zyklus. `activities` – Aktivitäten mit Details, Splits, Runden, Wetter, Ausrüstung, Strecken. `workouts` – Workouts, Trainingspläne, Kalender, Workouts einplanen, verschieben und an die Uhr senden. `training` – Trainingszustand, Trainingsbereitschaft, VO2max, HFV, Wettkampfprognosen, Bestleistungen, Challenges und Abzeichen. `nutrition` – Ernährungstagebuch, Mahlzeiten, eigene Lebensmittel. Weniger Tools = die KI arbeitet schneller und gezielter. |
| `write_access` | `read_only` – nur lesen. `create_only` (Standard) – darf zusätzlich Workouts anlegen und einplanen, an die Uhr senden und Einträge hinzufügen (Gewicht, Trinken, Essen, Blutdruck …), aber nie löschen oder überschreiben. `full` – auch löschen und bearbeiten (Aktivitäten, Workouts, Gewicht, Strecken, Einstellungen …). |
| `enable_tools` | Genaue Tool-Namen, die verfügbar sein sollen, obwohl `tool_areas` oder `write_access` sie ausschließen würden, z. B. `set_perceived_effort` oder `get_device_settings`. Unbekannte Namen (Tippfehler) zeigt die App-Seite als Warnung an. |
| `disable_tools` | Genaue Tool-Namen, die nie verfügbar sind, z. B. `delete_activity`. Hat immer Vorrang. |
| `remote_access` | `webhook` (Standard) – erreichbar über deine bestehende Home-Assistant-Adresse, braucht einen Neustart von Home Assistant. `direct` – du leitest einen eigenen HTTPS-Hostnamen auf Port 8100; beim Umstellen entfernt die App ihre Hilfs-Integration selbst. |
| `public_url` | Optional, meist leer. Deine öffentliche Home-Assistant-Adresse (webhook) bzw. dein eigener Hostname (direct); wird nur zum Anzeigen der Connector-URL und für den Verbindungstest gebraucht. Verwendet werden nur Schema und Host, eine kopierte Browser-Adresse geht also auch. Die App-Seite warnt, wenn sie ungültig ist oder `http://` nutzt. |
| `keep_downloads_days` | Aktivitätsdateien (FIT/GPX), die die KI herunterlädt, werden nach so vielen Tagen gelöscht (Standard 7, `0` = nie). Downloads landen nie in einem Home-Assistant-Backup. |
| `login_notification` | `true` (Standard): Benachrichtigung in Home Assistant, wenn die Garmin-Anmeldung nicht mehr funktioniert und die App das durch erneute Versuche nicht beheben konnte. |
| `log_level` | `debug`, `info` (Standard), `warning`, `error`. Nur `debug` protokolliert zusätzlich jede einzelne MCP-Anfrage. |

`tool_areas`, `write_access`, `enable_tools` und `disable_tools` werden ignoriert, sobald
du auf der App-Seite unter **Tools auswählen** eine eigene Auswahl speicherst (die Seite
zeigt dann „eigene Auswahl“). **Auf Konfiguration zurücksetzen** schaltet zurück.

> Geräte-Tools (Uhreinstellungen, Wecker, Solar) und `set_heart_rate_zones` gibt es nur bei
> `all`. Bei einzelnen Bereichen bei Bedarf über `enable_tools` ergänzen.
> Bei `workouts` nimmt die App automatisch `push_workout_to_device` und
> `reschedule_workout` dazu (die Schreibrechte gelten trotzdem).

### Beispiel: Trainingscoach ohne Löschrechte

```yaml
tool_areas:
  - activities
  - training
  - workouts
write_access: create_only
enable_tools:
  - set_perceived_effort
disable_tools: []
keep_downloads_days: 7
```

`push_workout_to_device` kommt mit `workouts` automatisch; `set_perceived_effort` ändert
eine vorhandene Aktivität und braucht bei `create_only` deshalb `enable_tools`.

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| Status *Garmin-Anmeldung fehlgeschlagen* | Tokens abgelaufen oder widerrufen. Auf der App-Seite abmelden und neu anmelden. |
| *Zu viele Anfragen* bei der Anmeldung | Garmin begrenzt Anmeldungen. Ein paar Minuten warten. |
| Workouts schreiben schlägt mit HTTP 412 fehl | Zustimmung zum Upload fehlt: Garmin Connect → Einstellungen → Datenschutzeinstellungen → Daten → *Gerätedaten hochladen*. |
| Bei der Anmeldung wird ein Code verlangt | Zwei-Faktor-Anmeldung ist aktiv – den Code eingeben, den Garmin geschickt hat. |
| KI-App will beim Hinzufügen eine Anmeldung bei Home Assistant | Kommt von ha-mcp (falls installiert), siehe Schritt 4. Bestätigen. |
| Status bleibt *Home Assistant muss einmal neu gestartet werden* | Home Assistant neu starten (Knopf auf der App-Seite oder *Einstellungen → System → Neu starten*). |
| Connector meldet *Server nicht erreichbar* | Prüfen, ob Home Assistant von außen erreichbar ist, ob die URL das aktuelle Geheimnis enthält und ob Firewall-/WAF-Regeln greifen. |
| Die KI sagt, das Tool gibt es nicht | Es ist durch `tool_areas`, `write_access` oder `disable_tools` abgeschaltet. |

## Deinstallieren

Einfach die App deinstallieren. Home Assistant führt beim Deinstallieren keinen Code der
App aus, deshalb räumt die Hilfs-Integration selbst auf: Alle 10 Minuten fragt sie den
Supervisor, ob die App noch installiert ist. Ist sie weg (zwei Prüfungen hintereinander,
also nach 10–20 Minuten), entfernt sie ihren Eintrag unter *Geräte & Dienste*, löscht
`custom_components/garmin_mcp_webhook` und `.garmin_mcp_webhook.json` und zeigt eine
Benachrichtigung. Ein Neustart ist nicht nötig. Ist Home Assistant in dem Moment aus,
passiert das nach dem nächsten Start.

Solange die App nur gestoppt ist oder der Supervisor nicht antwortet, wird nichts entfernt.

Von Hand entfernen geht auch: *Einstellungen → Geräte & Dienste → Garmin Connect MCP
(remote access) → Löschen*, dann den Ordner `custom_components/garmin_mcp_webhook` und die
Datei `.garmin_mcp_webhook.json` aus dem Konfigurationsordner löschen und Home Assistant
neu starten.

## Dank und Lizenzen

Der MCP-Server ist [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT) und
nutzt [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT). Der
Webhook-Ansatz folgt dem Webhook-Proxy von
[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) (MIT). Siehe `THIRD_PARTY_NOTICES.md`
im Repository.

## Alle Tools

*Art*: **lesen** = liest nur Daten · **anlegen** = fügt etwas Neues hinzu ·
**ändern/löschen** = ändert, überschreibt oder entfernt vorhandene Daten (nur mit
`write_access: full`). *Bereiche* nennt die `tool_areas`, die das Tool enthalten;
`–` heißt nur bei `all`. Die Tabelle wird aus dem Code erzeugt (`scripts/update_docs.py`).

<!-- tools:start -->
| Tool | Was es tut | Art | Bereiche |
|---|---|---|---|
| `add_body_composition` | Körperzusammensetzung eintragen. | anlegen | health |
| `add_gear_to_activity` | Ausrüstung einer Aktivität zuordnen. | anlegen | activities |
| `add_hydration_data` | Trinkmenge eintragen. | anlegen | health, nutrition |
| `add_weigh_in` | Neue Gewichtsmessung eintragen. | anlegen | health |
| `add_weigh_in_with_timestamps` | Neue Gewichtsmessung mit Zeitpunkt eintragen. | anlegen | health |
| `count_activities` | Gesamtzahl aller Aktivitäten abrufen. | lesen | activities |
| `create_custom_food` | Eigenes Lebensmittel anlegen. | anlegen | nutrition |
| `create_manual_activity` | Aktivität von Hand eintragen, z. B. ein Training ohne Uhr. | anlegen | activities |
| `create_run_interval_workout` | Intervall-Lauf-Workout anlegen. | anlegen | workouts |
| `create_run_workout` | Dauerlauf-Workout anlegen. | anlegen | workouts |
| `create_strength_workout` | Krafttraining-Workout anlegen. | anlegen | workouts |
| `create_walk_run_workout` | Geh-/Lauf-Intervall-Workout anlegen. | anlegen | workouts |
| `create_z2_walk_workout` | Gleichmäßiges Geh-Workout in Zone 2 anlegen. | anlegen | workouts |
| `delete_activity` | Aktivität endgültig aus Garmin Connect löschen. | ändern/löschen | activities |
| `delete_course` | Strecke löschen. | ändern/löschen | activities |
| `delete_custom_food` | Eigenes Lebensmittel löschen. | ändern/löschen | nutrition |
| `delete_food_log` | Eintrag aus dem Ernährungstagebuch löschen. | ändern/löschen | nutrition |
| `delete_weigh_ins` | Gewichtsmessungen eines Tages löschen. | ändern/löschen | health |
| `delete_workout` | Workout aus Garmin Connect löschen. | ändern/löschen | workouts |
| `delete_workouts` | Mehrere Workouts auf einmal löschen. | ändern/löschen | workouts |
| `download_activity_file` | Aktivität als Datei herunterladen (in der App gespeichert). | ändern/löschen | activities |
| `download_course_gpx` | Strecke als GPX-Datei herunterladen. | ändern/löschen | activities |
| `download_workout` | Workout als FIT-Datei herunterladen. | ändern/löschen | workouts |
| `get_acclimation` | Hitze- und Höhenakklimatisierung abrufen. | lesen | training |
| `get_activities` | Aktivitäten seitenweise abrufen. | lesen | minimal, activities |
| `get_activities_by_date` | Aktivitäten in einem Zeitraum abrufen. | lesen | minimal, activities |
| `get_activities_fordate` | Aktivitäten eines bestimmten Tages abrufen. | lesen | activities |
| `get_activity` | Details zu einer einzelnen Aktivität abrufen. | lesen | minimal, activities |
| `get_activity_exercise_sets` | Übungssätze eines Krafttrainings abrufen. | lesen | activities |
| `get_activity_fit_data` | Detaildaten (z. B. Radsensoren) aus der FIT-Datei auslesen. | lesen | activities |
| `get_activity_fit_messages` | Originale FIT-Datei einer Aktivität auslesen. | lesen | activities |
| `get_activity_gear` | Bei einer Aktivität verwendete Ausrüstung abrufen. | lesen | activities |
| `get_activity_hr_in_timezones` | Zeit in den Herzfrequenzzonen während einer Aktivität abrufen. | lesen | activities |
| `get_activity_power_in_timezones` | Zeit in den Leistungszonen während einer Aktivität abrufen. | lesen | activities |
| `get_activity_split_summaries` | Zusammenfassungen der Zwischenzeiten abrufen. | lesen | activities |
| `get_activity_splits` | Zwischenzeiten (Splits) einer Aktivität abrufen. | lesen | minimal, activities |
| `get_activity_typed_splits` | Zwischenzeiten nach Typ (z. B. Laufen/Gehen) abrufen. | lesen | activities |
| `get_activity_types` | Alle verfügbaren Sportarten abrufen. | lesen | activities |
| `get_activity_weather` | Wetter während einer Aktivität abrufen. | lesen | activities |
| `get_adhoc_challenges` | Selbst erstellte Gruppen-Challenges abrufen. | lesen | training |
| `get_all_day_events` | Tagesereignisse (z. B. erkannte Aktivitäten) abrufen. | lesen | health |
| `get_all_day_stress` | Stresswerte über den ganzen Tag abrufen. | lesen | health |
| `get_available_badge_challenges` | Verfügbare offizielle Abzeichen-Challenges abrufen. | lesen | training |
| `get_badge_challenges` | Abgeschlossene Abzeichen-Challenges abrufen. | lesen | training |
| `get_blood_pressure` | Blutdruckwerte abrufen. | lesen | health |
| `get_body_battery` | Body Battery mit Ereignissen abrufen. | lesen | minimal, health |
| `get_body_battery_events` | Body-Battery-Ereignisse abrufen. | lesen | health |
| `get_body_composition` | Körperzusammensetzung für einen Tag oder Zeitraum abrufen. | lesen | health |
| `get_calendar_events` | Wettkämpfe und Veranstaltungen im Kalender abrufen. | lesen | workouts |
| `get_course_details` | Details einer Strecke abrufen. | lesen | activities |
| `get_courses` | Gespeicherte Strecken abrufen. | lesen | activities |
| `get_custom_food_serving_units` | Portionseinheiten für eigene Lebensmittel abrufen. | lesen | nutrition |
| `get_custom_foods` | Eigene Lebensmittel abrufen. | lesen | nutrition |
| `get_cycling_ftp` | Aktuelle FTP (Radfahren) abrufen. | lesen | training |
| `get_daily_steps` | Schritte pro Tag für einen Zeitraum abrufen. | lesen | minimal, health |
| `get_daily_weigh_ins` | Gewichtsmessungen eines Tages abrufen. | lesen | health |
| `get_device_alarms` | Wecker aller Geräte abrufen. | lesen | – |
| `get_device_last_used` | Zuletzt verwendetes Gerät abrufen. | lesen | – |
| `get_device_settings` | Einstellungen eines Geräts abrufen. | lesen | – |
| `get_device_solar_data` | Solardaten eines Geräts abrufen. | lesen | – |
| `get_devices` | Alle deine Garmin-Geräte abrufen. | lesen | – |
| `get_earned_badges` | Erhaltene Abzeichen abrufen. | lesen | training |
| `get_endurance_score` | Endurance Score in einem Zeitraum abrufen. | lesen | training |
| `get_energy_balance` | Energiebilanz aus Ernährung, Verbrauch und Körperzusammensetzung schätzen. | lesen | health, nutrition |
| `get_fitnessage_data` | Fitnessalter abrufen. | lesen | health, training |
| `get_floors` | Gestiegene Stockwerke abrufen. | lesen | health |
| `get_full_name` | Deinen Namen aus dem Profil abrufen. | lesen | minimal, health, activities, workouts, training, nutrition |
| `get_garmin_coach_workouts` | Workouts aus Garmin Coach abrufen. | lesen | workouts |
| `get_gear` | Deine Ausrüstung (z. B. Laufschuhe) abrufen. | lesen | activities |
| `get_goals` | Deine Ziele abrufen (aktiv, künftig, vergangen). | lesen | training |
| `get_heart_rate_zones` | Deine Herzfrequenzzonen abrufen. | lesen | minimal, health, activities, workouts, training, nutrition |
| `get_heart_rates` | Herzfrequenz-Verlauf des Tages abrufen. | lesen | health |
| `get_heart_rates_summary` | Zusammenfassung der Herzfrequenz abrufen. | lesen | minimal, health |
| `get_hill_score` | Hill Score in einem Zeitraum abrufen. | lesen | training |
| `get_hrv_data` | Herzfrequenzvariabilität (HRV) abrufen. | lesen | minimal, health, training |
| `get_hrv_trend` | HRV-Verlauf über einen Zeitraum abrufen. | lesen | health, training |
| `get_hydration_data` | Trinkmenge abrufen. | lesen | health, nutrition |
| `get_inprogress_virtual_challenges` | Laufende virtuelle Challenges abrufen. | lesen | training |
| `get_lactate_threshold` | Laktatschwelle abrufen. | lesen | training |
| `get_lifestyle_logging_data` | Lifestyle-Protokoll eines Tages abrufen. | lesen | health |
| `get_menstrual_calendar_data` | Zykluskalender für einen Zeitraum abrufen. | lesen | health |
| `get_menstrual_data_for_date` | Zyklusdaten eines Tages abrufen. | lesen | health |
| `get_morning_training_readiness` | Trainingsbereitschaft am Morgen abrufen. | lesen | health, training |
| `get_non_completed_badge_challenges` | Laufende Abzeichen-Challenges abrufen. | lesen | training |
| `get_nutrition_daily_food_log` | Ernährungstagebuch eines Tages abrufen. | lesen | nutrition |
| `get_nutrition_daily_meals` | Mahlzeiten eines Tages abrufen. | lesen | nutrition |
| `get_nutrition_daily_settings` | Ernährungsziele eines Tages abrufen. | lesen | nutrition |
| `get_nutrition_summary_between_dates` | Nährwerte pro Tag für einen Zeitraum abrufen. | lesen | nutrition |
| `get_personal_record` | Persönliche Bestleistungen abrufen. | lesen | training |
| `get_power_duration_curve` | Leistungskurve (Bestwerte) über die letzten Aktivitäten abrufen. | lesen | activities, training |
| `get_pregnancy_summary` | Schwangerschafts-Zusammenfassung abrufen. | lesen | health |
| `get_primary_training_device` | Hauptgerät fürs Training abrufen. | lesen | training |
| `get_progress_summary_between_dates` | Fortschritt eines Messwerts in einem Zeitraum abrufen. | lesen | training |
| `get_race_predictions` | Prognostizierte Wettkampfzeiten abrufen (5 km bis Marathon). | lesen | training |
| `get_recovery_time_remaining` | Verbleibende Erholungszeit in Stunden abrufen. | lesen | health, training |
| `get_respiration_data` | Atemfrequenz-Verlauf abrufen. | lesen | health |
| `get_respiration_summary` | Zusammenfassung der Atemfrequenz abrufen. | lesen | health |
| `get_respiration_trend` | Verlauf der nächtlichen Atemfrequenz abrufen. | lesen | health, training |
| `get_rhr_day` | Ruhepuls abrufen. | lesen | health |
| `get_running_tolerance` | Lauftoleranz eines Tages abrufen. | lesen | training |
| `get_running_tolerance_trend` | Verlauf der Lauftoleranz abrufen. | lesen | training |
| `get_scheduled_workouts` | Geplante Workouts in einem Zeitraum abrufen. | lesen | workouts |
| `get_sleep_data` | Schlafdaten mit allen Details abrufen. | lesen | minimal, health |
| `get_sleep_summary` | Kurze Schlafzusammenfassung abrufen. | lesen | minimal, health |
| `get_sleep_summary_range` | Schlafzusammenfassung für jede Nacht eines Zeitraums abrufen. | lesen | health |
| `get_spo2_data` | Blutsauerstoff (SpO2) abrufen. | lesen | health |
| `get_stats` | Tageswerte abrufen (Schritte, Kalorien, Herzfrequenz …). | lesen | minimal, health |
| `get_stats_and_body` | Tageswerte und Körperzusammensetzung zusammen abrufen. | lesen | health |
| `get_stats_range` | Kalorien und Schritte pro Tag für einen Zeitraum abrufen. | lesen | health |
| `get_steps_data` | Schritte in 15-Minuten-Abschnitten abrufen. | lesen | health |
| `get_stress_data` | Stress-Verlauf des Tages abrufen. | lesen | health |
| `get_stress_summary` | Stress-Zusammenfassung abrufen. | lesen | minimal, health |
| `get_training_effect` | Trainingseffekt einer Aktivität abrufen. | lesen | training |
| `get_training_load_balance` | Belastungsfokus abrufen (Verteilung auf aerob niedrig/hoch und anaerob). | lesen | training |
| `get_training_load_trend` | Akute und chronische Trainingsbelastung über einen Zeitraum abrufen. | lesen | training |
| `get_training_plan_workouts` | Workouts aus Garmin Coach abrufen (ältere Bezeichnung). | lesen | workouts |
| `get_training_readiness` | Trainingsbereitschaft abrufen. | lesen | minimal, health, training |
| `get_training_status` | Trainingszustand abrufen. | lesen | minimal, training |
| `get_unit_system` | Bevorzugte Maßeinheiten abrufen. | lesen | minimal, health, activities, workouts, training, nutrition |
| `get_user_profile` | Profilinformationen abrufen. | lesen | minimal, health, activities, workouts, training, nutrition |
| `get_user_summary` | Tageszusammenfassung abrufen. | lesen | minimal, health |
| `get_userprofile_settings` | Profileinstellungen abrufen. | lesen | minimal, health, activities, workouts, training, nutrition |
| `get_vo2max_trend` | VO2max-Verlauf über einen Zeitraum abrufen. | lesen | training |
| `get_weekly_intensity_minutes` | Intensitätsminuten pro Woche abrufen. | lesen | health, training |
| `get_weekly_steps` | Schritte pro Woche abrufen. | lesen | health |
| `get_weekly_stress` | Stress pro Woche abrufen. | lesen | health |
| `get_weigh_ins` | Gewichtsmessungen in einem Zeitraum abrufen. | lesen | health |
| `get_workout_by_id` | Details eines Workouts abrufen. | lesen | workouts |
| `get_workouts` | Deine Workout-Bibliothek abrufen. | lesen | workouts |
| `log_custom_food` | Lebensmittel einer Mahlzeit hinzufügen. | anlegen | nutrition |
| `log_food` | Schnell einen Eintrag mit Nährwerten ins Ernährungstagebuch schreiben. | anlegen | nutrition |
| `push_workout_to_device` | Workout aus der Bibliothek an die Uhr senden. | anlegen | workouts |
| `remove_gear_from_activity` | Ausrüstung von einer Aktivität entfernen. | ändern/löschen | activities |
| `request_reload` | Garmin bitten, die Tagesdaten neu zu berechnen. | anlegen | training |
| `reschedule_workout` | Geplantes Workout auf ein anderes Datum verschieben. | ändern/löschen | workouts |
| `schedule_week` | Mehrere Workouts für eine Woche auf einmal einplanen. | anlegen | workouts |
| `schedule_workout` | Workout für ein Datum im Kalender einplanen. | anlegen | workouts |
| `schedule_workouts` | Mehrere Workouts im Kalender einplanen. | anlegen | workouts |
| `search_foods` | Lebensmittel im Garmin-Katalog suchen. | lesen | nutrition |
| `set_activity_description` | Beschreibung bzw. Notizen einer Aktivität setzen oder ändern. | ändern/löschen | activities |
| `set_activity_event_type` | Ereignistyp einer Aktivität setzen (z. B. Wettkampf, Training). | ändern/löschen | activities |
| `set_activity_exercise_sets` | Übungssätze eines Krafttrainings ersetzen (überschreibt die vorhandenen). | ändern/löschen | activities |
| `set_activity_feel` | Eintragen, wie sich eine Aktivität angefühlt hat. | ändern/löschen | activities |
| `set_activity_name` | Namen einer Aktivität setzen oder ändern. | ändern/löschen | activities |
| `set_activity_type` | Sportart einer Aktivität ändern. | ändern/löschen | activities |
| `set_blood_pressure` | Blutdruck eintragen. | anlegen | health |
| `set_fit_download_dir` | Speicherort für heruntergeladene Dateien festlegen. | anlegen | activities |
| `set_heart_rate_zones` | Herzfrequenzzonen für eine Sportart ändern (überschreibt die vorhandenen). | ändern/löschen | – |
| `set_nutrition_daily_settings` | Ernährungsziele ändern (Kalorien, Makronährstoffe). | ändern/löschen | nutrition |
| `set_perceived_effort` | Empfundene Anstrengung (RPE) einer Aktivität eintragen. | ändern/löschen | activities |
| `unschedule_workout` | Geplantes Workout aus dem Kalender entfernen. | ändern/löschen | workouts |
| `unschedule_workouts` | Mehrere geplante Workouts aus dem Kalender entfernen. | ändern/löschen | workouts |
| `update_custom_food` | Eigenes Lebensmittel ändern. | ändern/löschen | nutrition |
| `upload_course` | GPX-Datei als Strecke hochladen. | anlegen | activities |
| `upload_workout` | Workout aus einer Beschreibung anlegen. | anlegen | workouts |
| `upload_workouts` | Mehrere Workouts auf einmal anlegen. | anlegen | workouts |
| `upsert_and_log` | Eigenes Lebensmittel finden oder anlegen und direkt eintragen. | anlegen | nutrition |
<!-- tools:end -->
