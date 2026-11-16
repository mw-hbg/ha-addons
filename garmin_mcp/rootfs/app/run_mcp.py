"""Start the upstream garmin-mcp server with add-on specific adjustments.

* Error hints refer to the add-on page instead of the `garmin-mcp-auth`
  command line tool, which does not exist for add-on users. These texts reach
  the AI assistant, which passes them on to the user.
* The server's own log level follows the add-on option (GARMIN_ADDON_LOG_LEVEL),
  so per-request lines like "POST /mcp 200" only appear with log_level: debug.
"""

import os

import mcp.server.fastmcp as fastmcp_module

import garmin_mcp
from garminconnect import GarminConnectAuthenticationError

RELOGIN_HINT = (
    "The Garmin Connect login of the Home Assistant add-on 'Garmin Connect MCP' is no "
    "longer valid. Ask the user to open the add-on page in Home Assistant (sidebar: "
    "Garmin MCP) and log in to Garmin Connect again."
)

# 1. Hints attached to Garmin errors during tool calls
messages = dict(garmin_mcp._GarminProxy._MESSAGES)
prefix, _old_hint = messages[GarminConnectAuthenticationError]
messages[GarminConnectAuthenticationError] = (prefix, RELOGIN_HINT)
garmin_mcp._GarminProxy._MESSAGES = messages

# 2. Login from saved tokens failed at start-up -> every tool call reports this
_original_init_api = garmin_mcp.init_api


def _init_api(*args, **kwargs):
    client = _original_init_api(*args, **kwargs)
    if client is None:
        raise RuntimeError(RELOGIN_HINT)
    return client


garmin_mcp.init_api = _init_api

# 3. Log level of the MCP server (uvicorn access log, request logging)
_level = os.environ.get("GARMIN_ADDON_LOG_LEVEL", "WARNING").upper()
_original_fastmcp_init = fastmcp_module.FastMCP.__init__


def _fastmcp_init(self, *args, **kwargs):
    kwargs.setdefault("log_level", _level)
    _original_fastmcp_init(self, *args, **kwargs)


fastmcp_module.FastMCP.__init__ = _fastmcp_init

if __name__ == "__main__":
    garmin_mcp.main()
