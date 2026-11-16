"""Constants for the Garmin Connect MCP remote-access webhook."""

from pathlib import Path

DOMAIN = "garmin_mcp_webhook"
TITLE = "Garmin Connect MCP (remote access)"
# Written by the add-on: {"webhook_id": "...", "target_url": "http://<addon-ip>:8100/<secret>/mcp"}
CONFIG_FILE = Path("/config/.garmin_mcp_webhook.json")
