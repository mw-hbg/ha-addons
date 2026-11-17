"""Start the upstream garmin-mcp server with app specific adjustments.

* Error hints refer to the app page instead of the `garmin-mcp-auth`
  command line tool, which does not exist for app users. These texts reach
  the AI assistant, which passes them on to the user.
* The server's own log level follows the app option (GARMIN_APP_LOG_LEVEL),
  so per-request lines like "POST /mcp 200" only appear with log_level: debug.
* File paths given to tools are confined to the app's download folder.
  Without this, a tool call could read any file in the container (e.g.
  upload_course(gpx_path=...)) or write into the mapped Home Assistant config
  folder (download_activity_file(output_dir=...)) – including the public
  `www` folder.
"""

import functools
import inspect
import json
import logging
import os

import mcp.server.fastmcp as fastmcp_module

import garmin_mcp
from garminconnect import GarminConnectAuthenticationError

def _original(owner, name):
    """The unpatched attribute – also when this module is loaded twice (tests),
    so a patch never wraps an earlier patch of itself."""
    key = f"_app_original_{name}"
    if not hasattr(owner, key):
        setattr(owner, key, getattr(owner, name))
    return getattr(owner, key)


RELOGIN_HINT = (
    "The Garmin Connect login of the Home Assistant app 'Garmin Connect MCP' is no "
    "longer valid. Ask the user to open the app page in Home Assistant (sidebar: "
    "Garmin MCP) and log in to Garmin Connect again."
)

# 1. Hints attached to Garmin errors during tool calls
messages = dict(garmin_mcp._GarminProxy._MESSAGES)
prefix, _old_hint = messages[GarminConnectAuthenticationError]
messages[GarminConnectAuthenticationError] = (prefix, RELOGIN_HINT)
garmin_mcp._GarminProxy._MESSAGES = messages

# The app shows an invalid login in Home Assistant (repair notice). It learns
# about it through this marker file in the server's home folder: written when
# Garmin rejects the login during a tool call, removed when a call succeeds.
AUTH_FAILED_MARKER = os.path.join(os.environ.get("HOME", "/data/mcp_home"), "auth_failed")


def mark_login(valid: bool) -> None:
    try:
        if valid:
            if os.path.exists(AUTH_FAILED_MARKER):
                os.remove(AUTH_FAILED_MARKER)
        else:
            with open(AUTH_FAILED_MARKER, "w") as fh:
                fh.write("Garmin rejected the login\n")
    except OSError:
        pass  # never break a tool call because of the marker


_original_getattr = _original(garmin_mcp._GarminProxy, "__getattr__")


def _watched_getattr(self, name):
    attr = _original_getattr(self, name)
    if not callable(attr) or isinstance(attr, garmin_mcp._GarminProxy):
        return attr

    @functools.wraps(attr)
    def watched(*args, **kwargs):
        try:
            result = attr(*args, **kwargs)
        except Exception as exc:
            if RELOGIN_HINT in str(exc):
                mark_login(False)
            raise
        mark_login(True)
        return result

    return watched


garmin_mcp._GarminProxy.__getattr__ = _watched_getattr

# 2. Login from saved tokens failed at start-up -> every tool call reports this
_original_init_api = _original(garmin_mcp, "init_api")


def _init_api(*args, **kwargs):
    client = _original_init_api(*args, **kwargs)
    if client is None:
        mark_login(False)
        raise RuntimeError(RELOGIN_HINT)
    return client


garmin_mcp.init_api = _init_api

# 3. Log level of the MCP server (uvicorn access log, request logging)
_level = os.environ.get("GARMIN_APP_LOG_LEVEL", "WARNING").upper()
_original_fastmcp_init = _original(fastmcp_module.FastMCP, "__init__")


def _fastmcp_init(self, *args, **kwargs):
    kwargs.setdefault("log_level", _level)
    _original_fastmcp_init(self, *args, **kwargs)


fastmcp_module.FastMCP.__init__ = _fastmcp_init

# 4. Confine file paths of tools to the download folder
SANDBOX = os.path.realpath(os.environ.get("GARMIN_FIT_DOWNLOAD_DIR", "/data/downloads"))
PATH_PARAMETERS = {"output_dir", "output_path", "gpx_path", "path"}


def path_allowed(value: str) -> bool:
    """True if value points into the sandbox (symlinks and ../ resolved)."""
    if not isinstance(value, str) or not value.strip():
        return False
    resolved = os.path.realpath(os.path.join(SANDBOX, os.path.expanduser(value)))
    return resolved == SANDBOX or resolved.startswith(SANDBOX + os.sep)


def confine_paths(fn):
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn
    guarded_params = [p for p in signature.parameters if p in PATH_PARAMETERS]
    if not guarded_params:
        return fn

    def blocked(args, kwargs) -> str | None:
        bound = signature.bind_partial(*args, **kwargs)
        for name in guarded_params:
            value = bound.arguments.get(name)
            if value is not None and not path_allowed(value):
                return json.dumps(
                    {
                        "error": (
                            f"'{name}' must be inside the app's download folder {SANDBOX}. "
                            "Other locations are blocked for security reasons."
                        )
                    }
                )
        return None

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def guarded(*args, **kwargs):
            if (error := blocked(args, kwargs)) is not None:
                return error
            return await fn(*args, **kwargs)
    else:
        @functools.wraps(fn)
        def guarded(*args, **kwargs):
            if (error := blocked(args, kwargs)) is not None:
                return error
            return fn(*args, **kwargs)

    return guarded


_original_tool = _original(garmin_mcp._ToolFilter, "tool")


def _tool(self, *args, **kwargs):
    register = _original_tool(self, *args, **kwargs)

    def wrapper(fn):
        register(confine_paths(fn))
        return fn

    return wrapper


garmin_mcp._ToolFilter.tool = _tool

def lock_down() -> bool:
    """Landlock: from here on the server reaches only its own folders."""
    import sandbox

    writable = [
        SANDBOX,
        os.environ.get("GARMINTOKENS", "/data/garmin_tokens"),
        os.environ.get("HOME", "/data/mcp_home"),
        "/tmp",
    ]
    try:
        return sandbox.restrict(writable)
    except OSError as exc:  # never leave the server half-configured
        logging.getLogger("garmin_mcp_app").error("Landlock could not be applied: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=_level, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("garmin_mcp_app").setLevel(logging.INFO)  # sandbox status line
    os.makedirs(SANDBOX, exist_ok=True)
    os.chdir(SANDBOX)
    lock_down()
    garmin_mcp.main()
