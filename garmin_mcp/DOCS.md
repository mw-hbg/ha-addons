# Garmin Connect MCP

[English](#english) · [Deutsch](#deutsch)

## English

This app runs an [MCP](https://modelcontextprotocol.io) server for your
Garmin Connect account inside Home Assistant. AI assistants that support remote
MCP servers – Claude, ChatGPT and many others – can then read your training and
health data and, if you allow it, create workouts and schedule them on your
watch.

> **Unofficial.** This project is not affiliated with or endorsed by Garmin.
> Garmin offers no public API for individuals, so the app uses the same
> private endpoints as the Garmin Connect website (via
> [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)).
> Garmin may change or block this at any time. Use at your own risk.

### How it works

```
AI assistant ──HTTPS──► your Home Assistant address ──► /api/webhook/<secret id> ──► app ──► Garmin Connect
                        (Nabu Casa, Cloudflare Tunnel,   (helper integration)
                         reverse proxy …)
```

* By default the app is reached through the address you already use to
  access Home Assistant from outside – **no extra hostname, tunnel or port
  forwarding**. A small helper integration (`garmin_mcp_webhook`), installed by
  the app, provides a Home Assistant webhook with a long random id and
  forwards requests to the app.
* Alternatively (`remote_access: direct`) you route your own HTTPS hostname to
  the app's port 8100.
* The MCP server itself listens on loopback only. An nginx in front of it only
  forwards requests that carry a long random **secret path**; everything else
  gets a `404`.
* The app page (sidebar → **Garmin MCP**) is only reachable through Home
  Assistant and only for administrators.
* Your Garmin password is never stored. After logging in, only the OAuth tokens
  Garmin issues are kept in the app's private storage (valid for about six
  months).
* **Log out and delete tokens** removes the tokens from the app. Garmin
  itself is not notified, so tokens that might have been copied elsewhere stay
  valid until they expire. To revoke them everywhere, change your Garmin
  password.

### Setup

Requires Home Assistant **2026.2** or newer (OS or Supervised). The app is
marked *experimental* until version 1.0.

#### 1. Install and start

*Settings → Apps → Install app → ⋮ → Repositories*, add
`https://github.com/mw-hbg/ha-garmin-mcp` (formerly `mw-hbg/ha-apps` – if you added an old
address, keep it; it forwards). Then install **Garmin Connect MCP**, start it and
open **Garmin MCP** in the sidebar (or **Open Web UI** on the app page).

#### 2. Log in to Garmin Connect

Enter your Garmin e-mail and password.

**Two-factor authentication** is supported. If it is enabled for your Garmin
account, Garmin sends you a code (app, e-mail or SMS) and the app asks for
it on the next screen. You only need it at login – not for every request.
After about six months the tokens expire; then simply log in again.

**Data upload consent (EU accounts):** to create workouts and send them to your
watch, Garmin requires your consent to data uploads. In Garmin Connect go to
*Settings → Privacy settings → Data* and make sure **Upload device data** is
switched on (menu names can differ slightly between app versions and
languages). If your watch already syncs activities to Garmin Connect, this is
usually already the case. Without it, writing fails with HTTP 412.

#### 3. Restart Home Assistant once

On first start the app copies its helper integration into Home Assistant. The app page
then shows **“Home Assistant must be restarted once”**: restart via *Settings →
System → Restart*. Home Assistant itself shows **no notification** for this first
restart – the app has no access to its API, and the helper integration only runs after
the restart. After the restart Home Assistant sets the integration up by itself
(the app announces its settings through Home Assistant's official app discovery) and
the status changes to **Active** – nothing else to set up. When a later app update
brings a new version of the helper integration, Home Assistant shows a **repair
notice** (*Settings → Repairs*) with a button to restart, just like HACS does.

Requirement: Home Assistant must already be reachable from the internet over
HTTPS (Nabu Casa, Cloudflare Tunnel, reverse proxy, …). The app uses the
external URL from *Settings → System → Network* (or your Nabu Casa address).
If it cannot work it out, enter it as **Public address** in the app
configuration.

<details>
<summary>Alternative: own hostname (<code>remote_access: direct</code>)</summary>

Set `remote_access: direct`, then route a public **HTTPS** hostname to the
target address shown on the app page (e.g. with `additional_hosts` in the
Cloudflared app):

```yaml
additional_hosts:
  - hostname: garmin.example.com
    service: http://abcd1234-garmin-mcp:8100
```

Enter that hostname as **Public address**. Never forward port 8100 on your
router without HTTPS.

Best set `direct` before the first start. If you switch later, the app
removes its helper integration from Home Assistant by itself on the next start
(no restart needed). Switching back to `webhook` installs it again and asks for
one restart. The connector URL changes when you switch.
</details>

#### 4. Connect your AI assistant

Copy the **Connector URL** from the app page. It looks like
`https://home.example.com/api/webhook/garmin_mcp_<secret>` (or
`https://garmin.example.com/<secret>/mcp` in direct mode).

* **Claude** (claude.ai, desktop, mobile): *Settings → Connectors → Add custom
  connector*, paste the URL, no authentication. One custom connector is included in the
  free plan.
* **Mistral Vibe** (formerly Le Chat, chat.mistral.ai – also free): *Intelligence →
  Connectors → Add Connector → Custom MCP Connector*, any name without spaces (e.g.
  `GarminConnect`), paste the URL, no authentication. Then switch the connector on in a chat.
* **ChatGPT** (Plus or higher): enable developer mode, then add the URL as a custom
  connector / remote MCP server.
* **Other clients** (Cursor, VS Code, Gemini CLI, Open WebUI, …): add a remote
  MCP server using the *Streamable HTTP* transport and the URL.

> **Using ha-mcp as well?** If the [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)
> app with its webhook proxy (OAuth) runs on the same Home Assistant, your
> AI app may ask you to log in to your Home Assistant and grant access when
> you add this connector. That prompt comes from ha-mcp's sign-in for your
> domain and is harmless – confirm it. This app itself needs no sign-in.

### Security

* **Treat the connector URL like a password.** Anyone who knows it can use your
  Garmin account through the enabled tools. Don't share screenshots or logs that
  contain it. If it leaks, click **Generate new secret URL** on the app page.
* **The app has no access to Home Assistant's API** – it cannot read, switch or
  change anything in Home Assistant. Its only access is the configuration folder,
  and only for one thing: copying the helper integration into
  `custom_components/garmin_mcp_webhook` (and removing it again in direct mode).
  Home Assistant cannot map a single folder, so the whole folder is mapped; only the
  app's internal part uses it, which is not reachable from outside.
* **Settings travel through the official discovery service** of the Supervisor:
  the app announces the webhook id and its internal address, Home Assistant sets up
  the integration from it. In return, the integration reports to the app every
  minute (internal network only, protected by the secret path and a key): your
  external address and language for the app page, and it asks for the Garmin login
  state to show a repair notice. Nothing in this exchange can change Home Assistant.
* **From the internet** only the MCP endpoint is reachable (through the webhook or
  your own hostname). It only runs Garmin tools – there is no path from it to Home
  Assistant or to the app page.
* **AppArmor profile for the whole app:** the Linux kernel limits every process of the
  app – including its internal part – to what it needs. In the Home Assistant
  configuration folder it can only touch `custom_components/garmin_mcp_webhook`; it
  cannot read `secrets.yaml` or change anything else there, start other programs than
  Python and nginx or change system settings. Home Assistant rates the app 8 of 8.
* **The MCP server is locked in:** it runs as an unprivileged user, so it cannot read
  the app's secrets or change the helper integration; the AppArmor profile keeps it out
  of the rest of the Home Assistant configuration folder (not even reading). Where the
  Linux kernel offers *Landlock*, it additionally restricts itself to its own folders
  (Garmin tokens, downloads). Home Assistant OS currently does not offer Landlock – the
  app log then says *Landlock is not available here*; that is expected. File tools
  (upload a course, download an activity) only work inside the download folder.
* **Choose the write access level deliberately** (see below). `read_only` is the
  safest; `create_only` (default) never deletes or overwrites anything.
* **Optional extra layer – IP allow list:** if you only use one AI service, you
  can restrict the webhook path (`/api/webhook/garmin_mcp_*`) or your own
  hostname to that service's IP ranges, e.g. with a Cloudflare WAF rule. Claude connects from `160.79.104.0/21` (see Anthropic's
  published IP addresses). Other AI services use other ranges and would be
  blocked by such a rule. Test after enabling it.

### Connection test

The **Test connection** button on the app page checks, one after another:

1. the MCP server answers (and how many tools it offers),
2. your Garmin account can be reached with the saved login,
3. the connector URL works **from the internet** – the app calls its own
   public address, exactly the way your AI app does.

Each failed check comes with a hint what to do.

### Notifications

Shown by the helper integration as **repair notices** (*Settings → Repairs*), in the
Home Assistant language:

* **Restart required** – after updates of the helper integration (with a restart
  button). After the first installation the app page shows the hint.
* **Garmin login no longer valid** – e.g. when the tokens expired after about six
  months or were revoked. Temporary errors (no internet after a power cut, Garmin
  down) are fixed by the app itself by retrying; only if that does not help, the
  notice appears (can be switched off with `login_notification`). Log in again on the
  app page – the notice then disappears by itself. The AI app gets a clear message
  instead of an error.

### Switching the server off

The helper integration adds a device **Garmin Connect MCP <name>** per Garmin account,
each with the switch **Garmin Connect MCP <name> Server** (webhook mode only). Turn it
off and no AI app can reach the Garmin data of this account any more: Home Assistant answers every request itself with "switched
off" – nothing is forwarded to the app – and the app stops its Garmin server. Login,
settings and connector URL stay; turn the switch on and everything works again within
seconds. The state survives restarts.

The switch is a normal entity: use it in automations (e.g. off at night or while you
are on holiday), on dashboards or with voice assistants. The app page shows
*Switched off in Home Assistant* while it is off. A switched-off account needs no memory
for its Garmin server.

### Several Garmin accounts

One app can serve up to **10 Garmin accounts** – e.g. everyone in the household with
their own AI app. **Add Garmin account** on the app page creates a new card; log in there.
Every account has:

* its own Garmin login (incl. two-factor authentication) and its **own connector URL** –
  each person adds only their own URL to their AI app,
* its own connection test, **Generate new secret URL**, log out and **Remove account**,
* its own device and switch in Home Assistant and its own repair notice
  (“Garmin login of <name> no longer valid”),
* its own Garmin server, running as its own unprivileged user: no account can read another
  account's tokens.

**Name:** by default the name from the Garmin profile; ✏️ next to it sets your own name.
It is shown on the page and in Home Assistant (device, switch); entity IDs stay the same.

**Rights:** with **Same settings for all accounts** (default) write access and tool
choice from the configuration apply to every account. Untick it to set write access,
areas and tools per account (*Rights of this account* in each card).

**Load:** every running account needs roughly 70–80 MB of memory. From the 4th account
the page shows a warning – fine on a Raspberry Pi 5, possibly too much on devices with
1–2 GB.

**Who sees what:** the app page is only available to Home Assistant **administrators**,
and every administrator sees and manages **all** accounts, including their connector
URLs. Only add accounts of people who trust each other's admins.

**Updating from an earlier version:** your existing login becomes the first account –
same connector URL, same switch (`switch.garmin_connect_mcp_server`), nothing to redo.
Home Assistant asks for one restart (new helper integration).

### Language

The app page uses your browser language, otherwise the Home Assistant language,
otherwise English. You can switch the language at the bottom of the page; your browser
remembers the choice. English and German are available – adding another language is
easy, see [TRANSLATING.md](https://github.com/mw-hbg/ha-garmin-mcp/blob/main/garmin_mcp/TRANSLATING.md).

### Choosing tools

The app page shows, per category, what the AI may do (for all accounts, or per account
when they do not share their settings). **Choose tools** opens
a list of all tools grouped by category, with a search field, presets
(*read only*, *create, never delete*, *everything*, *nothing*), a checkbox per
tool and an **i** button explaining what each tool does and what kind of access
it needs (read / create / change-delete). Saving restarts the server.

A saved selection replaces `tool_areas`, `write_access`, `enable_tools` and
`disable_tools` from the configuration.

**After updates:** tools that a new version brings are **switched off** in a
saved selection. The app page and the tool list point them out (marked
“new”) so you can decide. Tools the server does not classify are always
treated as *change/delete* – they are never enabled by `read_only` or
`create_only`. **Reset to configuration** on that page
brings those options back into effect.

### Configuration

All options are on the **Configuration** tab of the app. Changes take effect after
restarting the app; the app page then shows how many tools are active.

| Option | Description |
|---|---|
| `tool_areas` | Which parts of Garmin Connect the AI may use (several can be combined): `all` (default) – every tool. `minimal` – a small daily overview (activities, sleep, stress, Body Battery, training status). `health` – sleep, heart rate, stress, Body Battery, steps, weight, blood pressure, hydration, cycle. `activities` – activities with details, splits, laps, weather, gear, courses. `workouts` – workouts, training plans, calendar, scheduling and moving workouts, sending them to the watch. `training` – training status, readiness, VO2 max, HRV, race predictions, records, challenges and badges. `nutrition` – food log, meals, custom foods. Fewer tools keep the AI faster and more focused. |
| `write_access` | `read_only` – reading only. `create_only` (default) – may also create and schedule workouts, send them to the watch and add entries (weigh-ins, hydration, food logs, blood pressure …), but never delete or overwrite. `full` – also delete and edit (activities, workouts, weigh-ins, courses, settings …). |
| `enable_tools` | Exact tool names to allow although `tool_areas` or `write_access` would exclude them, e.g. `set_perceived_effort` or `get_device_settings`. Unknown names (typos) are shown as a warning on the app page. |
| `disable_tools` | Exact tool names that are never available, e.g. `delete_activity`. Always wins. |
| `remote_access` | `webhook` (default) – reachable through your existing Home Assistant address, needs one Home Assistant restart. `direct` – you route your own HTTPS hostname to port 8100; switching to it removes the helper integration automatically. |
| `public_url` | Optional, usually empty. Your public Home Assistant address (webhook) or your own hostname (direct), only used to show the connector URL and for the connection test. Only scheme and host are used, so a copied browser address works too. The app page warns if it is invalid or uses `http://`. |
| `keep_downloads_days` | Activity files (FIT/GPX) the AI downloads are deleted after this many days (default 7, `0` = never). Downloads are never part of a Home Assistant backup. |
| `login_notification` | `true` (default): repair notice in Home Assistant if the Garmin login stops working and the app could not fix it by retrying. |
| `log_level` | `debug`, `info` (default), `warning`, `error`. Only `debug` also logs every single MCP request. |

`tool_areas`, `write_access`, `enable_tools` and `disable_tools` are ignored as soon as you
save your own selection under **Choose tools** on the app page (the page then shows
“custom selection”). **Reset to configuration** there switches back.

> Device tools (watch settings, alarms, solar) and `set_heart_rate_zones` are only part of
> `all`. With specific areas, add them via `enable_tools` when you need them.
> With `workouts`, the app automatically adds `push_workout_to_device` and
> `reschedule_workout` (still subject to `write_access`).

#### Example: training coach without delete rights

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

`push_workout_to_device` comes with `workouts` automatically, `set_perceived_effort`
changes an existing activity and therefore needs `enable_tools` with `create_only`.

### Troubleshooting

| Problem | Solution |
|---|---|
| Status *Garmin login failed* | Tokens expired or were revoked (e.g. Garmin password changed). Click **Log in again** on the app page – settings and connector URL stay the same. |
| *Too many requests* during login | Garmin rate-limits logins. Wait a few minutes. |
| Writing workouts fails with HTTP 412 | Upload consent missing: Garmin Connect → Settings → Privacy settings → Data → *Upload device data*. |
| Asked for a code at login | Two-factor authentication is enabled – enter the code Garmin sent you. |
| AI app asks to log in to Home Assistant when adding the connector | Comes from ha-mcp (if installed), see step 4. Confirm it. |
| Status stays *Home Assistant must be restarted once* | Restart Home Assistant (*Settings → System → Restart*). If it stays after the restart, check *Settings → System → Logs* for `garmin_mcp_webhook`. |
| Connector shows *couldn't reach the server* | Check that Home Assistant is reachable from outside, that the URL contains the current secret, and any firewall/WAF rules. |
| The AI says the tool does not exist | It is disabled by `tool_areas`, `write_access` or `disable_tools`. |

### Uninstalling

Just uninstall the app. The Supervisor then withdraws the app's announcement and Home
Assistant removes the integration's entry under *Devices & services* by itself – the
webhook is gone immediately. The helper integration then deletes its folder
`custom_components/garmin_mcp_webhook` and shows a notification. No restart is needed.

If Home Assistant was off during the uninstall, the helper notices it after the next
start: every 10 minutes it asks the Supervisor whether the app is still installed and
removes itself once the app is missing in two checks in a row. Nothing is removed while
the app is only stopped, or if the Supervisor cannot be asked.

To remove the integration by hand instead: *Settings → Devices & services → Garmin
Connect MCP (remote access) → Delete*, then delete the folder
`custom_components/garmin_mcp_webhook` from your configuration folder and restart Home
Assistant.

### Credits and licenses

The MCP server is [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)
(MIT), using [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
(MIT). The webhook approach follows the webhook proxy of
[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) (MIT). See `THIRD_PARTY_NOTICES.md` in the repository.

### All tools

*Type*: **read** = only reads data · **create** = adds something new ·
**change/delete** = changes, overwrites or removes existing data (only with
`write_access: full`). *Areas* lists the `tool_areas` that include the tool;
`–` means only `all`. This table is generated from the code
(`scripts/update_docs.py`).

<!-- tools:en:start -->
| Tool | What it does | Type | Areas |
|---|---|---|---|
| `add_body_composition` | Add body composition data. | create | health |
| `add_gear_to_activity` | Associate gear with an activity. | create | activities |
| `add_hydration_data` | Add hydration data. | create | health, nutrition |
| `add_weigh_in` | Add a new weight measurement. | create | health |
| `add_weigh_in_with_timestamps` | Add a new weight measurement with specific timestamps. | create | health |
| `count_activities` | Get total count of activities in the user's Garmin account. | read | activities |
| `create_custom_food` | Create a custom food in the user's Garmin nutrition library. | create | nutrition |
| `create_manual_activity` | Log a manual activity in Garmin Connect — useful for activities done without a watch. | create | activities |
| `create_run_interval_workout` | Create a repeat-based interval run workout and upload it to Garmin Connect. | create | workouts |
| `create_run_workout` | Create a continuous run workout and upload it to Garmin Connect. | create | workouts |
| `create_strength_workout` | Create a strength workout and upload it to Garmin Connect. | create | workouts |
| `create_walk_run_workout` | Create a walk/run interval workout and upload it to Garmin Connect. | create | workouts |
| `create_z2_walk_workout` | Create a steady Z2 walking workout and upload it to Garmin Connect. | create | workouts |
| `delete_activity` | Permanently delete an activity from Garmin Connect. | change/delete | activities |
| `delete_course` | Delete a course from Garmin Connect. | change/delete | activities |
| `delete_custom_food` | Delete a custom food from the user's Garmin nutrition library. | change/delete | nutrition |
| `delete_food_log` | Delete a food log entry. | change/delete | nutrition |
| `delete_weigh_ins` | Delete weight measurements for a specific date. | change/delete | health |
| `delete_workout` | Delete a workout from Garmin Connect. | change/delete | workouts |
| `delete_workouts` | Delete multiple workouts from Garmin Connect in a single call. | change/delete | workouts |
| `download_activity_file` | Download an activity and save it to disk as a file. | change/delete | activities |
| `download_course_gpx` | Download a Garmin Connect course as a GPX file. | change/delete | activities |
| `download_workout` | Download a workout as a FIT file. | change/delete | workouts |
| `get_acclimation` | Get heat and altitude acclimation status for a given date. | read | training |
| `get_activities` | Get activities with pagination support. | read | minimal, activities |
| `get_activities_by_date` | Get activities between specified dates with pagination support. | read | minimal, activities |
| `get_activities_fordate` | Get activities for a specific date. | read | activities |
| `get_activity` | Get detailed information for a single activity. | read | minimal, activities |
| `get_activity_exercise_sets` | Get exercise sets for strength training activities. | read | activities |
| `get_activity_fit_data` | Download and parse FIT file for an activity to expose advanced cycling data. | read | activities |
| `get_activity_fit_messages` | Retrieve and generically parse an activity's original FIT file. | read | activities |
| `get_activity_gear` | Get gear data used for an activity. | read | activities |
| `get_activity_hr_in_timezones` | Get heart rate data in different time zones for an activity. | read | activities |
| `get_activity_power_in_timezones` | Get power distribution across training zones for an activity. | read | activities |
| `get_activity_split_summaries` | Get split summaries for an activity. | read | activities |
| `get_activity_splits` | Get splits for an activity. | read | minimal, activities |
| `get_activity_typed_splits` | Get typed splits for an activity. | read | activities |
| `get_activity_types` | Get all available activity types. | read | activities |
| `get_activity_weather` | Get weather data for an activity. | read | activities |
| `get_adhoc_challenges` | Get user-created social/group challenges (e.g., step competitions with friends). | read | training |
| `get_all_day_events` | Get daily wellness events data. | read | health |
| `get_all_day_stress` | Get all-day stress data. | read | health |
| `get_available_badge_challenges` | Get official Garmin badge challenges available to join. | read | training |
| `get_badge_challenges` | Get badge challenges the user has completed. | read | training |
| `get_blood_pressure` | Get blood pressure data. | read | health |
| `get_body_battery` | Get body battery data with events. | read | minimal, health |
| `get_body_battery_events` | Get body battery events data. | read | health |
| `get_body_composition` | Get body composition data for a single date or date range. | read | health |
| `get_calendar_events` | Get races and events on the Garmin Connect calendar between two dates. | read | workouts |
| `get_course_details` | Get full details of a Garmin Connect course by ID. | read | activities |
| `get_courses` | List all courses saved on Garmin Connect. | read | activities |
| `get_custom_food_serving_units` | Get available serving units for custom foods. | read | nutrition |
| `get_custom_foods` | Search or list user's custom foods. | read | nutrition |
| `get_cycling_ftp` | Get the latest cycling Functional Threshold Power (FTP) data. | read | training |
| `get_daily_steps` | Get steps data for a date range. | read | minimal, health |
| `get_daily_weigh_ins` | Get weight measurements for a specific date. | read | health |
| `get_device_alarms` | Get alarms from all Garmin devices. | read | – |
| `get_device_last_used` | Get information about the last used Garmin device. | read | – |
| `get_device_settings` | Get settings for a specific Garmin device. | read | – |
| `get_device_solar_data` | Get solar data for a specific device. | read | – |
| `get_devices` | Get all Garmin devices associated with the user account. | read | – |
| `get_earned_badges` | Get earned badges for user. | read | training |
| `get_endurance_score` | Get endurance score data between dates. | read | training |
| `get_energy_balance` | Estimate daily energy expenditure from logged food, Garmin's calorie estimate and body composition changes over a date range. | read | health, nutrition |
| `get_fitnessage_data` | Get fitness age data. | read | health, training |
| `get_floors` | Get floors climbed data. | read | health |
| `get_full_name` | Get user's full name from profile. | read | minimal, health, activities, workouts, training, nutrition |
| `get_garmin_coach_workouts` | Get Garmin Coach workouts around the given date. | read | workouts |
| `get_gear` | Get all gear registered with the user account. | read | activities |
| `get_goals` | Get Garmin Connect goals (active, future, or past). | read | training |
| `get_heart_rate_zones` | Get the user's saved heart-rate training-zone configuration. | read | minimal, health, activities, workouts, training, nutrition |
| `get_heart_rates` | Get full heart rate time-series data. | read | health |
| `get_heart_rates_summary` | Get heart rate summary with essential metrics (lightweight version). | read | minimal, health |
| `get_hill_score` | Get hill score data between dates. | read | training |
| `get_hrv_data` | Get Heart Rate Variability (HRV) data. | read | minimal, health, training |
| `get_hrv_trend` | Get HRV (Heart Rate Variability) trend over a date range. | read | health, training |
| `get_hydration_data` | Get hydration data. | read | health, nutrition |
| `get_inprogress_virtual_challenges` | Get in-progress virtual challenges/expeditions. | read | training |
| `get_lactate_threshold` | Get lactate threshold data. | read | training |
| `get_lifestyle_logging_data` | Get lifestyle logging data for a specific date. | read | health |
| `get_menstrual_calendar_data` | Get menstrual calendar data between specified dates. | read | health |
| `get_menstrual_data_for_date` | Get menstrual data for a specific date. | read | health |
| `get_morning_training_readiness` | Get morning training readiness score. | read | health, training |
| `get_non_completed_badge_challenges` | Get badge challenges currently in progress (not yet completed). | read | training |
| `get_nutrition_daily_food_log` | Get daily food consumption records for a date. | read | nutrition |
| `get_nutrition_daily_meals` | Get daily meal summaries for a date. | read | nutrition |
| `get_nutrition_daily_settings` | Get nutrition plan/settings for a date. | read | nutrition |
| `get_nutrition_summary_between_dates` | Get per-day nutrition totals for every day in a date range. | read | nutrition |
| `get_personal_record` | Get personal records for user. | read | training |
| `get_power_duration_curve` | Get season-best Power Duration Curve across recent activities. | read | activities, training |
| `get_pregnancy_summary` | Get pregnancy summary data. | read | health |
| `get_primary_training_device` | Get information about the primary training device. | read | training |
| `get_progress_summary_between_dates` | Get progress summary for a metric between dates. | read | training |
| `get_race_predictions` | Get predicted race times based on current fitness level. | read | training |
| `get_recovery_time_remaining` | Get remaining recovery time in hours for a day. | read | health, training |
| `get_respiration_data` | Get full respiration time-series data. | read | health |
| `get_respiration_summary` | Get respiration summary with essential metrics (lightweight version). | read | health |
| `get_respiration_trend` | Get overnight respiration rate trend over a date range. | read | health, training |
| `get_rhr_day` | Get resting heart rate data. | read | health |
| `get_running_tolerance` | Get Running Tolerance for a single day. | read | training |
| `get_running_tolerance_trend` | Get Running Tolerance trend over a date range. | read | training |
| `get_scheduled_workouts` | Get scheduled workouts between two dates with curated summary list. | read | workouts |
| `get_sleep_data` | Get full sleep data with all details. | read | minimal, health |
| `get_sleep_summary` | Get sleep summary with only essential metrics (lightweight version). | read | minimal, health |
| `get_sleep_summary_range` | Get lightweight sleep summaries for every night in a date range. | read | health |
| `get_spo2_data` | Get SpO2 (blood oxygen) data. | read | health |
| `get_stats` | Get daily activity stats with curated essential metrics. | read | minimal, health |
| `get_stats_and_body` | Get stats and body composition data. | read | health |
| `get_stats_range` | Get lightweight per-day calorie and step totals for a date range. | read | health |
| `get_steps_data` | Get detailed steps data with 15-minute intervals. | read | health |
| `get_stress_data` | Get full stress time-series data. | read | health |
| `get_stress_summary` | Get stress summary with essential metrics (lightweight version). | read | minimal, health |
| `get_training_effect` | Get training effect data for a specific activity. | read | training |
| `get_training_load_balance` | Get Garmin's Load Focus: how the training load of the last month is split across aerobic low, aerobic high and anaerobic, with Garmin's feedback. | read | training |
| `get_training_load_trend` | Get Garmin's daily acute and chronic training load over a date range. | read | training |
| `get_training_plan_workouts` | Compatibility alias for get_garmin_coach_workouts. | read | workouts |
| `get_training_readiness` | Get training readiness data with curated metrics. | read | minimal, health, training |
| `get_training_status` | Get training status with curated metrics. | read | minimal, training |
| `get_unit_system` | Get user's preferred unit system from profile. | read | minimal, health, activities, workouts, training, nutrition |
| `get_user_profile` | Get user profile information. | read | minimal, health, activities, workouts, training, nutrition |
| `get_user_summary` | Get user summary data (compatible with garminconnect-ha). | read | minimal, health |
| `get_userprofile_settings` | Get user profile settings. | read | minimal, health, activities, workouts, training, nutrition |
| `get_vo2max_trend` | Get VO2 max trend over a date range. | read | training |
| `get_weekly_intensity_minutes` | Get weekly intensity minutes data aggregates. | read | health, training |
| `get_weekly_steps` | Get weekly step data aggregates. | read | health |
| `get_weekly_stress` | Get weekly stress data aggregates. | read | health |
| `get_weigh_ins` | Get weight measurements between specified dates. | read | health |
| `get_workout_by_id` | Get detailed information for a specific workout. | read | workouts |
| `get_workouts` | Get all workouts with curated summary list. | read | workouts |
| `log_custom_food` | Log a food item to a meal on a date. | create | nutrition |
| `log_food` | Quick-add a food entry with macro values to the nutrition log. | create | nutrition |
| `push_workout_to_device` | Send a workout from the workout library to a Garmin device. | create | workouts |
| `remove_gear_from_activity` | Remove gear association from an activity. | change/delete | activities |
| `request_reload` | Request reload of epoch data. | create | training |
| `reschedule_workout` | Move a scheduled workout to another date on the Garmin Connect calendar. | change/delete | workouts |
| `schedule_week` | Schedule a list of workouts for the week in a single call. | create | workouts |
| `schedule_workout` | Schedule a workout to a specific calendar date. | create | workouts |
| `schedule_workouts` | Schedule multiple workouts to specific calendar dates. | create | workouts |
| `search_foods` | Search Garmin's general food catalog (FatSecret + Garmin custom foods). | read | nutrition |
| `set_activity_description` | Set or update the free-text description (notes) of an activity. | change/delete | activities |
| `set_activity_event_type` | Set the event type of an activity. | change/delete | activities |
| `set_activity_exercise_sets` | Replace the exercise sets on a strength (or other rep-counting) activity. | change/delete | activities |
| `set_activity_feel` | Set how an activity felt ('How did you feel?'). | change/delete | activities |
| `set_activity_name` | Set or update the name of an activity. | change/delete | activities |
| `set_activity_type` | Change the activity type (sport) of an activity. | change/delete | activities |
| `set_blood_pressure` | Set blood pressure values. | create | health |
| `set_fit_download_dir` | Set and persist the default directory for downloaded activity files. | create | activities |
| `set_heart_rate_zones` | Set an account-level heart-rate training-zone configuration for one sport. | change/delete | – |
| `set_nutrition_daily_settings` | Update daily nutrition goals (calorie target and macronutrient targets). | change/delete | nutrition |
| `set_perceived_effort` | Set the perceived effort (RPE) for an activity. | change/delete | activities |
| `unschedule_workout` | Remove a scheduled workout from the Garmin Connect calendar. | change/delete | workouts |
| `unschedule_workouts` | Remove multiple scheduled workouts from the Garmin Connect calendar. | change/delete | workouts |
| `update_custom_food` | Update an existing custom food in the user's Garmin nutrition library. | change/delete | nutrition |
| `upload_course` | Upload a GPX file as a Garmin Connect Course. | create | activities |
| `upload_workout` | Upload a workout from JSON data. | create | workouts |
| `upload_workouts` | Upload multiple workouts from JSON data in a single call. | create | workouts |
| `upsert_and_log` | Find-or-create a custom food then log it in one step. | create | nutrition |
<!-- tools:en:end -->

## Deutsch

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

### So funktioniert es

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

### Einrichtung

Benötigt Home Assistant **2026.2** oder neuer (OS oder Supervised). Bis Version 1.0 ist
die App als *experimentell* gekennzeichnet.

#### 1. Installieren und starten

*Einstellungen → Apps → App installieren → ⋮ → Repositories*, dort
`https://github.com/mw-hbg/ha-garmin-mcp` eintragen (früher `mw-hbg/ha-apps` – eine alte
Adresse einfach stehen lassen, sie wird weitergeleitet). Dann **Garmin Connect MCP** installieren,
starten und in der Seitenleiste **Garmin MCP** öffnen (oder **Weboberfläche öffnen**
auf der App-Seite).

#### 2. Bei Garmin Connect anmelden

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

#### 3. Home Assistant einmal neu starten

Beim ersten Start kopiert die App ihre Hilfs-Integration in Home Assistant. Die App-Seite
zeigt dann **„Home Assistant muss einmal neu gestartet werden“**: neu starten über
*Einstellungen → System → Neu starten*. Home Assistant selbst zeigt für diesen ersten
Neustart **keine Benachrichtigung** – die App hat keinen Zugriff auf die API, und die
Hilfs-Integration läuft erst nach dem Neustart. Nach dem Neustart richtet Home Assistant die
Integration selbst ein (die App meldet ihre Einstellungen über die offizielle
App-Erkennung von Home Assistant), und der Status steht auf **Aktiv** – sonst ist nichts
einzurichten. Bringt ein späteres App-Update eine neue Version der Hilfs-Integration mit,
zeigt Home Assistant einen **Reparatur-Hinweis** (*Einstellungen → Reparaturen*) mit Knopf
zum Neustarten – wie bei HACS.

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

#### 4. KI-Assistenten verbinden

Die **Connector-URL** von der App-Seite kopieren. Sie sieht so aus:
`https://home.example.com/api/webhook/garmin_mcp_<geheim>` (bzw.
`https://garmin.example.com/<geheim>/mcp` bei `direct`).

* **Claude** (claude.ai, Desktop, Mobil): *Einstellungen → Konnektoren → Benutzerdefinierten
  Konnektor hinzufügen*, URL einfügen, keine Authentifizierung. Ein eigener Konnektor ist
  auch im kostenlosen Plan enthalten.
* **Mistral Vibe** (früher Le Chat, chat.mistral.ai – ebenfalls kostenlos): *Intelligence →
  Connectors → Add Connector → Custom MCP Connector*, beliebiger Name ohne Leerzeichen (z. B.
  `GarminConnect`), URL einfügen, keine Authentifizierung. Danach den Connector im Chat
  einschalten.
* **ChatGPT** (ab Plus): Entwicklermodus einschalten, dann die URL als benutzerdefinierten
  Connector / Remote-MCP-Server hinzufügen.
* **Andere Programme** (Cursor, VS Code, Gemini CLI, Open WebUI …): einen Remote-MCP-Server
  mit dem Transport *Streamable HTTP* und der URL anlegen.

> **Nutzt du zusätzlich ha-mcp?** Läuft die [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)-App
> mit ihrem Webhook-Proxy (OAuth) auf demselben Home Assistant, fragt deine KI-App beim
> Hinzufügen dieses Connectors eventuell nach einer Anmeldung bei deinem Home Assistant
> und einer Zugriffsfreigabe. Das kommt von der Anmeldung von ha-mcp für deine Domain und
> ist unbedenklich – einfach bestätigen. Diese App selbst braucht keine Anmeldung.

### Sicherheit

* **Behandle die Connector-URL wie ein Passwort.** Wer sie kennt, kann dein Garmin-Konto
  über die freigegebenen Tools nutzen. Keine Screenshots oder Protokolle teilen, in denen
  sie steht. Ist sie bekannt geworden: **Neue geheime URL erzeugen** auf der App-Seite.
* **Die App hat keinen Zugriff auf die Home-Assistant-API** – sie kann in Home Assistant
  nichts lesen, schalten oder ändern. Ihr einziger Zugriff ist der Konfigurationsordner,
  und zwar nur für eine Sache: die Hilfs-Integration nach
  `custom_components/garmin_mcp_webhook` kopieren (und im Modus `direct` wieder
  entfernen). Einzelne Ordner kann Home Assistant nicht freigeben, deshalb ist der ganze
  Ordner eingebunden; benutzt wird er nur vom internen Teil der App, der von außen nicht
  erreichbar ist.
* **Einstellungen laufen über die offizielle App-Erkennung** des Supervisors: Die App
  meldet Webhook-ID und interne Adresse, Home Assistant richtet die Integration damit
  ein. Umgekehrt meldet sich die Integration jede Minute bei der App (nur im internen
  Netz, geschützt durch den geheimen Pfad und einen Schlüssel): mit deiner externen
  Adresse und Sprache für die App-Seite, und sie fragt den Garmin-Anmeldestatus ab, um
  einen Reparatur-Hinweis anzuzeigen. Nichts in diesem Austausch kann Home Assistant
  verändern.
* **Aus dem Internet** ist nur der MCP-Endpunkt erreichbar (über den Webhook oder deinen
  eigenen Hostnamen). Er führt nur Garmin-Tools aus – von dort gibt es keinen Weg zu Home
  Assistant oder zur App-Seite.
* **AppArmor-Profil für die ganze App:** Der Linux-Kernel beschränkt jeden Prozess der
  App – auch ihren internen Teil – auf das Nötige. Im Home-Assistant-Konfigurationsordner
  darf sie nur `custom_components/garmin_mcp_webhook` anfassen; `secrets.yaml` lesen oder
  dort sonst etwas ändern, andere Programme als Python und nginx starten oder
  Systemeinstellungen ändern kann sie nicht. Home Assistant bewertet die App mit 8 von 8.
* **Der MCP-Server ist eingesperrt:** Er läuft als eingeschränkter Benutzer und kann
  deshalb weder die Geheimnisse der App lesen noch die Hilfs-Integration ändern; das
  AppArmor-Profil hält ihn vom übrigen Home-Assistant-Konfigurationsordner fern (nicht
  einmal lesend). Wo der Linux-Kernel *Landlock* anbietet, sperrt er sich zusätzlich in
  seine eigenen Ordner (Garmin-Tokens, Downloads) ein. Home Assistant OS bietet Landlock
  derzeit nicht an – im App-Protokoll steht dann *Landlock is not available here*; das ist
  so erwartet. Datei-Tools
  (Strecke hochladen, Aktivität herunterladen) arbeiten nur im Download-Ordner.
* **Schreibrechte bewusst wählen** (siehe unten). `read_only` ist am sichersten;
  `create_only` (Standard) löscht oder überschreibt nie etwas.
* **Zusätzliche Absicherung – IP-Freigabeliste:** Nutzt du nur einen KI-Dienst, kannst du
  den Webhook-Pfad (`/api/webhook/garmin_mcp_*`) oder deinen eigenen Hostnamen auf dessen
  IP-Bereiche beschränken, z. B. mit einer Cloudflare-WAF-Regel. Claude verbindet sich aus
  `160.79.104.0/21` (siehe die von Anthropic veröffentlichten IP-Adressen). Andere
  KI-Dienste nutzen andere Bereiche und würden von so einer Regel ausgesperrt. Nach dem
  Einschalten testen.

### Verbindungstest

Der Knopf **Verbindung testen** auf der App-Seite prüft nacheinander:

1. ob der MCP-Server antwortet (und wie viele Tools er anbietet),
2. ob dein Garmin-Konto mit der gespeicherten Anmeldung erreichbar ist,
3. ob die Connector-URL **aus dem Internet** funktioniert – die App ruft ihre eigene
   öffentliche Adresse genau so auf wie deine KI-App.

Zu jedem fehlgeschlagenen Punkt steht ein Hinweis, was zu tun ist.

### Benachrichtigungen

Die Hilfs-Integration zeigt sie als **Reparatur-Hinweise** (*Einstellungen → Reparaturen*)
in der Sprache von Home Assistant:

* **Neustart nötig** – nach Updates der Hilfs-Integration (mit Knopf zum Neustarten).
  Nach der ersten Installation steht der Hinweis auf der App-Seite.
* **Garmin-Anmeldung nicht mehr gültig** – z. B. wenn die Tokens nach etwa sechs Monaten
  abgelaufen sind oder widerrufen wurden. Vorübergehende Fehler (kein Internet nach einem
  Stromausfall, Garmin gestört) behebt die App selbst durch erneute Versuche; erst wenn
  das nicht klappt, erscheint der Hinweis (abschaltbar mit `login_notification`). Auf der
  App-Seite neu anmelden – der Hinweis verschwindet dann von selbst. Die KI-App bekommt in
  dem Fall eine verständliche Meldung statt eines Fehlers.

### Server ausschalten

Die Hilfs-Integration legt pro Garmin-Konto ein Gerät **Garmin Connect MCP <Name>** mit
dem Schalter **Garmin Connect MCP <Name> Server** an (nur im Modus webhook). Ist er aus,
erreicht keine KI-App mehr die Garmin-Daten dieses Kontos: Home Assistant beantwortet jede Anfrage selbst mit
„ausgeschaltet“ – nichts wird an die App weitergeleitet – und die App stoppt ihren
Garmin-Server. Anmeldung, Einstellungen und Connector-URL bleiben; Schalter wieder an,
und nach wenigen Sekunden funktioniert alles wie vorher. Der Zustand übersteht
Neustarts.

Der Schalter ist eine normale Entität: in Automationen nutzbar (z. B. nachts oder im
Urlaub aus), auf Dashboards oder mit Sprachassistenten. Solange er aus ist, zeigt die
App-Seite *In Home Assistant ausgeschaltet*. Ein ausgeschaltetes Konto braucht keinen
Arbeitsspeicher für seinen Garmin-Server.

### Mehrere Garmin-Konten

Eine App kann bis zu **10 Garmin-Konten** bedienen – z. B. jede Person im Haushalt mit
ihrer eigenen KI-App. **Garmin-Konto hinzufügen** auf der App-Seite legt eine neue Karte
an; dort anmelden. Jedes Konto hat:

* eine eigene Garmin-Anmeldung (inkl. Zwei-Faktor-Code) und eine **eigene Connector-URL** –
  jede Person trägt nur ihre eigene URL in ihre KI-App ein,
* einen eigenen Verbindungstest, **Neue geheime URL erzeugen**, Abmelden und
  **Konto entfernen**,
* ein eigenes Gerät mit Schalter in Home Assistant und einen eigenen Reparatur-Hinweis
  („Garmin-Anmeldung von <Name> nicht mehr gültig“),
* einen eigenen Garmin-Server, der als eigener eingeschränkter Benutzer läuft: Kein Konto
  kann die Tokens eines anderen lesen.

**Name:** standardmäßig der Name aus dem Garmin-Profil; ✏️ daneben setzt einen eigenen
Namen. Er erscheint auf der Seite und in Home Assistant (Gerät, Schalter);
Entitäts-IDs bleiben gleich.

**Rechte:** Mit **Gleiche Einstellungen für alle Konten** (Standard) gelten Schreibrechte
und Tool-Auswahl aus der Konfiguration für jedes Konto. Ohne Haken stellst du
Schreibrechte, Bereiche und Tools pro Konto ein (*Rechte dieses Kontos* in jeder Karte).

**Last:** Jedes laufende Konto braucht etwa 70–80 MB Arbeitsspeicher. Ab dem 4. Konto
zeigt die Seite einen Hinweis – auf einem Raspberry Pi 5 kein Problem, auf Geräten mit
1–2 GB eventuell zu viel.

**Wer was sieht:** Die App-Seite steht in Home Assistant nur **Administratoren** offen, und
jeder Administrator sieht und verwaltet **alle** Konten – auch ihre Connector-URLs. Nimm
nur Konten von Personen auf, die den Administratoren vertrauen.

**Update von einer früheren Version:** Deine bestehende Anmeldung wird das erste Konto –
gleiche Connector-URL, gleicher Schalter (`switch.garmin_connect_mcp_server`), nichts neu
einzurichten. Home Assistant bittet einmal um einen Neustart (neue Hilfs-Integration).

### Sprache

Die App-Seite erscheint in der Sprache deines Browsers, sonst in der Sprache von Home
Assistant, sonst auf Englisch. Unten auf der Seite kannst du die Sprache umstellen; die
Wahl merkt sich dein Browser. Derzeit gibt es Deutsch und Englisch – eine weitere Sprache
hinzuzufügen ist einfach, siehe
[TRANSLATING.md](https://github.com/mw-hbg/ha-garmin-mcp/blob/main/garmin_mcp/TRANSLATING.md).

### Tools auswählen

Die App-Seite zeigt pro Kategorie, was die KI darf (für alle Konten oder pro Konto, wenn
sie ihre Einstellungen nicht teilen). **Tools auswählen** öffnet eine Liste
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

### Konfiguration

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
| `login_notification` | `true` (Standard): Reparatur-Hinweis in Home Assistant, wenn die Garmin-Anmeldung nicht mehr funktioniert und die App das durch erneute Versuche nicht beheben konnte. |
| `log_level` | `debug`, `info` (Standard), `warning`, `error`. Nur `debug` protokolliert zusätzlich jede einzelne MCP-Anfrage. |

`tool_areas`, `write_access`, `enable_tools` und `disable_tools` werden ignoriert, sobald
du auf der App-Seite unter **Tools auswählen** eine eigene Auswahl speicherst (die Seite
zeigt dann „eigene Auswahl“). **Auf Konfiguration zurücksetzen** schaltet zurück.

> Geräte-Tools (Uhreinstellungen, Wecker, Solar) und `set_heart_rate_zones` gibt es nur bei
> `all`. Bei einzelnen Bereichen bei Bedarf über `enable_tools` ergänzen.
> Bei `workouts` nimmt die App automatisch `push_workout_to_device` und
> `reschedule_workout` dazu (die Schreibrechte gelten trotzdem).

#### Beispiel: Trainingscoach ohne Löschrechte

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

### Fehlerbehebung

| Problem | Lösung |
|---|---|
| Status *Garmin-Anmeldung fehlgeschlagen* | Tokens abgelaufen oder widerrufen (z. B. Garmin-Passwort geändert). Auf der App-Seite **Neu anmelden** – Einstellungen und Connector-URL bleiben gleich. |
| *Zu viele Anfragen* bei der Anmeldung | Garmin begrenzt Anmeldungen. Ein paar Minuten warten. |
| Workouts schreiben schlägt mit HTTP 412 fehl | Zustimmung zum Upload fehlt: Garmin Connect → Einstellungen → Datenschutzeinstellungen → Daten → *Gerätedaten hochladen*. |
| Bei der Anmeldung wird ein Code verlangt | Zwei-Faktor-Anmeldung ist aktiv – den Code eingeben, den Garmin geschickt hat. |
| KI-App will beim Hinzufügen eine Anmeldung bei Home Assistant | Kommt von ha-mcp (falls installiert), siehe Schritt 4. Bestätigen. |
| Status bleibt *Home Assistant muss einmal neu gestartet werden* | Home Assistant neu starten (*Einstellungen → System → Neu starten*). Bleibt er danach, unter *Einstellungen → System → Protokolle* nach `garmin_mcp_webhook` schauen. |
| Connector meldet *Server nicht erreichbar* | Prüfen, ob Home Assistant von außen erreichbar ist, ob die URL das aktuelle Geheimnis enthält und ob Firewall-/WAF-Regeln greifen. |
| Die KI sagt, das Tool gibt es nicht | Es ist durch `tool_areas`, `write_access` oder `disable_tools` abgeschaltet. |

### Deinstallieren

Einfach die App deinstallieren. Der Supervisor zieht dann die Meldung der App zurück, und
Home Assistant entfernt den Eintrag der Integration unter *Geräte & Dienste* selbst – der
Webhook ist sofort weg. Danach löscht die Hilfs-Integration ihren Ordner
`custom_components/garmin_mcp_webhook` und zeigt eine Benachrichtigung. Ein Neustart ist
nicht nötig.

War Home Assistant beim Deinstallieren aus, merkt die Hilfs-Integration das nach dem
nächsten Start: Alle 10 Minuten fragt sie den Supervisor, ob die App noch installiert ist,
und entfernt sich, sobald die App zweimal hintereinander fehlt. Solange die App nur
gestoppt ist oder der Supervisor nicht antwortet, wird nichts entfernt.

Von Hand entfernen geht auch: *Einstellungen → Geräte & Dienste → Garmin Connect MCP
(remote access) → Löschen*, dann den Ordner `custom_components/garmin_mcp_webhook` aus dem
Konfigurationsordner löschen und Home Assistant neu starten.

### Dank und Lizenzen

Der MCP-Server ist [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT) und
nutzt [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT). Der
Webhook-Ansatz folgt dem Webhook-Proxy von
[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) (MIT). Siehe `THIRD_PARTY_NOTICES.md`
im Repository.

### Alle Tools

*Art*: **lesen** = liest nur Daten · **anlegen** = fügt etwas Neues hinzu ·
**ändern/löschen** = ändert, überschreibt oder entfernt vorhandene Daten (nur mit
`write_access: full`). *Bereiche* nennt die `tool_areas`, die das Tool enthalten;
`–` heißt nur bei `all`. Die Tabelle wird aus dem Code erzeugt (`scripts/update_docs.py`).

<!-- tools:de:start -->
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
<!-- tools:de:end -->
