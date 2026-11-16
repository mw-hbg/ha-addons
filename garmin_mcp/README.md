# Garmin Connect MCP – Home Assistant app

[🇩🇪 Deutsche Version](README.de.md)

Let AI assistants such as **Claude** or **ChatGPT** read your Garmin Connect
training and health data – runs, splits, sleep, HRV, Body Battery, training
load – and create structured workouts that sync to your watch.

The app runs an [MCP](https://modelcontextprotocol.io) server inside your
Home Assistant, so your data goes straight from Garmin to your AI assistant
without any third-party service in between.

> **Unofficial.** Not affiliated with or endorsed by Garmin. It uses the same
> private endpoints as the Garmin Connect website, which Garmin may change or
> block at any time. Use at your own risk.

## Features

* **~157 tools** from [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp):
  activities, health, training metrics, workouts, courses, gear, nutrition, …
* **Login in the Home Assistant UI**, including two-factor authentication.
  Your password is never stored.
* **You decide what the AI may do:** read only, create without ever deleting,
  or full access – plus per-tool allow/deny lists.
* **No extra remote setup:** reachable through the address you already use for
  Home Assistant (Nabu Casa, Cloudflare Tunnel, reverse proxy …) via a webhook.
* **Connection test** with one click – server, Garmin login and connector URL
  from the internet.
* **Notifications** when a restart is needed or the Garmin login expired.
* **Protected endpoint:** only reachable via a long random secret URL, which you
  can rotate with one click.
* **English and German** – app page, configuration, notifications and documentation;
  more languages can be added without code ([TRANSLATING.md](TRANSLATING.md)).
* Works with any AI app that supports remote MCP servers (Streamable HTTP).
* Pre-built images for `amd64` and `aarch64` (Raspberry Pi 4/5).

## Installation

1. *Settings → Apps → Install app → ⋮ → Repositories*, add
   `https://github.com/mw-hbg/ha-apps`.
2. Install **Garmin Connect MCP** and start it.
3. Open **Garmin MCP** in the sidebar, log in to Garmin Connect.
4. Restart Home Assistant once when the app page asks for it.
5. Add the connector URL shown on the app page to your AI assistant.

Good to know:

* **Two-factor authentication** on your Garmin account is supported – the app
  asks for the code during login.
* **Workouts on your watch (EU accounts):** Garmin needs your consent to data
  uploads: Garmin Connect → *Settings → Privacy settings → Data → Upload device
  data* must be on.
* **Using ha-mcp too?** Your AI app may then ask you to log in to Home Assistant
  when adding the connector. That comes from ha-mcp and is harmless.

Full instructions: [DOCS.md](DOCS.md) (also shown in the
app's *Documentation* tab).

## Why does the app install an integration?

AI assistants call MCP servers **from the internet**. From outside, usually only
Home Assistant itself is reachable (via Nabu Casa, Cloudflare Tunnel or a
reverse proxy) – not the apps, which run in their own containers. And only
code running *inside* Home Assistant can add an address there.

So on first start the app installs a tiny helper integration
(`custom_components/garmin_mcp_webhook`). It registers a Home Assistant
**webhook** with a long random id (`/api/webhook/garmin_mcp_…`) and passes each
request on, unchanged, to the app inside your network. It stores nothing,
reads nothing else and logs nothing but errors.

* Benefit: no extra hostname, tunnel or port forwarding.
* Cost: one Home Assistant restart after installing (and after updates of the
  helper). The app page and a repair notice tell you when.

## Remote access: webhook or direct

| | `webhook` (default) | `direct` |
|---|---|---|
| Reached via | your existing Home Assistant address | your own hostname, e.g. `garmin.example.com` |
| Helper integration in Home Assistant | yes | no |
| Home Assistant restart | once after installing (and after helper updates) | never |
| You set up | nothing | a hostname in your tunnel / reverse proxy |

Use `direct` only if you don't want an extra integration in Home Assistant,
don't want restarts after updates, your reverse proxy blocks `/api/webhook/`,
or you want to secure Garmin access separately from Home Assistant.

**Setting up `direct`** – best before the first start:

1. Install the app, but don't start it yet.
2. *Configuration* tab: **Remote access** = `direct`, **Public address** =
   your hostname (e.g. `https://garmin.example.com`). Save.
3. Start the app. It installs nothing in Home Assistant.
4. The app page shows a *target for your tunnel / reverse proxy*
   (e.g. `http://abcd1234-garmin-mcp:8100`). Route your hostname there
   (Cloudflared app: `additional_hosts`).
5. Use the connector URL shown on the app page.

**Switching later** is fine too:

* `webhook` → `direct`: on the next start the app removes its helper
  integration from Home Assistant by itself (no restart needed). Then continue
  with steps 4–5.
* `direct` → `webhook`: on the next start the app installs the helper again
  and asks for one Home Assistant restart.

The connector URL changes when you switch – update it in your AI app.

## Requirements

* Home Assistant OS or Supervised, version 2026.2 or newer
* A Garmin Connect account
* Home Assistant reachable over HTTPS from the internet (Nabu Casa, Cloudflare
  Tunnel, reverse proxy, …)

## Development

* **Local testing:** copy the `garmin_mcp` folder into the local apps folder of your
  Home Assistant host (Samba or SSH), remove the `image:` line from `config.yaml` and install it
  from *Local apps* – Home Assistant then builds the image itself.
* **Tests:** `pytest tests` (unit tests for the launcher and the helper
  integration); every push also builds both images and runs a smoke test of
  the container (`tests/smoke_test.sh`).
* **Changes:** add an entry under `## Unreleased` in `CHANGELOG.md`. Never
  change `version` in `config.yaml` by hand.
* **Releases:** *Actions → Release → Run workflow* with the new version. The
  workflow builds and pushes the images first, then sets the version,
  finishes the changelog, tags and publishes the release – so Home Assistant
  only offers an update once its images exist.
* **Garmin server updates:** a weekly check opens an issue when
  [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) has new commits.
  Update `UPSTREAM_REF` in the `Dockerfile` deliberately and let the tests run.

## Credits and license

* MCP server: [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT)
* Garmin client: [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT)

This app is released under the [MIT License](../LICENSE). It is provided free of
charge and without warranty. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
for the licenses of bundled software.
