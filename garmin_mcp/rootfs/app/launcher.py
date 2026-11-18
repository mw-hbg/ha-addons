"""Garmin Connect MCP – Home Assistant app launcher.

Runs three things inside the app container:

* the upstream garmin-mcp server (streamable HTTP, loopback only),
* nginx in front of it, which only forwards requests that carry the secret
  path – everything else gets a 404,
* a small web UI behind Home Assistant ingress to log in to Garmin Connect
  (including MFA), show the connector URL and rotate the secret path.

No Garmin password is ever written to disk; only the OAuth tokens that
garminconnect produces are stored in /data.
"""

from __future__ import annotations

import html
import json
import logging
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from garmin_mcp.tool_annotations import (
    ADDITIVE_TOOLS,
    DESTRUCTIVE_TOOLS,
    READ_ONLY_TOOLS,
)
from garmin_mcp.tool_profiles import resolve_tool_profile

import i18n

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------
DATA = Path(os.environ.get("APP_DATA_DIR", "/data"))
OPTIONS_FILE = DATA / "options.json"
TOKEN_DIR = DATA / "garmin_tokens"
SECRET_FILE = DATA / "secret_path"
ACCOUNT_FILE = DATA / "account.json"
DOWNLOAD_DIR = DATA / "downloads"
MCP_HOME = DATA / "mcp_home"
# Written by the MCP server when Garmin rejects the login during a tool call
# (run_mcp.py); removed on success and on a new login.
AUTH_FAILED_FILE = MCP_HOME / "auth_failed"
# Exists while the MCP server is switched off with the switch of the helper
# integration in Home Assistant (webhook mode only).
SWITCHED_OFF_FILE = DATA / "mcp_switched_off"
# The internet-facing MCP server runs as this unprivileged user (created in the
# Dockerfile). It may only write its tokens, downloads and its home folder –
# never the Home Assistant configuration folder mapped into the container.
MCP_USER = "garmin"
NGINX_CONF = Path("/tmp/garmin-mcp-nginx.conf")

MCP_PORT = 8000          # upstream server, loopback only
PUBLIC_PORT = 8100       # nginx, reached by tunnel / reverse proxy
UI_PORT = 8099           # Home Assistant ingress
INGRESS_PROXY_IP = "172.30.32.2"
ALLOW_ANY_UI_CLIENT = os.environ.get("ALLOW_ANY_UI_CLIENT") == "1"  # tests only

# Remote access through a Home Assistant webhook (default)
HA_CONFIG = Path(os.environ.get("HA_CONFIG_DIR", "/homeassistant"))
COMPONENT_SRC = Path(__file__).resolve().parent / "integration" / "garmin_mcp_webhook"
COMPONENT_DST = HA_CONFIG / "custom_components" / "garmin_mcp_webhook"
# Written by app versions before 0.4 – removed on start.
LEGACY_WEBHOOK_CONFIG = HA_CONFIG / ".garmin_mcp_webhook.json"
DISCOVERY_FILE = DATA / "discovery_uuid"
# Integration reports newer than this count as "Home Assistant is connected".
REPORT_MAX_AGE = 180
WEBHOOK_ID_FILE = DATA / "webhook_id"
WEBHOOK_DOMAIN = "garmin_mcp_webhook"

# Several Garmin accounts. Account "1" keeps the files directly in /data (the
# layout of the versions with a single account – an update changes nothing);
# every further account gets /data/accounts/<id>/ with the same file names.
ACCOUNTS_FILE = DATA / "accounts.json"
ACCOUNTS_DIR = DATA / "accounts"
MAX_ACCOUNTS = 10
LOAD_WARNING_FROM = 4  # from this many accounts on, the page warns about the load
# Key for the integration's status channel and the stand-in server (nginx adds it).
REPORT_SECRET_FILE = DATA / "report_secret"

log = logging.getLogger("garmin_mcp_app")
SELECTION_FILE = DATA / "tool_selection.json"


def _build_catalog() -> list[dict]:
    """Every upstream tool with its category and description (no Garmin login needed)."""
    import inspect
    import importlib

    entries: list[dict] = []

    class _Collector:
        def __init__(self, module: str) -> None:
            self.module = module

        def tool(self, *args, **kwargs):
            def wrap(fn):
                name = kwargs.get("name") or (args[0] if args and isinstance(args[0], str) else fn.__name__)
                doc = (inspect.getdoc(fn) or "").split("\n\n")[0].replace("\n", " ").strip()
                entries.append({"name": name, "module": self.module, "doc": doc})
                return fn
            return wrap

        def __getattr__(self, _name):
            return lambda *a, **k: (lambda fn: fn)

    import pkgutil

    import garmin_mcp as _pkg

    # Every module of the server that registers tools – including modules a
    # future update adds, so no tool can escape the access rules.
    # Skip __main__ (it starts the server) and the auth command line tool.
    modules = [
        m.name for m in pkgutil.iter_modules(_pkg.__path__)
        if not m.name.startswith("_") and m.name not in ("auth_cli",)
    ]
    for module in modules:
        try:
            mod = importlib.import_module(f"garmin_mcp.{module}")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load garmin_mcp.%s: %s", module, exc)
            continue
        if not callable(getattr(mod, "register_tools", None)):
            continue
        try:
            mod.register_tools(_Collector(module if module in i18n.CATEGORY_ORDER else "other"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read tool list of %s: %s", module, exc)
    for entry in entries:
        entry["kind"] = kind_of(entry["name"])
    return entries


def kind_of(name: str) -> str:
    """read / create / change. Tools upstream has not classified count as
    'change' (most restrictive), so a new write tool can never slip through
    read_only or create_only."""
    if name in READ_ONLY_TOOLS:
        return "read"
    if name in ADDITIVE_TOOLS:
        return "create"
    return "change"


# The tools the server actually registers – not only the classified ones.
CATALOG: list[dict] = _build_catalog()
ALL_TOOLS = frozenset(e["name"] for e in CATALOG) | READ_ONLY_TOOLS | ADDITIVE_TOOLS | DESTRUCTIVE_TOOLS
_UNCLASSIFIED = sorted(n for n in ALL_TOOLS if n not in READ_ONLY_TOOLS | ADDITIVE_TOOLS | DESTRUCTIVE_TOOLS)


def load_selection(path: Path | None = None) -> tuple[set[str], set[str]] | None:
    """(picked tools, tools that existed when the user saved) or None if the
    user never saved a selection on the app page."""
    try:
        data = json.loads((path or SELECTION_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return None
    if isinstance(data, list):  # format of 0.2.x
        return {str(n) for n in data} & ALL_TOOLS, set()
    picked = {str(n) for n in data.get("enabled", [])} & ALL_TOOLS
    known = {str(n) for n in data.get("known", [])}
    return picked, known


def save_selection(picked: set[str], path: Path | None = None) -> None:
    write_private(
        path or SELECTION_FILE,
        json.dumps({"enabled": sorted(picked & ALL_TOOLS), "known": sorted(ALL_TOOLS)}),
    )


def new_tools(path: Path | None = None) -> list[str]:
    """Tools added (by an update) since the user saved their selection."""
    sel = load_selection(path)
    if sel is None or not sel[1]:
        return []
    return sorted(ALL_TOOLS - sel[1])
MFA_TIMEOUT = 600  # seconds a started MFA login stays valid


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------
DEFAULT_OPTIONS = {
    "tool_areas": ["all"],
    "write_access": "create_only",
    "enable_tools": [],
    "disable_tools": [],
    "remote_access": "webhook",
    "public_url": "",
    "keep_downloads_days": 7,
    "login_notification": True,
    "log_level": "info",
}


def load_options() -> dict:
    options = dict(DEFAULT_OPTIONS)
    try:
        options.update(json.loads(OPTIONS_FILE.read_text()))
    except FileNotFoundError:
        log.warning("No options.json found, using defaults")
    except json.JSONDecodeError as exc:
        log.error("options.json is invalid (%s), using defaults", exc)
    return options


# Added to the server's tool profiles: planning workouts without being able
# to put them on the watch or move them is of little use.
AREA_EXTRAS = {
    "workouts": {"push_workout_to_device", "reschedule_workout"},
}


def normalize_public_url(value) -> tuple[str, str]:
    """Return (base URL, problem) for the public_url option.

    Accepts "example.com", "https://example.com/" or a copied browser address
    like "https://example.com/lovelace/0" and reduces it to scheme + host.
    problem is "" (fine), "http" (works, but AI apps need HTTPS) or
    "invalid" (ignored).
    """
    raw = str(value or "").strip()
    if not raw:
        return "", ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        port = parts.port  # raises ValueError for a bad port
    except ValueError:
        return "", "invalid"
    if parts.scheme not in ("http", "https") or not host or " " in raw or parts.username:
        return "", "invalid"
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return f"{parts.scheme}://{netloc}", ("http" if parts.scheme == "http" else "")


def unknown_tool_names(options: dict) -> list[str]:
    """Tool names in enable_tools/disable_tools that do not exist (typos)."""
    return sorted((_names(options.get("enable_tools")) | _names(options.get("disable_tools"))) - ALL_TOOLS)


def keep_days(options: dict) -> int:
    try:
        return max(0, min(365, int(options.get("keep_downloads_days", 7))))
    except (TypeError, ValueError):
        return 7


def prune_downloads(days: int, folder: Path | None = None, now: float | None = None) -> int:
    """Delete downloaded files older than `days` (0 = keep everything).

    Downloads are only a hand-over to the AI; keeping them forever would fill
    the disk and every Home Assistant backup."""
    folder = folder or DOWNLOAD_DIR
    if days <= 0 or not folder.is_dir():
        return 0
    limit = (now or time.time()) - days * 86400
    removed = 0
    # os.walk never follows symlinks; a link is removed itself, not its target.
    for root, dirs, files in os.walk(folder, topdown=False, followlinks=False):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            path = Path(root, name)
            try:
                if path.lstat().st_mtime < limit:
                    path.unlink()
                    removed += 1
            except OSError as exc:
                log.debug("Could not remove %s: %s", path, exc)
        if Path(root) != folder:
            try:
                Path(root).rmdir()  # only succeeds when empty
            except OSError:
                pass
    if removed:
        log.info("Removed %d downloaded file(s) older than %d days", removed, days)
    return removed


def _names(values) -> set[str]:
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def tool_selection(options: dict, selection_file: Path | None = None) -> tuple[dict, set[str]]:
    """Return (environment for garmin-mcp, set of tools that will be active)."""
    sel = load_selection(selection_file)
    if sel is not None:
        picked = sel[0]
        return {"GARMIN_DISABLED_TOOLS": ",".join(sorted(ALL_TOOLS - picked))}, picked
    areas = [a.strip().lower() for a in options.get("tool_areas") or ["all"] if a.strip()]
    if not areas or "all" in areas:
        areas = ["all"]
    profile = resolve_tool_profile(",".join(areas))  # None = every tool

    write_access = options.get("write_access", "create_only")
    if write_access == "read_only":
        blocked = {n for n in ALL_TOOLS if kind_of(n) != "read"}
    elif write_access == "full":
        blocked = set()
    else:  # create_only (default)
        blocked = {n for n in ALL_TOOLS if kind_of(n) == "change"}

    enable = _names(options.get("enable_tools"))
    disable = _names(options.get("disable_tools"))
    disabled = (blocked - enable) | disable
    # Tools the server's profiles leave out although the area clearly needs
    # them. They still obey write_access (they are not in `enable`).
    extras = set()
    for area in areas:
        extras |= AREA_EXTRAS.get(area, set())
    extras &= ALL_TOOLS

    env = {"GARMIN_DISABLED_TOOLS": ",".join(sorted(disabled))}
    if profile is not None:
        env["GARMIN_TOOL_PROFILE"] = ",".join(areas)
        if enable | extras:
            # With a profile, upstream's allowlist ADDS tools to the profile.
            env["GARMIN_ENABLED_TOOLS"] = ",".join(sorted(enable | extras))
    # Without a profile every tool registers anyway; an allowlist would turn
    # into "only these tools", so it is intentionally not passed.

    base = set(ALL_TOOLS) if profile is None else set(profile) | ((enable | extras) & ALL_TOOLS)
    active = base - disabled
    unknown = sorted((enable | disable) - ALL_TOOLS)
    if unknown:
        log.warning("Unknown tool name(s) in options, ignored: %s", ", ".join(unknown))
    return env, active


# --------------------------------------------------------------------------
# Secret path, account info
# --------------------------------------------------------------------------
def write_private(path: Path, content: str) -> None:
    """Write a file atomically and readable by its owner only (no window in
    which a secret sits on disk with default permissions)."""
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _read_or_create(path: Path, make, rotate: bool = False) -> str:
    if not rotate and path.exists():
        value = path.read_text().strip()
        if len(value) >= 24:
            return value
    value = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_private(path, value)
    return value


def get_secret(rotate: bool = False, path: Path | None = None) -> str:
    value = _read_or_create(path or SECRET_FILE, lambda: secrets.token_urlsafe(32), rotate)
    if rotate:
        log.info("Generated a new secret path")
    return value


def get_webhook_id(rotate: bool = False, path: Path | None = None) -> str:
    return _read_or_create(path or WEBHOOK_ID_FILE, lambda: "garmin_mcp_" + secrets.token_urlsafe(32), rotate)


def get_report_secret() -> str:
    """Key of the status channel and the stand-in server – its own secret, never
    one of the accounts' secret paths (those end up in AI apps)."""
    return _read_or_create(REPORT_SECRET_FILE, lambda: secrets.token_urlsafe(32))


def has_tokens(token_dir: Path | None = None) -> bool:
    return ((token_dir or TOKEN_DIR) / "garmin_tokens.json").is_file()


def read_account(path: Path | None = None) -> dict:
    try:
        return json.loads((path or ACCOUNT_FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mcp_identity(user: str = MCP_USER) -> tuple[int, int] | None:
    """(uid, gid) of an MCP server user, or None where it does not exist (tests)."""
    import pwd

    try:
        entry = pwd.getpwnam(user)
    except KeyError:
        return None
    return entry.pw_uid, entry.pw_gid


def _allow_passage(folder: Path) -> None:
    """Execute bit only: the MCP user may pass through, but not list the folder."""
    mode = folder.stat().st_mode & 0o777
    if not mode & 0o001:
        os.chmod(folder, mode | 0o001)


def prepare_mcp_dirs(identity: tuple[int, int] | None, account: "Account | None" = None) -> None:
    """Folders the MCP server of an account may write: owned by its user, private.
    Every account has its own user, so no account can read another one's tokens."""
    base = account.base if account is not None else DATA
    folders = account.private_dirs() if account is not None else (TOKEN_DIR, DOWNLOAD_DIR, MCP_HOME)
    if identity is not None:
        _allow_passage(DATA)
        if base != DATA:
            ACCOUNTS_DIR.mkdir(mode=0o711, exist_ok=True)
            _allow_passage(ACCOUNTS_DIR)
            base.mkdir(mode=0o711, exist_ok=True)
            _allow_passage(base)
    for folder in folders:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if identity is None:
            continue
        uid, gid = identity
        for root, dirs, files in os.walk(folder, followlinks=False):
            for name in [*dirs, *files]:
                os.lchown(os.path.join(root, name), uid, gid)
        os.chown(folder, uid, gid)
        os.chmod(folder, 0o700)


def secure_dir(path: Path) -> None:
    os.chmod(path, 0o700)
    for entry in path.iterdir():
        if entry.is_file():
            os.chmod(entry, 0o600)


# --------------------------------------------------------------------------
# Child processes
# --------------------------------------------------------------------------
NGINX_TEMPLATE = """
worker_processes 1;
pid /tmp/garmin-mcp-nginx.pid;
# Only critical errors: nginx error lines contain the request path, i.e. the secret.
error_log stderr crit;
events {{ worker_connections 256; }}
http {{
    access_log off;            # the secret path must never end up in a log
    server_tokens off;
    client_max_body_size 20m;
    client_body_temp_path /tmp/nginx-body;
    proxy_temp_path /tmp/nginx-proxy;
    fastcgi_temp_path /tmp/nginx-fastcgi;
    uwsgi_temp_path /tmp/nginx-uwsgi;
    scgi_temp_path /tmp/nginx-scgi;
    server {{
        listen {public_port} default_server;
{account_locations}{report_location}
        location / {{
            return 404;
        }}
    }}
}}
"""

# One block per Garmin account: its own secret path and its own server.
NGINX_ACCOUNT = """
        location = /{secret}/mcp {{
            include {proxy_conf};
        }}
        location = /{secret}/mcp/ {{
            include {proxy_conf};
        }}
        # Server not running (not logged in, starting, login failed, switched
        # off): a small stand-in in the app answers proper MCP messages that
        # tell the AI why.
        location @unavailable_{account} {{
            # (a named location may not have a path in proxy_pass)
            rewrite ^ /mcp-unavailable/{account} break;
            proxy_pass http://127.0.0.1:{ui_port};
            proxy_set_header X-Report-Key "{report_secret}";
            proxy_set_header Host 127.0.0.1;
            proxy_set_header Origin "";
        }}
"""


NGINX_PROXY = """
proxy_pass http://127.0.0.1:{mcp_port}/mcp;
proxy_http_version 1.1;
# The MCP SDK only accepts loopback Host headers (DNS rebinding protection);
# the request has already passed the secret-path check at this point.
proxy_set_header Host 127.0.0.1:{mcp_port};
proxy_set_header Origin "";
proxy_set_header Connection "";
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
error_page 502 503 504 = @unavailable_{account};
"""


class Account:
    """One Garmin account: its files, its secret URL and its own MCP server."""

    def __init__(self, record: dict, services: "Services") -> None:
        self.services = services
        self.id = str(record["id"])
        self.slot = int(record["slot"])
        self.custom_name = str(record.get("custom_name", ""))[:60]
        self.base = DATA if self.id == "1" else ACCOUNTS_DIR / self.id
        self.token_dir = self.base / "garmin_tokens"
        self.secret_file = self.base / "secret_path"
        self.info_file = self.base / "account.json"
        self.download_dir = self.base / "downloads"
        self.home = self.base / "mcp_home"
        # Written by the MCP server when Garmin rejects the login during a tool
        # call (run_mcp.py); removed on success and on a new login.
        self.auth_failed_file = self.home / "auth_failed"
        # Exists while the account's switch in Home Assistant is off (webhook mode).
        self.switched_off_file = self.base / "mcp_switched_off"
        self.webhook_id_file = self.base / "webhook_id"
        # Write access, areas and tool choice of this account when the accounts
        # do not share their settings.
        self.own_settings_file = self.base / "own_settings.json"
        self.own_selection_file = self.base / "own_tool_selection.json"
        self.port = MCP_PORT + self.slot - 1
        self.user = MCP_USER if self.slot == 1 else f"{MCP_USER}{self.slot}"
        self.proxy_conf = Path(f"/tmp/garmin-mcp-proxy-{self.id}.conf")
        if self.base != DATA:
            # Passable, but not listable, for the accounts' users.
            for folder in (ACCOUNTS_DIR, self.base):
                folder.mkdir(mode=0o711, exist_ok=True)
                os.chmod(folder, 0o711)
        self.secret = get_secret(path=self.secret_file)
        self.webhook_id = get_webhook_id(path=self.webhook_id_file)
        if services.options.get("remote_access", "webhook") != "webhook":
            self.switched_off_file.unlink(missing_ok=True)  # the switch exists only in webhook mode
        self.switched_off = self.switched_off_file.exists()
        self.mcp: subprocess.Popen | None = None
        self.pending_mfa: dict = {}
        self.test_result: dict = {}
        self._mcp_failures = 0
        self._login_failures = 0
        self._next_login_retry = 0.0
        self.reload_settings()

    # names and files -------------------------------------------------------
    def private_dirs(self) -> tuple[Path, Path, Path]:
        return self.token_dir, self.download_dir, self.home

    def garmin_name(self) -> str:
        return str(read_account(self.info_file).get("name") or "")

    def display_name(self) -> str:
        """Own name > name of the Garmin profile > number."""
        return self.custom_name or self.garmin_name() or self.id

    def has_tokens(self) -> bool:
        return has_tokens(self.token_dir)

    def record(self) -> dict:
        return {"id": self.id, "slot": self.slot, "custom_name": self.custom_name}

    # settings --------------------------------------------------------------
    def own_settings(self) -> dict:
        try:
            data = json.loads(self.own_settings_file.read_text())
        except (FileNotFoundError, ValueError):
            data = {}
        result = {
            "write_access": self.services.options.get("write_access", "create_only"),
            "tool_areas": list(self.services.options.get("tool_areas") or ["all"]),
        }
        if data.get("write_access") in ("read_only", "create_only", "full"):
            result["write_access"] = data["write_access"]
        areas = [str(a) for a in data.get("tool_areas", []) if str(a) in TOOL_AREAS]
        if areas:
            result["tool_areas"] = areas
        return result

    def save_own_settings(self, write_access: str, areas: list[str]) -> None:
        if write_access not in ("read_only", "create_only", "full"):
            write_access = "create_only"
        areas = [a for a in areas if a in TOOL_AREAS] or ["all"]
        write_private(self.own_settings_file, json.dumps({"write_access": write_access, "tool_areas": areas}))

    def options(self) -> dict:
        """The app options as they apply to this account."""
        options = dict(self.services.options)
        if not self.services.same_settings:
            options.update(self.own_settings())
        return options

    def selection_file(self) -> Path:
        return SELECTION_FILE if self.services.same_settings else self.own_selection_file

    def reload_settings(self) -> None:
        self.mcp_env, self.active_tools = tool_selection(self.options(), self.selection_file())

    def reload_tools(self) -> None:
        self.reload_settings()
        self.restart_mcp()

    # garmin-mcp ------------------------------------------------------------
    def start_mcp(self) -> None:
        with self.services.lock:
            if self.mcp and self.mcp.poll() is None:
                return
            if self.switched_off:
                log.info("[%s] The MCP server is switched off in Home Assistant", self.display_name())
                return
            if not self.has_tokens():
                log.info("[%s] Not logged in to Garmin Connect yet – open the app page to log in", self.display_name())
                return
            identity = mcp_identity(self.user)
            prepare_mcp_dirs(identity, self)
            env = dict(os.environ)
            env.update(self.mcp_env)
            env.update(
                {
                    "GARMIN_MCP_TRANSPORT": "streamable-http",
                    "GARMIN_MCP_HOST": "127.0.0.1",
                    "GARMIN_MCP_PORT": str(self.port),
                    "GARMIN_MCP_STATELESS_HTTP": "true",
                    "GARMINTOKENS": str(self.token_dir),
                    "GARMINTOKENS_BASE64": str(self.token_dir / "tokens.b64"),
                    "GARMIN_FIT_DOWNLOAD_DIR": str(self.download_dir),
                    "HOME": str(self.home),
                }
            )
            # The MCP server is reachable from the internet and runs tools on
            # behalf of an AI – it must not hold the Supervisor token (which
            # grants access to the Home Assistant API) or any credentials.
            for key in list(env):
                upper = key.upper()
                sensitive = upper in ("GARMIN_EMAIL", "GARMIN_PASSWORD") or (
                    ("TOKEN" in upper or "SECRET" in upper or "PASSWORD" in upper)
                    and upper not in ("GARMINTOKENS", "GARMINTOKENS_BASE64")
                )
                if sensitive:
                    env.pop(key, None)
            level = str(self.services.options.get("log_level", "info")).lower()
            env["GARMIN_APP_LOG_LEVEL"] = "DEBUG" if level == "debug" else "WARNING"
            run_mcp = Path(__file__).resolve().parent / "run_mcp.py"
            drop = {}
            if identity is not None:
                drop = {"user": identity[0], "group": identity[1], "extra_groups": [], "umask": 0o077}
            else:
                log.warning("User %r missing – the MCP server runs with full rights", self.user)
            self.mcp = subprocess.Popen(
                [sys.executable, str(run_mcp)], env=env, cwd=str(self.download_dir), **drop
            )
            log.info(
                "[%s] garmin-mcp started (%d tools active, write access: %s)",
                self.display_name(),
                len(self.active_tools),
                self.options().get("write_access"),
            )

    def stop_mcp(self) -> None:
        with self.services.lock:
            proc, self.mcp = self.mcp, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def set_switched_off(self, off: bool) -> None:
        """The account's switch in Home Assistant: stop or start its server."""
        with self.services.lock:
            if off == self.switched_off:
                return
            self.switched_off = off
            if off:
                self.switched_off_file.touch()
            else:
                self.switched_off_file.unlink(missing_ok=True)
        if off:
            log.info("[%s] MCP server switched off in Home Assistant", self.display_name())
            self.stop_mcp()
        else:
            log.info("[%s] MCP server switched on in Home Assistant", self.display_name())
            self._mcp_failures = 0
            self.start_mcp()

    def restart_mcp(self) -> None:
        self.stop_mcp()
        self._mcp_failures = 0
        self.start_mcp()

    def reset_login_state(self) -> None:
        """After a fresh login: forget earlier failures and alerts."""
        self._login_failures = 0
        self._next_login_retry = 0.0

    def mcp_state(self) -> str:
        """'stopped', 'pending', 'ready' or 'failed'."""
        if not self.mcp or self.mcp.poll() is not None:
            return "stopped"
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/readyz", timeout=2) as resp:
                return json.loads(resp.read()).get("status", "ready")
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read()).get("status", "failed")
            except Exception:  # noqa: BLE001
                return "failed"
        except Exception:  # noqa: BLE001 - not listening yet
            return "pending"

    def check_login(self) -> None:
        """Tell the user in Home Assistant when the Garmin login stops working."""
        if self.switched_off:
            return
        state = self.mcp_state() if self.has_tokens() else "stopped"
        if state == "ready":
            self._login_failures = 0
        if state == "failed" and time.time() >= self._next_login_retry:
            # A failed start is often temporary (no internet yet after a power
            # cut, Garmin briefly down). Retry with growing pauses before
            # bothering the user: 2, 10, 30, then every 60 minutes.
            self._login_failures += 1
            pause = (120, 600, 1800, 3600)[min(self._login_failures - 1, 3)]
            self._next_login_retry = time.time() + pause
            log.warning(
                "[%s] Garmin login failed (attempt %d) – restarting the server, next try in %d min",
                self.display_name(),
                self._login_failures,
                pause // 60,
            )
            self.restart_mcp()

    def shown_state(self) -> str:
        """mcp_state, but 'failed' while Garmin rejects the login of the running
        server and 'off' while it is switched off in Home Assistant."""
        if self.switched_off:
            return "off"
        state = self.mcp_state()
        if state == "ready" and self.auth_failed_file.exists():
            return "failed"
        return state

    def login_status(self) -> str:
        """For the helper integration: 'ok', 'failed' (after retries), 'logged_out',
        'starting' or 'off' (switched off in Home Assistant)."""
        if self.switched_off:
            return "off"
        if not self.has_tokens():
            return "logged_out"
        state = self.mcp_state()
        if state == "ready" and self.auth_failed_file.exists():
            return "failed"  # Garmin rejected the login while the server was running
        if state == "ready":
            return "ok"
        if state == "failed" and self._login_failures >= 2:
            return "failed"
        return "starting"

    def expire_pending_mfa(self) -> None:
        """Drop a half-finished MFA login (it holds the password in memory)."""
        if self.pending_mfa and time.time() - self.pending_mfa.get("started", 0) > MFA_TIMEOUT:
            self.pending_mfa.clear()

    def supervise_tick(self) -> float:
        """Restart a crashed server. Returns the pause before the restart (0 = none)."""
        with self.services.lock:
            if self.mcp and self.mcp.poll() is not None:
                self._mcp_failures += 1
                delay = min(60, 5 * self._mcp_failures)
                log.error("[%s] garmin-mcp exited (%s), restarting in %ss", self.display_name(), self.mcp.returncode, delay)
                self.mcp = None
                return delay
        return 0

    def delete_files(self) -> None:
        """Remove everything of this account (tokens, URL, settings, downloads)."""
        if self.base == DATA:
            for path in (self.token_dir, self.download_dir, self.home):
                shutil.rmtree(path, ignore_errors=True)
            for path in (
                self.secret_file, self.info_file, self.switched_off_file, self.webhook_id_file,
                self.own_settings_file, self.own_selection_file, DATA / "garmin_tokens.b64",
            ):
                path.unlink(missing_ok=True)
        else:
            shutil.rmtree(self.base, ignore_errors=True)


TOOL_AREAS = ("all", "minimal", "health", "activities", "workouts", "training", "nutrition")


class AccountError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class Services:
    """Starts, stops and supervises nginx and one garmin-mcp server per account."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.nginx: subprocess.Popen | None = None
        self.stopping = False
        self.options = load_options()
        self.report_secret = get_report_secret()
        registry = self._load_registry()
        self.same_settings = bool(registry.get("same_settings", True))
        self.next_id = int(registry.get("next_id", 2))
        self.accounts: dict[str, Account] = {}
        for record in registry.get("accounts", []):
            try:
                account = Account(record, self)
            except (KeyError, ValueError, TypeError) as exc:
                log.error("Ignoring a broken account entry: %s", exc)
                continue
            self.accounts[account.id] = account

    # accounts ------------------------------------------------------------------
    def _load_registry(self) -> dict:
        try:
            data = json.loads(ACCOUNTS_FILE.read_text())
            if isinstance(data, dict) and isinstance(data.get("accounts"), list):
                return data
        except FileNotFoundError:
            pass
        except ValueError as exc:
            log.error("accounts.json is invalid (%s) – starting with one account", exc)
        # First start, or an update from a version with a single account: the
        # existing login, URL and settings simply become account 1.
        data = {"accounts": [{"id": "1", "slot": 1, "custom_name": ""}], "next_id": 2, "same_settings": True}
        write_private(ACCOUNTS_FILE, json.dumps(data))
        return data

    def save_registry(self) -> None:
        write_private(
            ACCOUNTS_FILE,
            json.dumps(
                {
                    "accounts": [a.record() for a in self.accounts.values()],
                    "next_id": self.next_id,
                    "same_settings": self.same_settings,
                }
            ),
        )

    @property
    def primary(self) -> "Account | None":
        """The first account (the one older helper integrations know about)."""
        return next(iter(self.accounts.values()), None)

    def account(self, account_id) -> Account:
        account = self.accounts.get(str(account_id or ""))
        if account is None:
            raise AccountError("err_no_account")
        return account

    def add_account(self) -> Account:
        with self.lock:
            if len(self.accounts) >= MAX_ACCOUNTS:
                raise AccountError("err_max_accounts")
            used = {a.slot for a in self.accounts.values()}
            slot = min(s for s in range(1, MAX_ACCOUNTS + 1) if s not in used)
            account_id = str(self.next_id)
            self.next_id += 1
            account = Account({"id": account_id, "slot": slot, "custom_name": ""}, self)
            self.accounts[account.id] = account
            self.save_registry()
            self.reload_nginx()
        log.info("Account %s added", account.id)
        return account

    def remove_account(self, account: Account) -> None:
        account.stop_mcp()
        account.pending_mfa.clear()
        with self.lock:
            self.accounts.pop(account.id, None)
            account.delete_files()
            self.save_registry()
            self.reload_nginx()
        log.info("Account %s removed (tokens deleted)", account.id)

    def rename_account(self, account: Account, name: str) -> None:
        name = " ".join(str(name or "").split())[:40]
        with self.lock:
            account.custom_name = name
            self.save_registry()

    def set_same_settings(self, same: bool) -> None:
        with self.lock:
            self.same_settings = bool(same)
            self.save_registry()
        for account in list(self.accounts.values()):
            account.reload_tools()

    # nginx ---------------------------------------------------------------
    def _report_location(self) -> str:
        """Status channel for the helper integration (webhook mode only).

        Reachable only from Home Assistant's internal network (never via the
        webhooks, which forward /mcp only), and nginx adds the key."""
        if self.options.get("remote_access", "webhook") != "webhook":
            return ""
        return (
            f"        location = /{self.report_secret}/ha {{\n"
            "            allow 172.30.32.0/23;\n"
            "            deny all;\n"
            "            limit_except POST { deny all; }\n"
            f"            proxy_pass http://127.0.0.1:{UI_PORT}/report;\n"
            f'            proxy_set_header X-Report-Key "{self.report_secret}";\n'
            "            proxy_set_header Host 127.0.0.1;\n"
            "            client_max_body_size 4k;\n"
            "        }\n"
        )

    def write_nginx_conf(self) -> None:
        blocks = []
        for account in self.accounts.values():
            write_private(account.proxy_conf, NGINX_PROXY.format(mcp_port=account.port, account=account.id))
            blocks.append(
                NGINX_ACCOUNT.format(
                    secret=account.secret,
                    account=account.id,
                    proxy_conf=account.proxy_conf,
                    ui_port=UI_PORT,
                    report_secret=self.report_secret,
                )
            )
        write_private(
            NGINX_CONF,
            NGINX_TEMPLATE.format(
                public_port=PUBLIC_PORT,
                account_locations="".join(blocks),
                report_location=self._report_location(),
            ),
        )

    def start_nginx(self) -> None:
        self.write_nginx_conf()
        self.nginx = subprocess.Popen(["nginx", "-c", str(NGINX_CONF), "-g", "daemon off;"])
        log.info("nginx listening on port %s", PUBLIC_PORT)

    def reload_nginx(self) -> None:
        self.write_nginx_conf()
        if self.nginx and self.nginx.poll() is None:
            subprocess.run(["nginx", "-c", str(NGINX_CONF), "-s", "reload"], check=False)

    def rotate_secret(self, account: Account) -> None:
        with self.lock:
            account.secret = get_secret(rotate=True, path=account.secret_file)
            self.reload_nginx()

    # all servers ---------------------------------------------------------------
    def start_all(self) -> None:
        for account in list(self.accounts.values()):
            account.start_mcp()

    def supervise(self) -> None:
        ticks = 0
        while not self.stopping:
            time.sleep(5)
            ticks += 1
            accounts = list(self.accounts.values())
            if ticks % 12 == 0:  # once a minute
                for account in accounts:
                    try:
                        account.expire_pending_mfa()
                        account.check_login()
                    except Exception as exc:  # noqa: BLE001
                        log.debug("Login check failed: %s", exc)
            if ticks % 720 == 1:  # at start, then once an hour
                for account in accounts:
                    try:
                        prune_downloads(keep_days(self.options), account.download_dir)
                    except Exception as exc:  # noqa: BLE001
                        log.debug("Download cleanup failed: %s", exc)
            with self.lock:
                if self.stopping:
                    return
                if self.nginx and self.nginx.poll() is not None:
                    log.error("nginx exited (%s), restarting", self.nginx.returncode)
                    self.start_nginx()
            for account in accounts:
                delay = account.supervise_tick()
                if delay and not self.stopping:
                    threading.Timer(delay, account.start_mcp).start()

    def shutdown(self) -> None:
        self.stopping = True
        for account in list(self.accounts.values()):
            account.stop_mcp()
        if self.nginx and self.nginx.poll() is None:
            self.nginx.terminate()


# --------------------------------------------------------------------------
# Remote access via the helper integration
#
# The app has NO access to the Home Assistant API. It only
#   * copies the helper integration into custom_components (and removes it in
#     direct mode),
#   * announces the integration's settings through the Supervisor's discovery
#     service – Home Assistant then sets up (and on uninstall removes) the
#     config entry itself,
#   * receives a status report from the integration over the internal network
#     (secret path + key), answering with the Garmin login state.
# --------------------------------------------------------------------------
def supervisor_api(method: str, path: str, data: dict | None = None):
    """Call the Supervisor (only /discovery is used). Returns the data or None."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        f"http://supervisor{path}",
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            body = json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        log.debug("Supervisor %s %s failed: %s", method, path, exc)
        return None
    return body.get("data", {}) if isinstance(body, dict) else {}


def app_slug() -> str:
    """Slug of this app as the Supervisor knows it (hostname "abcd1234-garmin-mcp")."""
    return socket.gethostname().replace("-", "_")


def _own_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return socket.gethostname()


class RemoteAccess:
    """Keeps the webhook integration installed and announced.

    States: disabled (direct mode), setting_up, restart_needed, active, error.
    """

    def __init__(self, services: "Services") -> None:
        self.services = services
        self.enabled = services.options.get("remote_access", "webhook") == "webhook"
        self.state = "setting_up" if self.enabled else "disabled"
        self.detail = ""
        self._wake = threading.Event()
        self._announced = ""
        self._started = time.time()
        # True when this start copied the integration for the first time:
        # Home Assistant only finds new custom integrations after a restart.
        self.first_install = False
        self.report: dict = {}
        self.cleaned_up = False

    # files ---------------------------------------------------------------
    def _install_component(self) -> bool:
        """Copy the integration into custom_components. True if files changed."""
        src_manifest = json.loads((COMPONENT_SRC / "manifest.json").read_text())
        dst_manifest_file = COMPONENT_DST / "manifest.json"
        try:
            dst_version = json.loads(dst_manifest_file.read_text()).get("version")
        except (OSError, ValueError):
            dst_version = None
        if dst_version == src_manifest.get("version"):
            return False
        COMPONENT_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(COMPONENT_DST, ignore_errors=True)
        shutil.copytree(COMPONENT_SRC, COMPONENT_DST)
        log.info("Installed Home Assistant integration %s %s", WEBHOOK_DOMAIN, src_manifest.get("version"))
        return True

    @staticmethod
    def bundled_version() -> str:
        try:
            return str(json.loads((COMPONENT_SRC / "manifest.json").read_text()).get("version"))
        except (OSError, ValueError):
            return ""

    # discovery -----------------------------------------------------------
    def discovery_config(self) -> dict:
        host = f"http://{_own_ip()}:{PUBLIC_PORT}"
        accounts = [
            {
                "id": account.id,
                "name": account.display_name(),
                "webhook_id": account.webhook_id,
                "target_url": f"{host}/{account.secret}/mcp",
            }
            for account in self.services.accounts.values()
        ]
        config = {
            "accounts": accounts,
            "report_url": f"{host}/{self.services.report_secret}/ha",
            "app_slug": app_slug(),
        }
        if accounts:
            # Helper integrations before 0.5 only know a single account.
            config["webhook_id"] = accounts[0]["webhook_id"]
            config["target_url"] = accounts[0]["target_url"]
        return config

    def _announce(self) -> bool:
        config = self.discovery_config()
        fingerprint = json.dumps(config, sort_keys=True)
        if fingerprint == self._announced:
            return True
        result = supervisor_api("POST", "/discovery", {"service": WEBHOOK_DOMAIN, "config": config})
        if result is None:
            return False
        if result.get("uuid"):
            write_private(DISCOVERY_FILE, str(result["uuid"]))
        self._announced = fingerprint
        log.info("Remote access: settings announced to Home Assistant")
        return True

    def _withdraw(self) -> None:
        try:
            uuid = DISCOVERY_FILE.read_text().strip()
        except OSError:
            return
        if uuid and supervisor_api("DELETE", f"/discovery/{uuid}") is not None:
            DISCOVERY_FILE.unlink(missing_ok=True)

    # status from the integration ----------------------------------------------
    def receive_report(self, report: dict) -> dict:
        def text(key: str, limit: int = 300) -> str:
            value = report.get(key)
            return str(value)[:limit] if isinstance(value, (str, int, float)) else ""

        external, _ = normalize_public_url(text("external_url"))
        self.report = {
            "time": time.time(),
            "external_url": external,
            "language": text("language", 20),
            "version": text("integration_version", 20),
            "restart_needed": bool(report.get("restart_needed")),
        }
        self._update_state()
        # The switches of the helper integration (one per account).
        switches = report.get("accounts")
        if isinstance(switches, dict):
            for account_id, info in list(switches.items())[:MAX_ACCOUNTS]:
                account = self.services.accounts.get(str(account_id))
                if account is not None and isinstance(info, dict) and isinstance(info.get("mcp_enabled"), bool):
                    account.set_switched_off(not info["mcp_enabled"])
        elif isinstance(report.get("mcp_enabled"), bool) and self.services.primary is not None:
            # Helper integration 0.4: one switch for the first account
            self.services.primary.set_switched_off(not report["mcp_enabled"])
        answer = {
            "accounts": {
                account.id: {
                    "name": account.display_name(),
                    "login": account.login_status(),
                    "mcp_enabled": not account.switched_off,
                }
                for account in self.services.accounts.values()
            },
            "notify": bool(self.services.options.get("login_notification", True)),
            "app_version": os.environ.get("APP_VERSION", "dev"),
        }
        primary = self.services.primary
        if primary is not None:  # for helper integrations before 0.5
            answer["login"] = answer["accounts"][primary.id]["login"]
            answer["mcp_enabled"] = answer["accounts"][primary.id]["mcp_enabled"]
        return answer

    def _update_state(self) -> None:
        if not self.enabled or self.state == "error":
            return
        fresh = self.report and time.time() - self.report.get("time", 0) < REPORT_MAX_AGE
        if fresh:
            if self.report.get("restart_needed") or self.report.get("version") != self.bundled_version():
                self.state = "restart_needed"
            else:
                if self.state != "active":
                    log.info("Remote access active")
                self.state, self.detail = "active", ""
        elif self.first_install:
            self.state = "restart_needed"
        elif time.time() - self._started > 300:
            self.state = "restart_needed"
        else:
            self.state = "setting_up"

    # loop ----------------------------------------------------------------
    def _cleanup(self) -> None:
        """Direct mode: remove the helper integration if an earlier start installed it."""
        self._withdraw()  # Home Assistant removes the config entry itself
        if not (COMPONENT_DST.exists() or LEGACY_WEBHOOK_CONFIG.exists()):
            return
        log.info("Remote access is set to direct – removing the helper integration")
        LEGACY_WEBHOOK_CONFIG.unlink(missing_ok=True)
        shutil.rmtree(COMPONENT_DST, ignore_errors=True)
        self.cleaned_up = True
        log.info("Helper integration removed (no Home Assistant restart needed)")

    def run(self) -> None:
        if not self.enabled:
            try:
                self._cleanup()
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not remove the helper integration: %s", exc)
            return
        if not HA_CONFIG.is_dir():
            self.state, self.detail = "error", "@no_config_access"
            log.error("Remote access: %s", i18n.ui("en")["detail_no_config_access"])
            return
        try:
            # New or updated files: Home Assistant needs a restart to load them.
            if self._install_component():
                self.first_install = True
            LEGACY_WEBHOOK_CONFIG.unlink(missing_ok=True)
        except OSError as exc:
            self.state, self.detail = "error", str(exc)
            log.error("Remote access: could not install integration: %s", exc)
            return
        while not self.services.stopping:
            try:
                announced = self._announce()
                self._update_state()
            except Exception as exc:  # noqa: BLE001
                announced = False
                log.warning("Remote access: %s", exc)
            self._wake.wait(30 if not announced or self.state != "active" else 300)
            self._wake.clear()

    def rotate(self, account: "Account") -> None:
        account.webhook_id = get_webhook_id(rotate=True, path=account.webhook_id_file)
        self._wake.set()

    def nudge(self) -> None:
        self._wake.set()

    def base_url(self) -> str:
        """Public base URL: option > address reported by Home Assistant."""
        configured, _ = normalize_public_url(self.services.options.get("public_url"))
        return configured or self.report.get("external_url", "")


# --------------------------------------------------------------------------
# Connection test
# --------------------------------------------------------------------------
def _mcp_request(url: str, payload: dict, host_header: str | None = None, timeout: int = 20):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        # A real client name: Cloudflare and similar services block requests
        # that look like scripts ("Python-urllib").
        "User-Agent": f"Mozilla/5.0 (compatible; GarminConnectMCP/{os.environ.get('APP_VERSION', 'dev')}; "
        "+https://github.com/mw-hbg/ha-garmin-mcp)",
    }
    if host_header:
        headers["Host"] = host_header
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    return json.loads(lines[0] if lines else raw)


def run_connection_test(account: "Account") -> dict:
    """Check server, Garmin account and the public connector URL of an account."""
    result: dict = {"time": time.strftime("%H:%M:%S"), "checks": []}

    def add(key: str, ok: bool, detail: str = "", warn: bool = False) -> None:
        result["checks"].append({"key": key, "ok": ok, "detail": detail, "warn": warn})

    # 1. MCP server answers locally
    try:
        data = _mcp_request(
            f"http://127.0.0.1:{account.port}/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            host_header=f"127.0.0.1:{account.port}",
        )
        add("test_server", True, str(len(data["result"]["tools"])))
    except Exception as exc:  # noqa: BLE001
        add("test_server", False, type(exc).__name__)

    # 2. Garmin account reachable with the saved tokens
    if not account.has_tokens():
        add("test_garmin", False, "@not_logged_in")
    else:
        try:
            client = Garmin()
            client.login(str(account.token_dir))
            add("test_garmin", True, client.full_name or client.display_name or "")
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if isinstance(exc, GarminConnectAuthenticationError) or "password" in text.lower() or "401" in text:
                add("test_garmin", False, "@relogin")
            else:
                add("test_garmin", False, text[:160])
        finally:
            # login() may have refreshed the token files as root – hand them
            # back to the MCP server's user, or it could not update them.
            try:
                prepare_mcp_dirs(mcp_identity(account.user), account)
            except OSError as exc:
                log.warning("Could not fix token permissions: %s", exc)

    # 3. The connector URL works from the internet (round trip via your
    #    public address, exactly like the AI app reaches it)
    if REMOTE.enabled:
        base = REMOTE.base_url()
        url = f"{base}/api/webhook/{account.webhook_id}" if base else ""
    else:
        public, _ = normalize_public_url(SERVICES.options.get("public_url"))
        url = f"{public}/{account.secret}/mcp" if public else ""
    if not url:
        add("test_public", False, "@no_public")
    else:
        try:
            data = _mcp_request(
                url,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "garmin-mcp-app-selftest", "version": "1"},
                    },
                },
            )
            add("test_public", "result" in data, data.get("result", {}).get("serverInfo", {}).get("name", ""))
        except urllib.error.HTTPError as exc:
            if blocked_by_proxy(exc):
                # Blocked before Home Assistant (Cloudflare bot protection, WAF
                # or IP rules). The AI app may still get through – a note, not an error.
                add("test_public", True, f"@blocked_proxy|{exc.code}", warn=True)
            elif exc.code in (401, 403):
                add("test_public", False, f"@http_forbidden|{exc.code}")
            else:
                add("test_public", False, f"HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001
            add("test_public", False, type(exc).__name__)
    result["ok"] = all(c["ok"] for c in result["checks"])
    result["warn"] = any(c.get("warn") for c in result["checks"])
    return result


def blocked_by_proxy(exc: urllib.error.HTTPError) -> bool:
    """True if a 403/429/503 came from Cloudflare (or a similar proxy), not from HA."""
    if exc.code not in (403, 429, 503):
        return False
    headers = {k.lower(): v.lower() for k, v in (exc.headers or {}).items()}
    if "cf-ray" in headers or "cf-mitigated" in headers or "cloudflare" in headers.get("server", ""):
        return True
    try:
        body = exc.read(2048).decode(errors="ignore").lower()
    except Exception:  # noqa: BLE001
        body = ""
    return "cloudflare" in body


SERVICES: Services  # set in main()
REMOTE: RemoteAccess  # set in main()


# --------------------------------------------------------------------------
# Garmin login (with MFA)
# --------------------------------------------------------------------------
class LoginError(Exception):
    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(key)
        self.key = key
        self.detail = detail


LOGIN_ATTEMPTS: list[float] = []
MAX_LOGINS = 5            # per LOGIN_WINDOW – protects your Garmin account from a lockout
LOGIN_WINDOW = 15 * 60


def _throttle_login() -> None:
    now = time.time()
    LOGIN_ATTEMPTS[:] = [t for t in LOGIN_ATTEMPTS if now - t < LOGIN_WINDOW]
    if len(LOGIN_ATTEMPTS) >= MAX_LOGINS:
        raise LoginError("err_too_many_attempts")
    LOGIN_ATTEMPTS.append(now)


LOGIN_LOCK = threading.Lock()


def _translate_login_error(exc: Exception) -> LoginError:
    if isinstance(exc, GarminConnectAuthenticationError):
        text = str(exc).lower()
        if "mfa" in text or "code" in text:
            return LoginError("err_mfa")
        return LoginError("err_credentials")
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return LoginError("err_rate_limit")
    if isinstance(exc, GarminConnectConnectionError):
        return LoginError("err_connection", str(exc))
    return LoginError("err_unknown", str(exc))


def _finish_login(account: "Account", garmin: Garmin) -> str:
    """Store tokens, verify them and remember the account name."""
    account.base.mkdir(mode=0o711, parents=True, exist_ok=True)
    tmp = account.base / "garmin_tokens.new"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(mode=0o700)
    garmin.client.dump(str(tmp))
    verify = Garmin()
    verify.login(str(tmp))
    name = verify.full_name or verify.display_name or ""
    shutil.rmtree(account.token_dir, ignore_errors=True)
    tmp.rename(account.token_dir)
    secure_dir(account.token_dir)
    write_private(account.info_file, json.dumps({"name": name, "since": int(time.time())}))
    log.info("[%s] Logged in to Garmin Connect", name or account.id)
    account.auth_failed_file.unlink(missing_ok=True)
    account.reset_login_state()
    account.restart_mcp()
    remote = globals().get("REMOTE")
    if remote is not None:
        remote.nudge()  # the name shown in Home Assistant may have changed
    return name


def start_login(account: "Account", email: str, password: str) -> str:
    """Returns 'done' or 'mfa'. Raises LoginError."""
    with LOGIN_LOCK:
        if account.has_tokens() and account.login_status() != "failed":
            # A second click while the first login was still running – don't
            # log in again (Garmin rate-limits repeated logins). A login that
            # Garmin rejects may be replaced right away (re-login).
            return "done"
        account.pending_mfa.clear()
        _throttle_login()
        try:
            garmin = Garmin(email=email, password=password, return_on_mfa=True)
            result, _state = garmin.client.login(email, password, return_on_mfa=True)
            if result == "needs_mfa":
                account.pending_mfa.update({"garmin": garmin, "state": _state, "started": time.time()})
                return "mfa"
            _finish_login(account, garmin)
            return "done"
        except LoginError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Garmin login failed: %s", type(exc).__name__)
            raise _translate_login_error(exc) from exc


def finish_mfa(account: "Account", code: str) -> None:
    with LOGIN_LOCK:
        pending = account.pending_mfa
        if not pending or time.time() - pending["started"] > MFA_TIMEOUT:
            pending.clear()
            raise LoginError("err_mfa_expired")
        garmin, state = pending["garmin"], pending["state"]
        try:
            garmin.resume_login(state, code.strip())
            _finish_login(account, garmin)
        except Exception as exc:  # noqa: BLE001
            log.warning("Garmin MFA failed: %s", type(exc).__name__)
            raise _translate_login_error(exc) from exc
        finally:
            pending.clear()


def logout(account: "Account") -> None:
    account.stop_mcp()
    shutil.rmtree(account.token_dir, ignore_errors=True)
    for path in (account.info_file, account.base / "garmin_tokens.b64", account.auth_failed_file):
        path.unlink(missing_ok=True)
    log.info("[%s] Logged out of Garmin Connect, tokens deleted", account.id)


# --------------------------------------------------------------------------
# Web UI (Home Assistant ingress)
# --------------------------------------------------------------------------

CSRF_TOKEN = secrets.token_urlsafe(24)
FLASH: dict = {}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1c1c1c;--muted:#5f6368;--accent:#0d47a1;--border:#e0e3e7;--ok:#1b7f3b;--err:#b3261e;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1c2026;--text:#e8eaed;--muted:#9aa0a6;--accent:#8ab4f8;--border:#2f343b;--ok:#81c995;--err:#f28b82;--warn:#fdd663}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
main{max-width:760px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 16px}h2{font-size:17px;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.muted{color:var(--muted)}.ok{color:var(--ok)}.err{color:var(--err)}.warn{color:var(--warn)}
label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
input{width:100%;padding:9px 11px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text);font-size:15px}
button{margin-top:14px;padding:9px 16px;border:0;border-radius:8px;background:var(--accent);color:#fff;font-size:14px;cursor:pointer}
@media (prefers-color-scheme:dark){button{color:#111}}
button.secondary{background:transparent;color:var(--accent);border:1px solid var(--border)}
button.danger{color:var(--err)}
select{padding:8px 10px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--text);font-size:15px}
label.check{display:inline-flex;gap:6px;align-items:center;color:var(--text);font-size:14px;margin:6px 14px 0 0}
label.check input{width:auto}
details.rename summary{list-style:none;font-weight:normal;padding:0 4px}
details.rename summary::-webkit-details-marker{display:none}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.row button{margin-top:0}
code{display:block;padding:9px 11px;border-radius:8px;border:1px solid var(--border);word-break:break-all;font-size:13px;flex:1;min-width:0}
h3{font-size:15px;margin:18px 0 8px}
.cats td{padding:4px 14px 4px 0}.num{color:var(--muted);white-space:nowrap}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:10px;margin-right:4px;border:1px solid}
.badge.read{color:var(--ok);border-color:var(--ok)}.badge.create{color:var(--accent);border-color:var(--accent)}.badge.change{color:var(--err);border-color:var(--err)}
a.btn{display:inline-block;margin-top:14px;padding:9px 16px;border-radius:8px;background:var(--accent);color:#fff;text-decoration:none;font-size:14px}
a.btn.secondary{background:transparent;color:var(--accent);border:1px solid var(--border)}
@media (prefers-color-scheme:dark){a.btn{color:#111}a.btn.secondary{color:var(--accent)}}
.links{gap:10px}
.toolbar{position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:2}
.tool{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--border)}
.tool input{width:auto;margin-top:3px}.tool .txt{flex:1}.tool code{display:inline;border:0;padding:0;font-size:12px;color:var(--muted)}
.info{background:none;border:1px solid var(--border);color:var(--accent);border-radius:50%;width:24px;height:24px;padding:0;margin:0;font-size:13px;line-height:22px;flex:none}
.infobox{display:none;margin-top:6px;padding:8px 10px;border-radius:8px;border:1px solid var(--border);font-size:13px}
.infobox.open{display:block}
summary{cursor:pointer;font-weight:600;padding:6px 0}
.savebar{position:sticky;bottom:0;background:var(--bg);padding:10px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.footer{text-align:center;font-size:12px;margin-top:8px}
.badge.new{color:var(--warn);border-color:var(--warn)}
.busy-note{display:none;margin-top:10px}button:disabled{opacity:.6;cursor:wait}
.banner{padding:14px 16px;border-radius:12px;margin-bottom:16px;border:2px solid var(--warn)}
.flash{padding:10px 14px;border-radius:8px;margin-bottom:16px;border:1px solid var(--border)}
table{border-collapse:collapse}td{padding:3px 16px 3px 0;vertical-align:top}
"""

JS = """
function toggle(id,btn){const el=document.getElementById(id);const hidden=el.dataset.hidden!=='0';
el.textContent=hidden?el.dataset.value:el.dataset.mask;el.dataset.hidden=hidden?'0':'1';btn.textContent=hidden?btn.dataset.hide:btn.dataset.show}
function busy(form){const b=form.querySelector('button[type=submit]');if(form.dataset.busy){return false}
form.dataset.busy='1';if(b){b.disabled=true;b.textContent=b.dataset.busy||b.textContent}
const n=form.querySelector('.busy-note');if(n){n.style.display='block'}return true}
function copyVal(id,btn){navigator.clipboard.writeText(document.getElementById(id).dataset.value).then(()=>{const t=btn.textContent;btn.textContent=btn.dataset.done;setTimeout(()=>btn.textContent=t,1500)})}
"""


def _config_url() -> str:
    """Link to this app's configuration tab in the Home Assistant UI."""
    return f"/config/app/{app_slug()}/config"


DOCS_BASE = "https://github.com/mw-hbg/ha-garmin-mcp/blob/main/garmin_mcp"
LANG_COOKIE = "garmin_mcp_lang"


def ha_language() -> str:
    """Home Assistant language, as reported by the helper integration."""
    remote = globals().get("REMOTE")
    return remote.report.get("language", "") if remote is not None else ""


def _lang(request: Request) -> str:
    """Language chosen on the page > browser language > Home Assistant language > English."""
    return i18n.pick(
        request.cookies.get(LANG_COOKIE),
        i18n.from_accept_language(request.headers.get("accept-language")),
        ha_language(),
    )


def detail_text(t: dict, detail: str) -> str:
    """Details starting with "@" are translated ("@key" or "@key|value")."""
    if not detail.startswith("@"):
        return html.escape(detail)
    key, _, value = detail[1:].partition("|")
    return html.escape(t.get("detail_" + key, key).replace("{value}", value))


def _language_links(request: Request, current: str) -> str:
    links = []
    for code, name in i18n.names().items():
        if code == current:
            links.append(f"<b>{html.escape(name)}</b>")
        else:
            links.append(f'<a href="lang?l={code}">{html.escape(name)}</a>')
    return " · ".join(links) if len(links) > 1 else ""


def _guard(request: Request, allow_local: bool = False) -> Response | None:
    """Only Home Assistant's ingress proxy may use the page.

    127.0.0.1 is allowed only for the health check (status.json): the MCP
    server runs in the same container, and must not be able to read the page
    (CSRF token, connector URL) or press its buttons."""
    client = request.client.host if request.client else ""
    if ALLOW_ANY_UI_CLIENT or client == INGRESS_PROXY_IP or (allow_local and client == "127.0.0.1"):
        return None
    return Response("Forbidden", status_code=403)


def _redirect(request: Request) -> RedirectResponse:
    base = request.headers.get("x-ingress-path", "")
    return RedirectResponse(f"{base}/", status_code=303)


async def _form(request: Request) -> dict | None:
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), CSRF_TOKEN):
        FLASH.update(kind="err", key="err_csrf")
        return None
    return dict(form)


def _secret_field(fid: str, value: str, t: dict) -> str:
    mask = "•" * 24
    if "://" in value:
        scheme, rest = value.split("://", 1)
        host = rest.split("/", 1)[0]
        mask = f"{scheme}://{host}/{'•' * 20}"
    v = html.escape(value, quote=True)
    m = html.escape(mask, quote=True)
    return (
        f'<div class="row"><code id="{fid}" data-value="{v}" data-mask="{m}" data-hidden="1">{m}</code>'
        f'<button type="button" class="secondary" data-show="{t["show"]}" data-hide="{t["hide"]}" '
        f'onclick="toggle(\'{fid}\',this)">{t["show"]}</button>'
        f'<button type="button" class="secondary" data-done="{t["copied"]}" '
        f'onclick="copyVal(\'{fid}\',this)">{t["copy"]}</button></div>'
    )


def _csrf() -> str:
    return f'<input type="hidden" name="csrf" value="{CSRF_TOKEN}">'


def _acc_field(account: "Account") -> str:
    return f'<input type="hidden" name="account" value="{html.escape(account.id, quote=True)}">'


def _rights_rows(lang: str, t: dict, active: set[str]) -> str:
    rows = []
    for module in i18n.CATEGORY_ORDER:
        tools_in = [e for e in CATALOG if e["module"] == module]
        if not tools_in:
            continue
        on = [e for e in tools_in if e["name"] in active]
        kinds = {e["kind"] for e in on}
        badges = "".join(
            f'<span class="badge {k}">{t["kind_" + k]}</span>' for k in ("read", "create", "change") if k in kinds
        ) or f'<span class="muted">{t["nothing"]}</span>'
        rows.append(
            f'<tr><td>{html.escape(i18n.category(lang, module))}</td><td class="num">{len(on)}/{len(tools_in)}</td><td>{badges}</td></tr>'
        )
    return f'<table class="cats">{"".join(rows)}</table>'


def _test_html(t: dict, result: dict) -> str:
    if not result:
        return ""
    items = "".join(
        f'<tr><td>{"⚠️" if c.get("warn") else "✅" if c["ok"] else "❌"}</td><td>{t[c["key"]]}</td>'
        f'<td class="muted">{detail_text(t, c["detail"])}</td></tr>'
        for c in result["checks"]
    )
    if not result["ok"]:
        summary, cls = t["test_failed"], "err"
    elif result.get("warn"):
        summary, cls = t["test_warn"], "warn"
    else:
        summary, cls = t["test_ok"], "ok"
    return f'<p class="{cls}">{summary} <span class="muted">({result["time"]})</span></p><table>{items}</table>'


def _connector_url(account: "Account", base: str) -> str:
    if REMOTE.enabled:
        return f"{base or 'https://<your-home-assistant>'}/api/webhook/{account.webhook_id}"
    public, _ = normalize_public_url(SERVICES.options.get("public_url"))
    return f"{public or 'https://<your-domain>'}/{account.secret}/mcp"


async def _account_card(request: Request, lang: str, t: dict, account: "Account", base: str) -> str:
    csrf, acc = _csrf(), _acc_field(account)
    name = html.escape(account.display_name() if (account.custom_name or account.garmin_name()) else t["account_n"].format(n=account.id))
    garmin_name = account.garmin_name()
    parts = ['<div class="card">']
    parts.append(
        f'<div class="row"><h2 style="margin:0">{name}</h2>'
        f'<details class="rename"><summary title="{t["rename"]}" aria-label="{t["rename"]}">✏️</summary>'
        f'<form method="post" action="accounts/rename">{csrf}{acc}'
        f'<label>{t["rename"]}</label><input name="name" maxlength="40" value="{html.escape(account.custom_name, quote=True)}" '
        f'placeholder="{html.escape(garmin_name or t["account_n"].format(n=account.id), quote=True)}">'
        f'<p class="muted">{t["rename_hint"]}</p><button type="submit">{t["save_name"]}</button></form></details></div>'
    )
    if account.custom_name and garmin_name:
        parts.append(f'<p class="muted" style="margin:4px 0 0">{t["garmin_profile"]}: {html.escape(garmin_name)}</p>')

    # login
    login_broken = account.has_tokens() and await anyio.to_thread.run_sync(account.login_status) == "failed"
    login_form = (
        f'<form method="post" action="login" onsubmit="return busy(this)">{csrf}{acc}'
        f'<label>{t["email"]}</label><input name="email" type="email" autocomplete="username" required>'
        f'<label>{t["password"]}</label><input name="password" type="password" autocomplete="current-password" required>'
        f'<button type="submit" data-busy="{t["login_busy"]}">{{button}}</button>'
        f'<p class="muted busy-note">{t["login_wait"]}</p></form>'
    )
    if account.pending_mfa:
        parts.append(
            f'<p>{t["mfa_hint"]}</p><form method="post" action="mfa" onsubmit="return busy(this)">{csrf}{acc}'
            f'<label>{t["mfa_code"]}</label><input name="code" inputmode="numeric" autocomplete="one-time-code" required autofocus>'
            f'<div class="row"><button type="submit" data-busy="{t["login_busy"]}">{t["confirm"]}</button>'
            f'<button type="submit" class="secondary" formaction="cancel" formnovalidate>{t["cancel"]}</button></div></form>'
        )
    elif login_broken:
        parts.append(
            f'<p>{t["last_connected_as"]} <b>{html.escape(garmin_name or "–")}</b></p>'
            f'<p class="err">{t["relogin_needed"]}</p>' + login_form.replace("{button}", t["relogin"])
        )
    elif account.has_tokens():
        parts.append(f'<p>{t["connected_as"]} <b>{html.escape(garmin_name or "–")}</b></p>')
        if account.options().get("write_access") != "read_only":
            parts.append(f'<p class="muted">{t["upload_hint"]}</p>')
    else:
        parts.append(f'<p class="muted">{t["not_connected"]}</p>' + login_form.replace("{button}", t["login"]))

    # server and rights
    state = await anyio.to_thread.run_sync(account.shown_state)
    state_cls = {"ready": "ok", "failed": "err", "pending": "warn", "off": "warn"}.get(state, "muted")
    custom = account.selection_file().exists()
    wa = account.options().get("write_access", "create_only")
    rights = t["custom_selection"] if custom else t.get("wa_" + wa, wa)
    parts.append(
        f'<table><tr><td class="muted">{t["state"]}</td><td class="{state_cls}">{t["state_" + state]}</td></tr>'
        f'<tr><td class="muted">{t["tools"]}</td><td>{len(account.active_tools)} / {len(ALL_TOOLS)}</td></tr>'
        f'<tr><td class="muted">{t["write_access"]}</td><td>{rights}</td></tr></table>'
    )
    if not SERVICES.same_settings:
        own = account.own_settings()
        options = "".join(
            f'<option value="{v}"{" selected" if own["write_access"] == v else ""}>{t["wa_" + v]}</option>'
            for v in ("read_only", "create_only", "full")
        )
        areas = "".join(
            f'<label class="check"><input type="checkbox" name="area" value="{a}"'
            f'{" checked" if a in own["tool_areas"] else ""}> {t["area_" + a]}</label>'
            for a in TOOL_AREAS
        )
        fresh = new_tools(account.selection_file())
        parts.append(
            f'<details><summary>{t["account_rights"]}</summary>'
            + (f'<p class="warn">{t["new_tools_hint"].format(n=len(fresh))}</p>' if fresh else "")
            + f'<h3>{t["what_ai_may"]}</h3>{_rights_rows(lang, t, account.active_tools)}'
            f'<form method="post" action="accounts/settings" onsubmit="return busy(this)">{csrf}{acc}'
            f'<label>{t["write_access"]}</label><select name="write_access">{options}</select>'
            f'<label>{t["tool_areas"]}</label><div class="areas">{areas}</div>'
            + (f'<p class="muted">{t["custom_selection_note"]}</p>' if custom else "")
            + f'<div class="row"><button type="submit" data-busy="{t["restart_busy"]}">{t["save"]}</button>'
            f'<a class="btn secondary" href="tools?account={html.escape(account.id)}">{t["choose_tools"]}</a></div></form></details>'
        )

    # connector URL
    parts.append(f'<label>{t["connector_url"]}</label>{_secret_field("url" + account.id, _connector_url(account, base), t)}')
    if REMOTE.enabled and not base:
        parts.append(f'<p class="muted">{t["no_base_url"]}</p>')

    # test, new URL, log out, remove
    parts.append(_test_html(t, account.test_result))
    parts.append(
        '<div class="row">'
        f'<form method="post" action="test" onsubmit="return busy(this)">{csrf}{acc}'
        f'<button type="submit" class="secondary" data-busy="{t["test_busy"]}">{t["test_run"]}</button></form>'
        f'<form method="post" action="rotate" onsubmit="return confirm(\'{t["rotate_confirm"]}\')">{csrf}{acc}'
        f'<button type="submit" class="secondary">{t["rotate"]}</button></form>'
        + (
            f'<form method="post" action="logout" onsubmit="return confirm(\'{t["logout_confirm"]}\')">{csrf}{acc}'
            f'<button type="submit" class="secondary">{t["logout"]}</button></form>'
            if account.has_tokens() else ""
        )
        + f'<form method="post" action="accounts/remove" onsubmit="return confirm(\'{t["remove_confirm"]}\')">{csrf}{acc}'
        f'<button type="submit" class="secondary danger">{t["remove_account"]}</button></form></div>'
    )
    parts.append("</div>")
    return "".join(parts)


async def index(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    lang = _lang(request)
    t = i18n.ui(lang)
    services = SERVICES
    csrf = _csrf()
    parts = [f"<h1>{t['title']}</h1>"]

    if FLASH:
        kind, key = FLASH.get("kind", "ok"), FLASH.get("key", "")
        detail = FLASH.get("detail", "")
        msg = t.get(key, key) + (f" <span class='muted'>({html.escape(detail)})</span>" if detail else "")
        parts.append(f'<div class="flash {kind}">{msg}</div>')
        FLASH.clear()

    # Restart banner – shown above everything else
    if REMOTE.enabled and REMOTE.state == "restart_needed":
        parts.append(f'<div class="banner"><b>{t["restart_banner_title"]}</b><p>{t["restart_hint"]}</p></div>')
    accounts = list(services.accounts.values())
    if len(accounts) >= LOAD_WARNING_FROM:
        parts.append(f'<div class="banner">{t["load_warning"]}</div>')

    base = await anyio.to_thread.run_sync(REMOTE.base_url) if REMOTE.enabled else ""
    for account in accounts:
        parts.append(await _account_card(request, lang, t, account, base))

    # add an account
    parts.append(f'<div class="card"><h2>{t["add_account"]}</h2>')
    if len(accounts) >= MAX_ACCOUNTS:
        parts.append(f'<p class="muted">{t["max_accounts"].format(n=MAX_ACCOUNTS)}</p>')
    else:
        parts.append(f'<p class="muted">{t["add_account_hint"]}</p>')
        if len(accounts) + 1 >= LOAD_WARNING_FROM:
            parts.append(f'<p class="warn">{t["load_warning"]}</p>')
        parts.append(
            f'<form method="post" action="accounts/add">{csrf}<button type="submit">{t["add_account"]}</button></form>'
        )
    parts.append("</div>")

    # rights: shared or per account
    same = services.same_settings
    shared_env, shared_active = tool_selection(services.options, SELECTION_FILE)
    del shared_env
    custom = SELECTION_FILE.exists()
    wa = services.options.get("write_access", "create_only")
    rights = t["custom_selection"] if custom else t.get("wa_" + wa, wa)
    parts.append(
        f'<div class="card"><h2>{t["settings_title"]}</h2>'
        f'<form method="post" action="settings/shared" onsubmit="return busy(this)">{csrf}'
        f'<label class="check"><input type="checkbox" name="same" value="1"{" checked" if same else ""}> '
        f'<b>{t["same_settings"]}</b></label>'
        f'<p class="muted">{t["same_settings_on"] if same else t["same_settings_off"]}</p>'
        f'<button type="submit" class="secondary" data-busy="{t["restart_busy"]}">{t["save"]}</button></form>'
    )
    if same:
        parts.append(
            f'<table><tr><td class="muted">{t["tools"]}</td><td>{len(shared_active)} / {len(ALL_TOOLS)}</td></tr>'
            f'<tr><td class="muted">{t["write_access"]}</td><td>{rights}</td></tr></table>'
            + (f'<p class="warn">{t["new_tools_hint"].format(n=len(fresh))} <a href="tools">{t["review"]}</a></p>' if (fresh := new_tools()) else "")
            + (
                f'<p class="warn">{t["unknown_tools"]} <code>{html.escape(", ".join(unknown))}</code></p>'
                if not custom and (unknown := unknown_tool_names(services.options))
                else ""
            )
            + f'<h3>{t["what_ai_may"]}</h3>{_rights_rows(lang, t, shared_active)}'
            f'<div class="row links"><a class="btn" href="tools">{t["choose_tools"]}</a>'
            f'<a class="btn secondary" href="{_config_url()}" target="_top">{t["open_config"]}</a></div>'
        )
    parts.append("</div>")

    # remote access
    remote = REMOTE
    direct_public, url_problem = normalize_public_url(services.options.get("public_url"))
    internal = f"http://{socket.gethostname()}:{PUBLIC_PORT}"
    parts.append(f'<div class="card"><h2>{t["connection"]}</h2>')
    if url_problem:
        parts.append(f'<p class="warn">{t["public_url_" + url_problem]}</p>')
    if remote.enabled:
        rstate = remote.state
        rcls = {"active": "ok", "error": "err", "restart_needed": "warn"}.get(rstate, "muted")
        parts.append(
            f'<table><tr><td class="muted">{t["remote"]}</td>'
            f'<td class="{rcls}">{t["remote_" + rstate]}'
            + (f' <span class="muted">({detail_text(t, remote.detail)})</span>' if rstate == "error" and remote.detail else "")
            + "</td></tr></table>"
            f'<p class="warn">{t["secret_warning"]}</p><p>{t["steps"]}</p><p class="muted">{t["oauth_hint"]}</p>'
        )
    else:
        if remote.cleaned_up:
            parts.append(f'<p class="ok">{t["cleaned_up"]}</p>')
        parts.append(
            ("" if direct_public else f'<p class="muted">{t["no_public_url"]}</p>')
            + f'<p class="warn">{t["secret_warning"]}</p><p>{t["steps"]}</p>'
            f'<label>{t["internal_url"]}</label><div class="row"><code>{html.escape(internal)}</code></div>'
            f'<p class="muted">{t["internal_hint"]}</p>'
        )
    parts.append(f'<p class="muted">{t["admins_note"]}</p></div>')

    parts.append(
        f'<p class="muted footer">Garmin Connect MCP {html.escape(os.environ.get("APP_VERSION", "dev"))}'
        f' · <a href="{DOCS_BASE}/DOCS.md#{t["docs_section"]}" target="_blank" rel="noopener">{t["docs"]}</a>'
        + (f" · {links}" if (links := _language_links(request, lang)) else "")
        + "</p>"
    )
    shown = await anyio.to_thread.run_sync(page_status)
    waiting = (
        any(a.shown_state() == "pending" for a in accounts) or REMOTE.state == "setting_up"
    ) and not any(a.pending_mfa for a in accounts)
    page = (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{t['title']}</title><style>{CSS}</style></head>"
        f"<body><main>{''.join(parts)}</main><script>{JS}</script>"
        # While a server or remote access is still starting, check the status
        # every few seconds and reload only when it changed – and never while
        # the user is typing into a form (login, 2FA code).
        + (f"<script>const SHOWN={json.dumps(shown)};{STATUS_POLL_JS}</script>" if waiting else "")
        + "</body></html>"
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "X-Frame-Options": "SAMEORIGIN"})


async def _account_form(request: Request) -> tuple[dict, "Account"] | None:
    """Form of an account card: CSRF checked, account looked up."""
    form = await _form(request)
    if form is None:
        return None
    try:
        return form, SERVICES.account(form.get("account"))
    except AccountError as exc:
        FLASH.update(kind="err", key=exc.key)
        return None


async def do_login(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        form, account = got
        email = str(form.get("email", "")).strip()
        password = str(form.get("password", ""))
        try:
            result = await anyio.to_thread.run_sync(start_login, account, email, password)
            if result == "done":
                FLASH.update(kind="ok", key="ok_login")
        except LoginError as exc:
            FLASH.update(kind="err", key=exc.key, detail=exc.detail[:200])
        finally:
            password = ""
            form.pop("password", None)
    return _redirect(request)


async def do_mfa(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        form, account = got
        try:
            await anyio.to_thread.run_sync(finish_mfa, account, str(form.get("code", "")))
            FLASH.update(kind="ok", key="ok_login")
        except LoginError as exc:
            FLASH.update(kind="err", key=exc.key, detail=exc.detail[:200])
    return _redirect(request)


async def do_cancel(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        got[1].pending_mfa.clear()
    return _redirect(request)


async def do_logout(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        await anyio.to_thread.run_sync(logout, got[1])
        FLASH.update(kind="ok", key="ok_logout")
    return _redirect(request)


async def do_rotate(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        account = got[1]
        await anyio.to_thread.run_sync(SERVICES.rotate_secret, account)
        REMOTE.rotate(account)
        FLASH.update(kind="ok", key="ok_rotate")
    return _redirect(request)


async def do_test(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        account = got[1]
        account.test_result.clear()
        account.test_result.update(await anyio.to_thread.run_sync(run_connection_test, account))
    return _redirect(request)


async def add_account(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        try:
            await anyio.to_thread.run_sync(SERVICES.add_account)
            REMOTE.nudge()
            FLASH.update(kind="ok", key="ok_account_added")
        except AccountError as exc:
            FLASH.update(kind="err", key=exc.key)
    return _redirect(request)


async def remove_account(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        await anyio.to_thread.run_sync(SERVICES.remove_account, got[1])
        REMOTE.nudge()
        FLASH.update(kind="ok", key="ok_account_removed")
    return _redirect(request)


async def rename_account(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (got := await _account_form(request)) is not None:
        form, account = got
        await anyio.to_thread.run_sync(SERVICES.rename_account, account, str(form.get("name", "")))
        REMOTE.nudge()
        FLASH.update(kind="ok", key="ok_renamed")
    return _redirect(request)


async def account_settings(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), CSRF_TOKEN):
        FLASH.update(kind="err", key="err_csrf")
        return _redirect(request)
    try:
        account = SERVICES.account(form.get("account"))
    except AccountError as exc:
        FLASH.update(kind="err", key=exc.key)
        return _redirect(request)
    account.save_own_settings(str(form.get("write_access", "")), [str(a) for a in form.getlist("area")])
    await anyio.to_thread.run_sync(account.reload_tools)
    FLASH.update(kind="ok", key="ok_rights")
    return _redirect(request)


async def shared_settings(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (form := await _form(request)) is not None:
        await anyio.to_thread.run_sync(SERVICES.set_same_settings, form.get("same") == "1")
        FLASH.update(kind="ok", key="ok_same_settings")
    return _redirect(request)


def page_status() -> str:
    """Status as the page shows it – compared with status.json by STATUS_POLL_JS."""
    states = [f"{a.id}:{a.shown_state()}:{int(a.has_tokens())}" for a in SERVICES.accounts.values()]
    return "|".join([*states, REMOTE.state])


STATUS_POLL_JS = """
(function(){
  // SHOWN: the status this page was rendered with (same format as status.json "state")
  function busyTyping(){
    const a=document.activeElement;
    if(a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.tagName==='SELECT'))return true;
    return Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([name=name])')).some(i=>i.value);
  }
  async function poll(){
    try{
      const r=await fetch('status.json',{cache:'no-store'});
      const s=await r.json();
      if(s.state!==SHOWN&&!busyTyping()&&!document.querySelector('form[data-busy]')){location.reload();return}
    }catch(e){}
    setTimeout(poll,5000);
  }
  setTimeout(poll,3000);
})();
"""


def _page(request: Request, t: dict, body: str, extra_js: str = "") -> HTMLResponse:
    return HTMLResponse(
        f'<!doctype html><html lang="{_lang(request)}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{t['title']}</title><style>{CSS}</style></head>"
        f"<body><main>{body}</main><script>{JS}{extra_js}</script></body></html>",
        headers={"Cache-Control": "no-store", "X-Frame-Options": "SAMEORIGIN"},
    )


TOOLS_JS = """
function q(s){return Array.from(document.querySelectorAll(s))}
function count(){const n=q('.tool input:checked').length;document.getElementById('cnt').textContent=n;
q('details').forEach(d=>{const all=d.querySelectorAll('.tool input').length,on=d.querySelectorAll('.tool input:checked').length;d.querySelector('.ccount').textContent=on+'/'+all})}
function preset(kinds){q('.tool input').forEach(c=>c.checked=kinds.includes(c.dataset.kind));count()}
function filt(v){v=v.toLowerCase();q('.tool').forEach(r=>{r.style.display=r.dataset.search.includes(v)?'':'none'});
q('details').forEach(d=>{const vis=Array.from(d.querySelectorAll('.tool')).some(r=>r.style.display!=='none');d.style.display=vis?'':'none';if(v)d.open=true})}
function info(b){b.closest('.tool').querySelector('.infobox').classList.toggle('open')}
document.addEventListener('change',e=>{if(e.target.matches('.tool input'))count()});count();
"""


def _tools_target(account_id) -> tuple["Account | None", Path, set[str]]:
    """(account or None for the shared choice, selection file, active tools)."""
    if account_id and not SERVICES.same_settings:
        account = SERVICES.account(account_id)
        return account, account.own_selection_file, account.active_tools
    _env, active = tool_selection(SERVICES.options, SELECTION_FILE)
    return None, SELECTION_FILE, active


async def tools_page(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    lang = _lang(request)
    t = i18n.ui(lang)
    try:
        account, selection_file, active = _tools_target(request.query_params.get("account"))
    except AccountError:
        return _redirect(request)
    csrf = _csrf()
    title = t["tools_title"] + (f" – {html.escape(account.display_name())}" if account else "")
    parts = [f'<p><a href="./">{t["back"]}</a></p><h1>{title}</h1>']
    if FLASH:
        parts.append(f'<div class="flash {FLASH.get("kind", "ok")}">{t.get(FLASH.get("key", ""), "")}</div>')
        FLASH.clear()
    fresh = set(new_tools(selection_file))
    if fresh:
        parts.append(f'<div class="banner">{t["new_tools_banner"].format(n=len(fresh))}</div>')
    acc = _acc_field(account) if account else ""
    parts.append(
        f'<p class="muted">{t["tools_intro"]}</p>'
        f'<div class="toolbar"><input type="search" placeholder="{t["search"]}" oninput="filt(this.value)">'
        f'<div class="row" style="margin-top:8px"><span class="muted">{t["preset"]}</span>'
        f'<button type="button" class="secondary" onclick="preset([\'read\'])">{t["preset_read"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([\'read\',\'create\'])">{t["preset_create"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([\'read\',\'create\',\'change\'])">{t["preset_all"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([])">{t["preset_none"]}</button></div></div>'
        f'<form method="post" action="tools" onsubmit="return busy(this)">{csrf}{acc}'
    )
    for module in i18n.CATEGORY_ORDER:
        cat = i18n.category(lang, module)
        entries = sorted((e for e in CATALOG if e["module"] == module), key=lambda e: ("read", "create", "change").index(e["kind"]))
        if not entries:
            continue
        parts.append(f'<details class="card" open><summary>{html.escape(cat)} <span class="muted ccount"></span></summary>')
        for e in entries:
            label = i18n.tool(lang, e["name"], e["doc"])
            search = html.escape(f'{e["name"]} {label} {e["doc"]} {cat} {i18n.category("en", module)}'.lower(), quote=True)
            checked = " checked" if e["name"] in active else ""
            parts.append(
                f'<div class="tool" data-search="{search}">'
                f'<input type="checkbox" name="tool" value="{e["name"]}" data-kind="{e["kind"]}" id="t_{e["name"]}"{checked}>'
                f'<div class="txt"><label for="t_{e["name"]}" style="margin:0;color:inherit;font-size:14px">{html.escape(label)}</label>'
                f' <span class="badge {e["kind"]}">{t["kind_" + e["kind"]]}</span>'
                + (f' <span class="badge new">{t["new"]}</span>' if e["name"] in fresh else "")
                + f'<div class="infobox"><b>{t["info_name"]}:</b> <code>{e["name"]}</code><br>'
                f'<b>{t["info_kind"]}:</b> {t["info_kind_" + e["kind"]]}'
                + (f'<br><b>{t["info_original"]}:</b> {html.escape(e["doc"])}' if e["doc"] and e["doc"].rstrip(".") != label.rstrip(".") else "")
                + '</div></div>'
                f'<button type="button" class="info" onclick="info(this)" aria-label="{t["info"]}">i</button></div>'
            )
        parts.append("</details>")
    parts.append(
        f'<div class="savebar"><button type="submit" data-busy="{t["restart_busy"]}">{t["save"]}</button>'
        f'<span class="muted"><span id="cnt"></span> / {len(CATALOG)} {t["selected"]}</span></div></form>'
    )
    if selection_file.exists():
        parts.append(
            f'<form method="post" action="tools/reset" onsubmit="return confirm(\'{t["reset_confirm"]}\')">{csrf}{acc}'
            f'<button type="submit" class="secondary">{t["reset"]}</button></form>'
        )
    return _page(request, t, "".join(parts), TOOLS_JS)


def _reload_after_tool_change(account: "Account | None") -> None:
    for target in [account] if account else list(SERVICES.accounts.values()):
        target.reload_tools()


async def save_tools(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), CSRF_TOKEN):
        FLASH.update(kind="err", key="err_csrf")
        return _redirect(request)
    try:
        account, selection_file, _active = _tools_target(form.get("account"))
    except AccountError as exc:
        FLASH.update(kind="err", key=exc.key)
        return _redirect(request)
    picked = {str(v) for v in form.getlist("tool")} & ALL_TOOLS
    save_selection(picked, selection_file)
    log.info("Tool selection saved (%d tools)", len(picked))
    await anyio.to_thread.run_sync(_reload_after_tool_change, account)
    FLASH.update(kind="ok", key="ok_tools")
    return _redirect(request)


async def reset_tools(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if (form := await _form(request)) is not None:
        try:
            account, selection_file, _active = _tools_target(form.get("account"))
        except AccountError:
            return _redirect(request)
        selection_file.unlink(missing_ok=True)
        await anyio.to_thread.run_sync(_reload_after_tool_change, account)
        FLASH.update(kind="ok", key="ok_tools_reset")
    return _redirect(request)


async def set_language(request: Request) -> Response:
    """Language links in the footer: remember the choice in a cookie."""
    if (denied := _guard(request)) is not None:
        return denied
    response = _redirect(request)
    lang = i18n.supported(request.query_params.get("l"))
    if lang:
        base = request.headers.get("x-ingress-path", "") or "/"
        response.set_cookie(LANG_COOKIE, lang, max_age=365 * 86400, path=base, httponly=True, samesite="strict")
    return response


def _report_key_ok(request: Request) -> bool:
    """nginx adds the key – only it knows it, so neither an MCP server inside
    the container nor anything else can fake a report or a stand-in answer."""
    services = globals().get("SERVICES")
    key = request.headers.get("x-report-key", "")
    return bool(services is not None and services.report_secret) and secrets.compare_digest(
        key.encode(), services.report_secret.encode()
    )


async def report(request: Request) -> Response:
    """Status report of the helper integration, forwarded by nginx."""
    remote = globals().get("REMOTE")
    if remote is None or not remote.enabled or not _report_key_ok(request):
        return Response("Forbidden", status_code=403)
    body = await request.body()
    if len(body) > 4096:
        return Response("Too large", status_code=413)
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return Response("Bad request", status_code=400)
    if not isinstance(data, dict):
        return Response("Bad request", status_code=400)
    answer = await anyio.to_thread.run_sync(remote.receive_report, data)
    return JSONResponse(answer)


NOT_READY_TEXT = {
    "logged_out": (
        "Garmin Connect is not connected: this Garmin account is not logged in in the Home "
        "Assistant app 'Garmin Connect MCP'. Ask the user to open 'Garmin MCP' in the Home "
        "Assistant sidebar and log in to Garmin Connect, then try again."
    ),
    "failed": (
        "The Garmin Connect login of this account in the Home Assistant app 'Garmin Connect MCP' "
        "is no longer valid. Ask the user to open 'Garmin MCP' in the Home Assistant sidebar and "
        "log in to Garmin Connect again."
    ),
    "starting": "The Garmin Connect MCP server is starting. Try again in a minute.",
    "off": (
        "The Garmin Connect MCP server of this Garmin account is switched off in Home Assistant. "
        "Ask the user to turn on its switch ('Garmin Connect MCP … Server') in Home Assistant, then "
        "try again."
    ),
}


def not_ready_answer(message: dict, reason: str) -> dict | None:
    """MCP answer of the stand-in server for one JSON-RPC message (None = no answer)."""
    if not isinstance(message, dict) or "id" not in message:
        return None  # notification
    text = NOT_READY_TEXT[reason]
    method = message.get("method")
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        result = {
            "protocolVersion": str(params.get("protocolVersion") or "2025-06-18"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "Garmin Connect MCP (not ready)", "version": os.environ.get("APP_VERSION", "dev")},
            "instructions": text,
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "garmin_connection_status",
                    "description": "Explains why the Garmin Connect tools are not available right now. " + text,
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": text}], "isError": True}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": text}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


async def mcp_unavailable(request: Request) -> Response:
    """Stand-in MCP endpoint while an account's Garmin server is not running (via nginx only)."""
    if not _report_key_ok(request):
        return Response("Forbidden", status_code=403)
    account = SERVICES.accounts.get(str(request.path_params.get("account", "")))
    if request.method != "POST":
        return Response(status_code=405, headers={"Allow": "POST"})
    body = await request.body()
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    status_now = await anyio.to_thread.run_sync(account.login_status) if account else "logged_out"
    reason = status_now if status_now in NOT_READY_TEXT else "starting"
    if isinstance(data, list):
        answers = [a for a in (not_ready_answer(m, reason) for m in data[:50]) if a is not None]
        return JSONResponse(answers) if answers else Response(status_code=202)
    answer = not_ready_answer(data, reason)
    return JSONResponse(answer) if answer is not None else Response(status_code=202)


async def status(request: Request) -> Response:
    if (denied := _guard(request, allow_local=True)) is not None:
        return denied
    state = await anyio.to_thread.run_sync(page_status)
    return JSONResponse(
        {
            "state": state,
            "remote": REMOTE.state if globals().get("REMOTE") is not None else "",
            "accounts": [
                {"id": a.id, "logged_in": a.has_tokens(), "switched_off": a.switched_off, "tools": len(a.active_tools)}
                for a in SERVICES.accounts.values()
            ],
        }
    )


SECURITY_HEADERS = {
    # The page shows secrets (connector URL): never cache it, never leak it
    # via the Referer header, only allow Home Assistant to frame it.
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "frame-ancestors 'self'; base-uri 'none'; form-action 'self'; object-src 'none'",
}


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                for key, value in SECURITY_HEADERS.items():
                    if key.lower().encode() not in present:
                        headers.append((key.lower().encode(), value.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/login", do_login, methods=["POST"]),
        Route("/mfa", do_mfa, methods=["POST"]),
        Route("/cancel", do_cancel, methods=["POST"]),
        Route("/logout", do_logout, methods=["POST"]),
        Route("/rotate", do_rotate, methods=["POST"]),
        Route("/test", do_test, methods=["POST"]),
        Route("/status.json", status),
        Route("/lang", set_language),
        Route("/report", report, methods=["POST"]),
        Route("/mcp-unavailable/{account}", mcp_unavailable, methods=["GET", "POST"]),
        Route("/accounts/add", add_account, methods=["POST"]),
        Route("/accounts/remove", remove_account, methods=["POST"]),
        Route("/accounts/rename", rename_account, methods=["POST"]),
        Route("/accounts/settings", account_settings, methods=["POST"]),
        Route("/settings/shared", shared_settings, methods=["POST"]),
        Route("/tools", tools_page),
        Route("/tools", save_tools, methods=["POST"]),
        Route("/tools/reset", reset_tools, methods=["POST"]),
    ],
    middleware=[Middleware(SecurityHeaders)],
)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    global SERVICES
    options = load_options()
    level = getattr(logging, str(options.get("log_level", "info")).upper(), logging.INFO)
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    DATA.mkdir(parents=True, exist_ok=True)

    if _UNCLASSIFIED:
        log.warning(
            "Tools without access classification (treated as change/delete): %s",
            ", ".join(_UNCLASSIFIED),
        )
    SERVICES = Services()
    SERVICES.start_nginx()
    SERVICES.start_all()
    threading.Thread(target=SERVICES.supervise, name="supervisor", daemon=True).start()
    global REMOTE
    REMOTE = RemoteAccess(SERVICES)
    threading.Thread(target=REMOTE.run, name="remote-access", daemon=True).start()

    def _stop(*_args):
        SERVICES.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=UI_PORT,
            log_level="warning",
            access_log=False,
            proxy_headers=False,
        )
    finally:
        SERVICES.shutdown()


if __name__ == "__main__":
    main()
