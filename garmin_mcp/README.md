# Garmin Connect MCP – Home Assistant add-on

[🇩🇪 Deutsche Version](README.de.md)

Let AI assistants such as **Claude** or **ChatGPT** read your Garmin Connect
training and health data – runs, splits, sleep, HRV, Body Battery, training
load – and create structured workouts that sync to your watch.

The add-on runs an [MCP](https://modelcontextprotocol.io) server inside your
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
* **Protected endpoint:** only reachable via a long random secret URL, which you
  can rotate with one click.
* Works with any AI app that supports remote MCP servers (Streamable HTTP).
* Pre-built images for `amd64` and `aarch64` (Raspberry Pi 4/5).

## Installation

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmw-hbg%2Fha-addons)

1. *Settings → Add-ons → Add-on Store → ⋮ → Repositories*, add
   `https://github.com/mw-hbg/ha-addons`.
2. Install **Garmin Connect MCP** and start it.
3. Open **Garmin MCP** in the sidebar, log in to Garmin Connect.
4. Restart Home Assistant once when the add-on page asks for it.
5. Add the connector URL shown on the add-on page to your AI assistant.

Good to know:

* **Two-factor authentication** on your Garmin account is supported – the add-on
  asks for the code during login.
* **Workouts on your watch (EU accounts):** Garmin needs your consent to data
  uploads: Garmin Connect → *Settings → Privacy settings → Data → Upload device
  data* must be on.
* **Using ha-mcp too?** Your AI app may then ask you to log in to Home Assistant
  when adding the connector. That comes from ha-mcp and is harmless.

Full instructions: [DOCS.md](DOCS.md) (also shown in the
add-on's *Documentation* tab).

## Requirements

* Home Assistant OS or Supervised (add-on support)
* A Garmin Connect account
* Home Assistant reachable over HTTPS from the internet (Nabu Casa, Cloudflare
  Tunnel, reverse proxy, …)

## Development

To test changes locally, copy the `garmin_mcp` folder to `/addons/` on your Home
Assistant host, remove the `image:` line from `config.yaml` and install it from
*Local add-ons* – Home Assistant then builds the image itself.

Releases: bump `version` in `garmin_mcp/config.yaml` (only right before releasing), add a `CHANGELOG.md`
entry and publish a GitHub release `vX.Y.Z`. GitHub Actions builds and pushes
the images.

## Credits and license

* MCP server: [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) (MIT)
* Garmin client: [cyberjunky/python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (MIT)

This add-on is released under the [MIT License](../LICENSE). It is provided free of
charge and without warranty. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
for the licenses of bundled software.
