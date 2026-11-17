"""Constants for the Garmin Connect MCP remote-access webhook."""

from pathlib import Path

DOMAIN = "garmin_mcp_webhook"
# Must equal "version" in manifest.json (checked by the tests). Raise both
# with every change – the app only replaces the files on a higher version.
VERSION = "0.4.1"
PLATFORMS = ["switch"]
TITLE = "Garmin Connect MCP (remote access)"
# Written by app versions before 0.4; the settings now arrive via discovery.
LEGACY_CONFIG_FILE = Path("/config/.garmin_mcp_webhook.json")

ISSUE_RESTART = "restart_required"
ISSUE_LOGIN = "garmin_login"
