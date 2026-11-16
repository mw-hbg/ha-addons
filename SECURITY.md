# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's
private reporting instead: **Security → Report a vulnerability** in this
repository. You will get an answer as soon as possible; this is a hobby
project, so please allow a few days.

Helpful details: add-on and Home Assistant version, remote access mode
(`webhook` / `direct`), what an attacker could do and how to reproduce it.

## Scope

In scope: the add-ons in this repository (web UI, secret-path protection,
helper integration, handling of Garmin tokens).

Out of scope: vulnerabilities in the upstream projects
([garmin_mcp](https://github.com/Taxuspt/garmin_mcp),
[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)) –
please report those there – and in Garmin's own services.

## Good to know

* The connector URL is the credential. Anyone who knows it can use the enabled
  tools – treat it like a password and rotate it on the add-on page if it leaks.
* Garmin tokens are stored only in the add-on's private storage (`/data`) and
  are part of Home Assistant backups.
