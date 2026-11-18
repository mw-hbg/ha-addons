# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's
private reporting instead: **Security → Report a vulnerability** in this
repository. You will get an answer as soon as possible; this is a hobby
project, so please allow a few days.

Helpful details: app and Home Assistant version, remote access mode
(`webhook` / `direct`), what an attacker could do and how to reproduce it.

## Scope

In scope: the Garmin Connect MCP app (web UI, secret-path protection,
helper integration, handling of Garmin tokens).

Out of scope: vulnerabilities in the upstream projects
([garmin_mcp](https://github.com/Taxuspt/garmin_mcp),
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)) –
please report those there – and in Garmin's own services.

## Good to know

* The connector URL is the credential. Anyone who knows it can use the enabled
  tools – treat it like a password and rotate it on the app page if it leaks.
* Garmin tokens are stored only in the app's private storage (`/data`) and
  are part of Home Assistant backups.
* The app has no access to the Home Assistant API. Its only access to Home
  Assistant is the configuration folder, used solely to copy (and in direct
  mode remove) the helper integration `custom_components/garmin_mcp_webhook`.
* An AppArmor profile confines the whole app; in the configuration folder it only
  allows `custom_components/garmin_mcp_webhook`.
* Several Garmin accounts: every account has its own secret URL and its own MCP server,
  running as its own unprivileged user – no account can read another account's tokens.
  The servers share the app's container, though: each listens only on the container's own
  loopback address, where the others could reach it – they are not separated on the
  network level. Every Home Assistant administrator can open the app page and therefore sees all
  accounts and their connector URLs (by design).
* The internet-facing MCP server runs as an unprivileged user. Where the Linux kernel
  offers Landlock, it additionally confines itself to its own folders (Garmin tokens,
  downloads, `/tmp`); Home Assistant OS currently does not offer it (the app log says
  so), then the user rights and the AppArmor profile apply.
