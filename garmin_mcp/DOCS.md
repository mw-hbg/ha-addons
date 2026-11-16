# Garmin Connect MCP

This add-on runs an [MCP](https://modelcontextprotocol.io) server for your
Garmin Connect account inside Home Assistant. AI assistants that support remote
MCP servers – Claude, ChatGPT and many others – can then read your training and
health data and, if you allow it, create workouts and schedule them on your
watch.

> **Unofficial.** This project is not affiliated with or endorsed by Garmin.
> Garmin offers no public API for individuals, so the add-on uses the same
> private endpoints as the Garmin Connect website (via
> [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)).
> Garmin may change or block this at any time. Use at your own risk.

## How it works

```
AI assistant ──HTTPS──► your Home Assistant address ──► /api/webhook/<secret id> ──► add-on ──► Garmin Connect
                        (Nabu Casa, Cloudflare Tunnel,   (helper integration)
                         reverse proxy …)
```

* By default the add-on is reached through the address you already use to
  access Home Assistant from outside – **no extra hostname, tunnel or port
  forwarding**. A small helper integration (`garmin_mcp_webhook`), installed by
  the add-on, provides a Home Assistant webhook with a long random id and
  forwards requests to the add-on.
* Alternatively (`remote_access: direct`) you route your own HTTPS hostname to
  the add-on's port 8100.
* The MCP server itself listens on loopback only. An nginx in front of it only
  forwards requests that carry a long random **secret path**; everything else
  gets a `404`.
* The add-on page (sidebar → **Garmin MCP**) is only reachable through Home
  Assistant and only for administrators.
* Your Garmin password is never stored. After logging in, only the OAuth tokens
  Garmin issues are kept in the add-on's private storage (valid for about six
  months).

## Setup

### 1. Install and start

Install the add-on, start it and open **Garmin MCP** in the sidebar
(or **Open Web UI** on the add-on page).

### 2. Log in to Garmin Connect

Enter your Garmin e-mail and password. If two-factor authentication is enabled,
Garmin sends you a code – enter it on the next screen.

**Two-factor authentication** is supported. If it is enabled for your Garmin
account, Garmin sends you a code (app, e-mail or SMS) and the add-on asks for
it on the next screen. You only need it at login – not for every request.
After about six months the tokens expire; then simply log in again.

**Data upload consent (EU accounts):** to create workouts and send them to your
watch, Garmin requires your consent to data uploads. In Garmin Connect go to
*Settings → Privacy settings → Data* and make sure **Upload device data** is
switched on (menu names can differ slightly between app versions and
languages). If your watch already syncs activities to Garmin Connect, this is
usually already the case. Without it, writing fails with HTTP 412.

### 3. Restart Home Assistant once

On first start the add-on installs its helper integration. The add-on page
then shows **“Home Assistant must be restarted once”** with a button to do so
(a notification appears as well). After the restart the status changes to
**Active** – nothing else to set up. When a later add-on update brings a new
version of the helper integration, Home Assistant shows a **repair notice**
(*Settings → Repairs*) with a button to restart, just like HACS does.

Requirement: Home Assistant must already be reachable from the internet over
HTTPS (Nabu Casa, Cloudflare Tunnel, reverse proxy, …). The add-on uses the
external URL from *Settings → System → Network* (or your Nabu Casa address).
If it cannot work it out, enter it as **Public base URL** in the add-on
configuration.

<details>
<summary>Alternative: own hostname (<code>remote_access: direct</code>)</summary>

Set `remote_access: direct`, then route a public **HTTPS** hostname to the
target address shown on the add-on page (e.g. with `additional_hosts` in the
Cloudflared add-on):

```yaml
additional_hosts:
  - hostname: garmin.example.com
    service: http://abcd1234-garmin-mcp:8100
```

Enter that hostname as **Public base URL**. Never forward port 8100 on your
router without HTTPS.

Best set `direct` before the first start. If you switch later, the add-on
removes its helper integration from Home Assistant by itself on the next start
(no restart needed). Switching back to `webhook` installs it again and asks for
one restart. The connector URL changes when you switch.
</details>

### 4. Connect your AI assistant

Copy the **Connector URL** from the add-on page. It looks like
`https://home.example.com/api/webhook/garmin_mcp_<secret>` (or
`https://garmin.example.com/<secret>/mcp` in direct mode).

* **Claude** (claude.ai, desktop, mobile): *Settings → Connectors → Add custom
  connector*, paste the URL, no authentication.
* **ChatGPT**: add it as a custom connector / remote MCP server (developer mode).
* **Other clients** (Cursor, VS Code, Gemini CLI, Open WebUI, …): add a remote
  MCP server using the *Streamable HTTP* transport and the URL.

> **Using ha-mcp as well?** If the [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)
> add-on with its webhook proxy (OAuth) runs on the same Home Assistant, your
> AI app may ask you to log in to your Home Assistant and grant access when
> you add this connector. That prompt comes from ha-mcp's sign-in for your
> domain and is harmless – confirm it. This add-on itself needs no sign-in.

## Security

* **Treat the connector URL like a password.** Anyone who knows it can use your
  Garmin account through the enabled tools. Don't share screenshots or logs that
  contain it. If it leaks, click **Generate new secret URL** on the add-on page.
* **What the add-on may access in Home Assistant:** it writes only the helper
  integration (`custom_components/garmin_mcp_webhook`) and its settings file
  (`.garmin_mcp_webhook.json`) into the configuration folder, and uses the
  Home Assistant API only to set up that integration, to show the restart
  notification and – when you click the button – to restart Home Assistant. It
  does not read or change anything else. With `remote_access: direct` it does
  not touch the configuration folder at all.
* **Choose the write access level deliberately** (see below). `read_only` is the
  safest; `create_only` (default) never deletes or overwrites anything.
* **Optional extra layer – IP allow list:** if you only use one AI service, you
  can restrict the webhook path (`/api/webhook/garmin_mcp_*`) or your own
  hostname to that service's IP ranges, e.g. with a Cloudflare WAF rule. Claude connects from `160.79.104.0/21` (see Anthropic's
  published IP addresses). Other AI services use other ranges and would be
  blocked by such a rule. Test after enabling it.

## Choosing tools

The add-on page shows, per category, what the AI may do. **Choose tools** opens
a list of all tools grouped by category, with a search field, presets
(*read only*, *create, never delete*, *everything*, *nothing*), a checkbox per
tool and an **i** button explaining what each tool does and what kind of access
it needs (read / create / change-delete). Saving restarts the server.

A saved selection replaces `tool_areas`, `write_access`, `enable_tools` and
`disable_tools` from the configuration. **Reset to configuration** on that page
brings those options back into effect.

## Configuration

| Option | Description |
|---|---|
| `tool_areas` | Which areas the AI may use: `all` (default), `minimal`, `health`, `activities`, `workouts`, `training`, `nutrition`. Several can be combined. Fewer tools keep the AI faster and more focused. |
| `write_access` | `read_only` – reading only. `create_only` (default) – may also create and schedule workouts, send them to the watch and add entries (weigh-ins, hydration, food logs …), but never delete or overwrite. `full` – also delete and edit (activities, workouts, weigh-ins, courses, …). |
| `enable_tools` | Individual tools to allow although `write_access` or `tool_areas` would exclude them, e.g. `set_perceived_effort` or `push_workout_to_device`. |
| `disable_tools` | Individual tools that are never available, e.g. `delete_activity`. Always wins. |
| `remote_access` | `webhook` (default) – reachable through your existing Home Assistant address, needs one Home Assistant restart. `direct` – you route your own HTTPS hostname to port 8100; switching to it removes the helper integration automatically. |
| `public_url` | Optional. Your public Home Assistant address (webhook mode) or your own hostname (direct mode), only used to display the connector URL. |
| `log_level` | `debug`, `info` (default), `warning`, `error`. |

Changes take effect after restarting the add-on. The add-on page shows how many
tools are active.

> Tip: `push_workout_to_device` and the device tools are only part of `all`.
> If you pick specific areas, add them via `enable_tools` when you need them.

### Example: training coach without delete rights

```yaml
tool_areas:
  - activities
  - training
  - workouts
write_access: create_only
enable_tools:
  - push_workout_to_device
  - set_perceived_effort
disable_tools: []
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Status *Garmin login failed* | Tokens expired or were revoked. Log out on the add-on page and log in again. |
| *Too many requests* during login | Garmin rate-limits logins. Wait a few minutes. |
| Writing workouts fails with HTTP 412 | Upload consent missing: Garmin Connect → Settings → Privacy settings → Data → *Upload device data*. |
| Asked for a code at login | Two-factor authentication is enabled – enter the code Garmin sent you. |
| AI app asks to log in to Home Assistant when adding the connector | Comes from ha-mcp (if installed), see step 4. Confirm it. |
| Status stays *Home Assistant must be restarted once* | Restart Home Assistant (button on the add-on page or *Settings → System → Restart*). |
| Connector shows *couldn't reach the server* | Check that Home Assistant is reachable from outside, that the URL contains the current secret, and any firewall/WAF rules. |
| The AI says the tool does not exist | It is disabled by `tool_areas`, `write_access` or `disable_tools`. |

## Uninstalling

Tip: set **Remote access** to `direct` and restart the add-on once before
uninstalling – it then removes its helper integration by itself.

Otherwise uninstalling the add-on leaves the helper integration in place (it
then just answers `502`). To remove it by hand: *Settings → Devices & services →
Garmin Connect MCP (remote access) → Delete*, then delete the folder
`custom_components/garmin_mcp_webhook` and the file `.garmin_mcp_webhook.json`
from your configuration folder and restart Home Assistant.

## Credits and licenses

The MCP server is [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)
(MIT), using [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
(MIT). The webhook approach follows the webhook proxy of
[ha-mcp](https://github.com/homeassistant-ai/ha-mcp) (MIT). See `THIRD_PARTY_NOTICES.md` in the repository.

## All tools

*Type*: **read** = only reads data · **create** = adds something new ·
**delete / overwrite** = removes or changes existing data (only with
`write_access: full`). *Areas* lists the `tool_areas` that include the tool;
`–` means only `all`.

| Tool | Type | Areas |
|---|---|---|
| `add_body_composition` | create | health |
| `add_gear_to_activity` | create | activities |
| `add_hydration_data` | create | health, nutrition |
| `add_weigh_in` | create | health |
| `add_weigh_in_with_timestamps` | create | health |
| `count_activities` | read | activities |
| `create_custom_food` | create | nutrition |
| `create_manual_activity` | create | activities |
| `create_run_interval_workout` | create | workouts |
| `create_run_workout` | create | workouts |
| `create_strength_workout` | create | workouts |
| `create_walk_run_workout` | create | workouts |
| `create_z2_walk_workout` | create | workouts |
| `delete_activity` | delete / overwrite | activities |
| `delete_course` | delete / overwrite | activities |
| `delete_custom_food` | delete / overwrite | nutrition |
| `delete_food_log` | delete / overwrite | nutrition |
| `delete_weigh_ins` | delete / overwrite | health |
| `delete_workout` | delete / overwrite | workouts |
| `delete_workouts` | delete / overwrite | workouts |
| `download_activity_file` | delete / overwrite | activities |
| `download_course_gpx` | delete / overwrite | activities |
| `download_workout` | delete / overwrite | workouts |
| `get_acclimation` | read | training |
| `get_activities` | read | minimal, activities |
| `get_activities_by_date` | read | minimal, activities |
| `get_activities_fordate` | read | activities |
| `get_activity` | read | minimal, activities |
| `get_activity_exercise_sets` | read | activities |
| `get_activity_fit_data` | read | activities |
| `get_activity_fit_messages` | read | activities |
| `get_activity_gear` | read | activities |
| `get_activity_hr_in_timezones` | read | activities |
| `get_activity_power_in_timezones` | read | activities |
| `get_activity_split_summaries` | read | activities |
| `get_activity_splits` | read | minimal, activities |
| `get_activity_typed_splits` | read | activities |
| `get_activity_types` | read | activities |
| `get_activity_weather` | read | activities |
| `get_adhoc_challenges` | read | training |
| `get_all_day_events` | read | health |
| `get_all_day_stress` | read | health |
| `get_available_badge_challenges` | read | training |
| `get_badge_challenges` | read | training |
| `get_blood_pressure` | read | health |
| `get_body_battery` | read | minimal, health |
| `get_body_battery_events` | read | health |
| `get_body_composition` | read | health |
| `get_calendar_events` | read | workouts |
| `get_course_details` | read | activities |
| `get_courses` | read | activities |
| `get_custom_food_serving_units` | read | nutrition |
| `get_custom_foods` | read | nutrition |
| `get_cycling_ftp` | read | training |
| `get_daily_steps` | read | minimal, health |
| `get_daily_weigh_ins` | read | health |
| `get_device_alarms` | read | – |
| `get_device_last_used` | read | – |
| `get_device_settings` | read | – |
| `get_device_solar_data` | read | – |
| `get_devices` | read | – |
| `get_earned_badges` | read | training |
| `get_endurance_score` | read | training |
| `get_energy_balance` | read | health, nutrition |
| `get_fitnessage_data` | read | health, training |
| `get_floors` | read | health |
| `get_full_name` | read | minimal, health, activities, workouts, training, nutrition |
| `get_garmin_coach_workouts` | read | workouts |
| `get_gear` | read | activities |
| `get_goals` | read | training |
| `get_heart_rate_zones` | read | minimal, health, activities, workouts, training, nutrition |
| `get_heart_rates` | read | health |
| `get_heart_rates_summary` | read | minimal, health |
| `get_hill_score` | read | training |
| `get_hrv_data` | read | minimal, health, training |
| `get_hrv_trend` | read | health, training |
| `get_hydration_data` | read | health, nutrition |
| `get_inprogress_virtual_challenges` | read | training |
| `get_lactate_threshold` | read | training |
| `get_lifestyle_logging_data` | read | health |
| `get_menstrual_calendar_data` | read | health |
| `get_menstrual_data_for_date` | read | health |
| `get_morning_training_readiness` | read | health, training |
| `get_non_completed_badge_challenges` | read | training |
| `get_nutrition_daily_food_log` | read | nutrition |
| `get_nutrition_daily_meals` | read | nutrition |
| `get_nutrition_daily_settings` | read | nutrition |
| `get_nutrition_summary_between_dates` | read | nutrition |
| `get_personal_record` | read | training |
| `get_power_duration_curve` | read | activities, training |
| `get_pregnancy_summary` | read | health |
| `get_primary_training_device` | read | training |
| `get_progress_summary_between_dates` | read | training |
| `get_race_predictions` | read | training |
| `get_recovery_time_remaining` | read | health, training |
| `get_respiration_data` | read | health |
| `get_respiration_summary` | read | health |
| `get_respiration_trend` | read | health, training |
| `get_rhr_day` | read | health |
| `get_running_tolerance` | read | training |
| `get_running_tolerance_trend` | read | training |
| `get_scheduled_workouts` | read | workouts |
| `get_sleep_data` | read | minimal, health |
| `get_sleep_summary` | read | minimal, health |
| `get_sleep_summary_range` | read | health |
| `get_spo2_data` | read | health |
| `get_stats` | read | minimal, health |
| `get_stats_and_body` | read | health |
| `get_stats_range` | read | health |
| `get_steps_data` | read | health |
| `get_stress_data` | read | health |
| `get_stress_summary` | read | minimal, health |
| `get_training_effect` | read | training |
| `get_training_load_balance` | read | training |
| `get_training_load_trend` | read | training |
| `get_training_plan_workouts` | read | workouts |
| `get_training_readiness` | read | minimal, health, training |
| `get_training_status` | read | minimal, training |
| `get_unit_system` | read | minimal, health, activities, workouts, training, nutrition |
| `get_user_profile` | read | minimal, health, activities, workouts, training, nutrition |
| `get_user_summary` | read | minimal, health |
| `get_userprofile_settings` | read | minimal, health, activities, workouts, training, nutrition |
| `get_vo2max_trend` | read | training |
| `get_weekly_intensity_minutes` | read | health, training |
| `get_weekly_steps` | read | health |
| `get_weekly_stress` | read | health |
| `get_weigh_ins` | read | health |
| `get_workout_by_id` | read | workouts |
| `get_workouts` | read | workouts |
| `log_custom_food` | create | nutrition |
| `log_food` | create | nutrition |
| `push_workout_to_device` | create | – |
| `remove_gear_from_activity` | delete / overwrite | activities |
| `request_reload` | create | training |
| `reschedule_workout` | delete / overwrite | – |
| `schedule_week` | create | workouts |
| `schedule_workout` | create | workouts |
| `schedule_workouts` | create | workouts |
| `search_foods` | read | nutrition |
| `set_activity_description` | delete / overwrite | activities |
| `set_activity_event_type` | delete / overwrite | activities |
| `set_activity_exercise_sets` | delete / overwrite | activities |
| `set_activity_feel` | delete / overwrite | activities |
| `set_activity_name` | delete / overwrite | activities |
| `set_activity_type` | delete / overwrite | activities |
| `set_blood_pressure` | create | health |
| `set_fit_download_dir` | create | activities |
| `set_heart_rate_zones` | delete / overwrite | – |
| `set_nutrition_daily_settings` | delete / overwrite | nutrition |
| `set_perceived_effort` | delete / overwrite | activities |
| `unschedule_workout` | delete / overwrite | workouts |
| `unschedule_workouts` | delete / overwrite | workouts |
| `update_custom_food` | delete / overwrite | nutrition |
| `upload_course` | create | activities |
| `upload_workout` | create | workouts |
| `upload_workouts` | create | workouts |
| `upsert_and_log` | create | nutrition |
