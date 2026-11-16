# Garmin Connect MCP

[🇩🇪 Deutsche Anleitung](https://github.com/mw-hbg/ha-apps/blob/main/garmin_mcp/DOCS.de.md)

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

## How it works

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

## Setup

Requires Home Assistant **2026.2** or newer (OS or Supervised). The app is
marked *experimental* until version 1.0.

### 1. Install and start

*Settings → Apps → Install app → ⋮ → Repositories*, add
`https://github.com/mw-hbg/ha-apps`. Then install **Garmin Connect MCP**, start it and
open **Garmin MCP** in the sidebar (or **Open Web UI** on the app page).

### 2. Log in to Garmin Connect

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

### 3. Restart Home Assistant once

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

### 4. Connect your AI assistant

Copy the **Connector URL** from the app page. It looks like
`https://home.example.com/api/webhook/garmin_mcp_<secret>` (or
`https://garmin.example.com/<secret>/mcp` in direct mode).

* **Claude** (claude.ai, desktop, mobile): *Settings → Connectors → Add custom
  connector*, paste the URL, no authentication.
* **ChatGPT**: add it as a custom connector / remote MCP server (developer mode).
* **Other clients** (Cursor, VS Code, Gemini CLI, Open WebUI, …): add a remote
  MCP server using the *Streamable HTTP* transport and the URL.

> **Using ha-mcp as well?** If the [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)
> app with its webhook proxy (OAuth) runs on the same Home Assistant, your
> AI app may ask you to log in to your Home Assistant and grant access when
> you add this connector. That prompt comes from ha-mcp's sign-in for your
> domain and is harmless – confirm it. This app itself needs no sign-in.

## Security

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
* **The MCP server is locked in:** it runs as an unprivileged user and additionally
  restricts itself with the Linux kernel's *Landlock*: it can reach only its own
  folders (Garmin tokens, downloads) – not the Home Assistant configuration folder
  (not even to read), not the app's secrets and not the app page. File tools
  (upload a course, download an activity) only work inside the download folder.
* **Choose the write access level deliberately** (see below). `read_only` is the
  safest; `create_only` (default) never deletes or overwrites anything.
* **Optional extra layer – IP allow list:** if you only use one AI service, you
  can restrict the webhook path (`/api/webhook/garmin_mcp_*`) or your own
  hostname to that service's IP ranges, e.g. with a Cloudflare WAF rule. Claude connects from `160.79.104.0/21` (see Anthropic's
  published IP addresses). Other AI services use other ranges and would be
  blocked by such a rule. Test after enabling it.

## Connection test

The **Test connection** button on the app page checks, one after another:

1. the MCP server answers (and how many tools it offers),
2. your Garmin account can be reached with the saved login,
3. the connector URL works **from the internet** – the app calls its own
   public address, exactly the way your AI app does.

Each failed check comes with a hint what to do.

## Notifications

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

## Language

The app page uses your browser language, otherwise the Home Assistant language,
otherwise English. You can switch the language at the bottom of the page; your browser
remembers the choice. English and German are available – adding another language is
easy, see [TRANSLATING.md](https://github.com/mw-hbg/ha-apps/blob/main/garmin_mcp/TRANSLATING.md).

## Choosing tools

The app page shows, per category, what the AI may do. **Choose tools** opens
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

## Configuration

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

### Example: training coach without delete rights

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

## Troubleshooting

| Problem | Solution |
|---|---|
| Status *Garmin login failed* | Tokens expired or were revoked. Log out on the app page and log in again. |
| *Too many requests* during login | Garmin rate-limits logins. Wait a few minutes. |
| Writing workouts fails with HTTP 412 | Upload consent missing: Garmin Connect → Settings → Privacy settings → Data → *Upload device data*. |
| Asked for a code at login | Two-factor authentication is enabled – enter the code Garmin sent you. |
| AI app asks to log in to Home Assistant when adding the connector | Comes from ha-mcp (if installed), see step 4. Confirm it. |
| Status stays *Home Assistant must be restarted once* | Restart Home Assistant (*Settings → System → Restart*). If it stays after the restart, check *Settings → System → Logs* for `garmin_mcp_webhook`. |
| Connector shows *couldn't reach the server* | Check that Home Assistant is reachable from outside, that the URL contains the current secret, and any firewall/WAF rules. |
| The AI says the tool does not exist | It is disabled by `tool_areas`, `write_access` or `disable_tools`. |

## Uninstalling

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

## Credits and licenses

The MCP server is [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)
(MIT), using [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
(MIT). The webhook approach follows the webhook proxy of
[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) (MIT). See `THIRD_PARTY_NOTICES.md` in the repository.

## All tools

*Type*: **read** = only reads data · **create** = adds something new ·
**change/delete** = changes, overwrites or removes existing data (only with
`write_access: full`). *Areas* lists the `tool_areas` that include the tool;
`–` means only `all`. This table is generated from the code
(`scripts/update_docs.py`).

<!-- tools:start -->
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
<!-- tools:end -->
