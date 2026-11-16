"""Garmin Connect MCP – Home Assistant add-on launcher.

Runs three things inside the add-on container:

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

import tool_texts

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------
DATA = Path(os.environ.get("ADDON_DATA_DIR", "/data"))
OPTIONS_FILE = DATA / "options.json"
TOKEN_DIR = DATA / "garmin_tokens"
SECRET_FILE = DATA / "secret_path"
ACCOUNT_FILE = DATA / "account.json"
DOWNLOAD_DIR = DATA / "downloads"
NGINX_CONF = Path("/tmp/garmin-mcp-nginx.conf")
NGINX_PROXY_CONF = Path("/tmp/garmin-mcp-proxy.conf")

MCP_PORT = 8000          # upstream server, loopback only
PUBLIC_PORT = 8100       # nginx, reached by tunnel / reverse proxy
UI_PORT = 8099           # Home Assistant ingress
INGRESS_PROXY_IP = "172.30.32.2"
ALLOW_ANY_UI_CLIENT = os.environ.get("ALLOW_ANY_UI_CLIENT") == "1"  # tests only

# Remote access through a Home Assistant webhook (default)
HA_CONFIG = Path(os.environ.get("HA_CONFIG_DIR", "/homeassistant"))
COMPONENT_SRC = Path(__file__).resolve().parent / "integration" / "garmin_mcp_webhook"
COMPONENT_DST = HA_CONFIG / "custom_components" / "garmin_mcp_webhook"
WEBHOOK_CONFIG = HA_CONFIG / ".garmin_mcp_webhook.json"
WEBHOOK_ID_FILE = DATA / "webhook_id"
WEBHOOK_DOMAIN = "garmin_mcp_webhook"

log = logging.getLogger("garmin_mcp_addon")
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
            mod.register_tools(_Collector(module if module in tool_texts.CATEGORIES else "other"))
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


def load_selection() -> tuple[set[str], set[str]] | None:
    """(picked tools, tools that existed when the user saved) or None if the
    user never saved a selection on the add-on page."""
    try:
        data = json.loads(SELECTION_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if isinstance(data, list):  # format of 0.2.x
        return {str(n) for n in data} & ALL_TOOLS, set()
    picked = {str(n) for n in data.get("enabled", [])} & ALL_TOOLS
    known = {str(n) for n in data.get("known", [])}
    return picked, known


def save_selection(picked: set[str]) -> None:
    write_private(
        SELECTION_FILE,
        json.dumps({"enabled": sorted(picked & ALL_TOOLS), "known": sorted(ALL_TOOLS)}),
    )


def new_tools() -> list[str]:
    """Tools added (by an update) since the user saved their selection."""
    sel = load_selection()
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


def prune_downloads(days: int, now: float | None = None) -> int:
    """Delete downloaded files older than `days` (0 = keep everything).

    Downloads are only a hand-over to the AI; keeping them forever would fill
    the disk and every Home Assistant backup."""
    if days <= 0 or not DOWNLOAD_DIR.is_dir():
        return 0
    limit = (now or time.time()) - days * 86400
    removed = 0
    # os.walk never follows symlinks; a link is removed itself, not its target.
    for root, dirs, files in os.walk(DOWNLOAD_DIR, topdown=False, followlinks=False):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            path = Path(root, name)
            try:
                if path.lstat().st_mtime < limit:
                    path.unlink()
                    removed += 1
            except OSError as exc:
                log.debug("Could not remove %s: %s", path, exc)
        if Path(root) != DOWNLOAD_DIR:
            try:
                Path(root).rmdir()  # only succeeds when empty
            except OSError:
                pass
    if removed:
        log.info("Removed %d downloaded file(s) older than %d days", removed, days)
    return removed


def _names(values) -> set[str]:
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def tool_selection(options: dict) -> tuple[dict, set[str]]:
    """Return (environment for garmin-mcp, set of tools that will be active)."""
    sel = load_selection()
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


def get_secret(rotate: bool = False) -> str:
    if not rotate and SECRET_FILE.exists():
        value = SECRET_FILE.read_text().strip()
        if len(value) >= 24:
            return value
    value = secrets.token_urlsafe(32)
    write_private(SECRET_FILE, value)
    log.info("Generated a new secret path")
    return value


def get_webhook_id(rotate: bool = False) -> str:
    if not rotate and WEBHOOK_ID_FILE.exists():
        value = WEBHOOK_ID_FILE.read_text().strip()
        if len(value) >= 24:
            return value
    value = "garmin_mcp_" + secrets.token_urlsafe(32)
    write_private(WEBHOOK_ID_FILE, value)
    return value


def has_tokens() -> bool:
    return (TOKEN_DIR / "garmin_tokens.json").is_file()


def read_account() -> dict:
    try:
        return json.loads(ACCOUNT_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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
error_log /dev/stderr crit;
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

        location = /{secret}/mcp {{
            include /tmp/garmin-mcp-proxy.conf;
        }}
        location = /{secret}/mcp/ {{
            include /tmp/garmin-mcp-proxy.conf;
        }}
        location @unavailable {{
            default_type application/json;
            return 503 '{{"error":"Garmin MCP is not ready. Open the Garmin MCP app page in Home Assistant and log in to Garmin Connect."}}';
        }}
        location / {{
            return 404;
        }}
    }}
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
error_page 502 503 504 = @unavailable;
"""


class Services:
    """Starts, stops and supervises nginx and the garmin-mcp server."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.mcp: subprocess.Popen | None = None
        self.nginx: subprocess.Popen | None = None
        self.stopping = False
        self.options = load_options()
        self.mcp_env, self.active_tools = tool_selection(self.options)
        self.secret = get_secret()
        self._mcp_failures = 0
        self._login_alert = False
        self._login_failures = 0
        self._next_login_retry = 0.0

    # nginx ---------------------------------------------------------------
    def write_nginx_conf(self) -> None:
        NGINX_PROXY_CONF.write_text(NGINX_PROXY.format(mcp_port=MCP_PORT))
        NGINX_CONF.write_text(
            NGINX_TEMPLATE.format(
                public_port=PUBLIC_PORT, mcp_port=MCP_PORT, secret=self.secret
            )
        )
        os.chmod(NGINX_CONF, 0o600)

    def start_nginx(self) -> None:
        self.write_nginx_conf()
        self.nginx = subprocess.Popen(
            ["nginx", "-c", str(NGINX_CONF), "-g", "daemon off;"]
        )
        log.info("nginx listening on port %s", PUBLIC_PORT)

    def rotate_secret(self) -> None:
        with self.lock:
            self.secret = get_secret(rotate=True)
            self.write_nginx_conf()
            subprocess.run(["nginx", "-c", str(NGINX_CONF), "-s", "reload"], check=False)

    # garmin-mcp ----------------------------------------------------------
    def start_mcp(self) -> None:
        with self.lock:
            if self.mcp and self.mcp.poll() is None:
                return
            if not has_tokens():
                log.info("Not logged in to Garmin Connect yet – open the app page to log in")
                return
            DOWNLOAD_DIR.mkdir(exist_ok=True)
            env = dict(os.environ)
            env.update(self.mcp_env)
            env.update(
                {
                    "GARMIN_MCP_TRANSPORT": "streamable-http",
                    "GARMIN_MCP_HOST": "127.0.0.1",
                    "GARMIN_MCP_PORT": str(MCP_PORT),
                    "GARMIN_MCP_STATELESS_HTTP": "true",
                    "GARMINTOKENS": str(TOKEN_DIR),
                    "GARMINTOKENS_BASE64": str(DATA / "garmin_tokens.b64"),
                    "GARMIN_FIT_DOWNLOAD_DIR": str(DOWNLOAD_DIR),
                    "HOME": str(DATA),
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
            level = str(self.options.get("log_level", "info")).lower()
            env["GARMIN_ADDON_LOG_LEVEL"] = "DEBUG" if level == "debug" else "WARNING"
            run_mcp = Path(__file__).resolve().parent / "run_mcp.py"
            self.mcp = subprocess.Popen([sys.executable, str(run_mcp)], env=env, cwd=str(DOWNLOAD_DIR))
            log.info(
                "garmin-mcp started (%d tools active, write access: %s)",
                len(self.active_tools),
                self.options.get("write_access"),
            )

    def stop_mcp(self) -> None:
        with self.lock:
            proc, self.mcp = self.mcp, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def restart_mcp(self) -> None:
        self.stop_mcp()
        self._mcp_failures = 0
        self.start_mcp()

    def reset_login_state(self) -> None:
        """After a fresh login: forget earlier failures and alerts."""
        self._login_failures = 0
        self._next_login_retry = 0.0

    def reload_tools(self) -> None:
        self.mcp_env, self.active_tools = tool_selection(self.options)
        self.restart_mcp()

    def mcp_state(self) -> str:
        """'stopped', 'pending', 'ready' or 'failed'."""
        if not self.mcp or self.mcp.poll() is not None:
            return "stopped"
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{MCP_PORT}/readyz", timeout=2
            ) as resp:
                return json.loads(resp.read()).get("status", "ready")
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read()).get("status", "failed")
            except Exception:  # noqa: BLE001
                return "failed"
        except Exception:  # noqa: BLE001 - not listening yet
            return "pending"

    # supervision ---------------------------------------------------------
    def _check_login(self) -> None:
        """Tell the user in Home Assistant when the Garmin login stops working."""
        state = self.mcp_state() if has_tokens() else "stopped"
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
                "Garmin login failed (attempt %d) – restarting the server, next try in %d min",
                self._login_failures,
                pause // 60,
            )
            self.restart_mcp()
        notify = bool(self.options.get("login_notification", True))
        if notify and state == "failed" and self._login_failures >= 2 and not self._login_alert:
            log.warning("Garmin login failed – asking the user to log in again")
            core_api(
                "POST",
                "/services/persistent_notification/create",
                {
                    "notification_id": "garmin_mcp_login",
                    "title": "Garmin Connect MCP",
                    "message": (
                        "The Garmin Connect login is no longer valid – the AI cannot read your "
                        "Garmin data. Open **Garmin MCP** in the sidebar and log in again. / "
                        "Die Anmeldung bei Garmin Connect ist nicht mehr gültig – die KI kann "
                        "nicht auf deine Garmin-Daten zugreifen. Öffne **Garmin MCP** in der "
                        "Seitenleiste und melde dich neu an."
                    ),
                },
                quiet=True,
            )
            self._login_alert = True
        elif state == "ready" and self._login_alert:
            core_api(
                "POST",
                "/services/persistent_notification/dismiss",
                {"notification_id": "garmin_mcp_login"},
                quiet=True,
            )
            self._login_alert = False

    def supervise(self) -> None:
        ticks = 0
        while not self.stopping:
            time.sleep(5)
            ticks += 1
            if ticks % 12 == 0:  # once a minute
                try:
                    expire_pending_mfa()
                    self._check_login()
                except Exception as exc:  # noqa: BLE001
                    log.debug("Login check failed: %s", exc)
            if ticks % 720 == 1:  # at start, then once an hour
                try:
                    prune_downloads(keep_days(self.options))
                except Exception as exc:  # noqa: BLE001
                    log.debug("Download cleanup failed: %s", exc)
            with self.lock:
                if self.stopping:
                    return
                if self.nginx and self.nginx.poll() is not None:
                    log.error("nginx exited (%s), restarting", self.nginx.returncode)
                    self.start_nginx()
                if self.mcp and self.mcp.poll() is not None:
                    self._mcp_failures += 1
                    delay = min(60, 5 * self._mcp_failures)
                    log.error(
                        "garmin-mcp exited (%s), restarting in %ss",
                        self.mcp.returncode,
                        delay,
                    )
                    self.mcp = None
                else:
                    delay = 0
            if delay:
                time.sleep(delay)
                self.start_mcp()

    def shutdown(self) -> None:
        self.stopping = True
        self.stop_mcp()
        if self.nginx and self.nginx.poll() is None:
            self.nginx.terminate()


# --------------------------------------------------------------------------
# Home Assistant Core API (via Supervisor) and webhook remote access
# --------------------------------------------------------------------------
def core_api(method: str, path: str, data: dict | None = None, quiet: bool = False):
    """Call the Home Assistant REST API through the Supervisor proxy."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        f"http://supervisor/core/api{path}",
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            log.debug("HA API %s %s failed: %s", method, path, exc)
        return None


def _own_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return socket.gethostname()


class RemoteAccess:
    """Keeps the webhook integration installed, configured and loaded.

    States: disabled (direct mode), setting_up, restart_needed, active, error.
    """

    def __init__(self, services: "Services") -> None:
        self.services = services
        self.enabled = services.options.get("remote_access", "webhook") == "webhook"
        self.state = "setting_up" if self.enabled else "disabled"
        self.detail = ""
        self.webhook_id = get_webhook_id()
        self._wake = threading.Event()
        self._config_changed = True
        self._base_url_cache: tuple[float, str] = (0.0, "")
        # Set when the integration code was updated while HA already had it
        # loaded: Python modules only reload with a Home Assistant restart.
        self.pending_restart = False
        self._saw_ha_down = False
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

    def _write_config(self) -> None:
        target = f"http://{_own_ip()}:{PUBLIC_PORT}/{self.services.secret}/mcp"
        content = json.dumps({"webhook_id": self.webhook_id, "target_url": target})
        try:
            if WEBHOOK_CONFIG.read_text() == content:
                return
        except OSError:
            pass
        write_private(WEBHOOK_CONFIG, content)
        self._config_changed = True

    # HA config entry -----------------------------------------------------
    def _entry(self):
        entries = core_api("GET", f"/config/config_entries/entry?domain={WEBHOOK_DOMAIN}", quiet=True)
        if entries is None:
            return None, False
        for entry in entries if isinstance(entries, list) else []:
            if entry.get("domain") == WEBHOOK_DOMAIN:
                return entry, True
        return None, True

    def _create_entry(self) -> bool:
        flow = core_api("POST", "/config/config_entries/flow", {"handler": WEBHOOK_DOMAIN}, quiet=True)
        return isinstance(flow, dict) and flow.get("type") in ("create_entry", "abort")

    def _notify_restart(self) -> None:
        core_api(
            "POST",
            "/services/persistent_notification/create",
            {
                "notification_id": "garmin_mcp_restart",
                "title": "Garmin Connect MCP",
                "message": (
                    "Please restart Home Assistant once to activate remote access "
                    "for the Garmin Connect MCP app. / Bitte Home Assistant einmal "
                    "neu starten, um den Fernzugriff für die App Garmin Connect MCP "
                    "zu aktivieren."
                ),
            },
        )

    def _dismiss_notification(self) -> None:
        core_api(
            "POST",
            "/services/persistent_notification/dismiss",
            {"notification_id": "garmin_mcp_restart"},
            quiet=True,
        )

    # loop ----------------------------------------------------------------
    def _cleanup(self) -> None:
        """Direct mode: remove the helper integration if an earlier start installed it."""
        if not (COMPONENT_DST.exists() or WEBHOOK_CONFIG.exists()):
            return
        log.info("Remote access is set to direct – removing the helper integration")
        for _ in range(10):
            entry, api_ok = self._entry()
            if api_ok:
                break
            time.sleep(10)
        if entry:
            core_api("DELETE", f"/config/config_entries/entry/{entry['entry_id']}")
        WEBHOOK_CONFIG.unlink(missing_ok=True)
        shutil.rmtree(COMPONENT_DST, ignore_errors=True)
        self._dismiss_notification()
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
            self.state, self.detail = "error", "no access to the Home Assistant config folder"
            log.error("Remote access: %s", self.detail)
            return
        try:
            was_installed = (COMPONENT_DST / "manifest.json").exists()
            if self._install_component() and was_installed:
                self.pending_restart = True
        except OSError as exc:
            self.state, self.detail = "error", str(exc)
            log.error("Remote access: could not install integration: %s", exc)
            return
        while not self.services.stopping:
            try:
                self._sync()
            except Exception as exc:  # noqa: BLE001
                log.warning("Remote access: %s", exc)
            self._wake.wait(30 if self.state != "active" else 300)
            self._wake.clear()

    def _sync(self) -> None:
        self._write_config()
        entry, api_ok = self._entry()
        if not api_ok:
            self._saw_ha_down = True
            self.state, self.detail = "setting_up", "Home Assistant API not reachable"
            return
        if self.pending_restart:
            if self._saw_ha_down:
                self.pending_restart = False
                self._config_changed = True
            else:
                if self.state != "restart_needed":
                    log.info("Remote access: integration updated – Home Assistant must be restarted once")
                    self._notify_restart()
                self.state = "restart_needed"
                return
        if entry is None:
            if self._create_entry():
                log.info("Remote access: integration set up")
                entry, _ = self._entry()
                self._config_changed = False
            else:
                if self.state != "restart_needed":
                    log.info("Remote access: Home Assistant must be restarted once")
                    self._notify_restart()
                self.state = "restart_needed"
                return
        if entry and entry.get("state") == "loaded" and self._config_changed:
            core_api("POST", f"/config/config_entries/entry/{entry['entry_id']}/reload")
            self._config_changed = False
            entry, _ = self._entry()
        if entry and entry.get("state") == "loaded":
            if self.state != "active":
                log.info("Remote access active")
                self._dismiss_notification()
            self.state = "active"
        elif entry and entry.get("state") in ("setup_retry", "not_loaded"):
            core_api("POST", f"/config/config_entries/entry/{entry['entry_id']}/reload")
            self.state = "setting_up"
        else:
            self.state = "error"
            self.detail = f"integration state: {entry.get('state') if entry else 'missing'}"

    def rotate(self) -> None:
        self.webhook_id = get_webhook_id(rotate=True)
        self._config_changed = True
        self._wake.set()

    def nudge(self) -> None:
        self._config_changed = True
        self._wake.set()

    def base_url(self) -> str:
        """Public base URL: option > HA external URL > Nabu Casa remote UI."""
        configured, _ = normalize_public_url(self.services.options.get("public_url"))
        if configured:
            return configured
        cached_at, cached = self._base_url_cache
        if time.time() - cached_at < 300:
            return cached
        url = ""
        cfg = core_api("GET", "/config", quiet=True)
        if isinstance(cfg, dict) and cfg.get("external_url"):
            url = str(cfg["external_url"]).rstrip("/")
        if not url:
            cloud = core_api("GET", "/cloud/status", quiet=True)
            if isinstance(cloud, dict) and cloud.get("remote_domain") and cloud.get("remote_enabled", True):
                url = f"https://{cloud['remote_domain']}"
        self._base_url_cache = (time.time(), url)
        return url

    def restart_home_assistant(self) -> None:
        core_api("POST", "/services/homeassistant/restart", {})


# --------------------------------------------------------------------------
# Connection test
# --------------------------------------------------------------------------
TEST_RESULT: dict = {}


def _mcp_request(url: str, payload: dict, host_header: str | None = None, timeout: int = 20):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if host_header:
        headers["Host"] = host_header
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    return json.loads(lines[0] if lines else raw)


def run_connection_test() -> dict:
    """Check server, Garmin account and the public connector URL, one by one."""
    result: dict = {"time": time.strftime("%H:%M:%S"), "checks": []}

    def add(key: str, ok: bool, detail: str = "") -> None:
        result["checks"].append({"key": key, "ok": ok, "detail": detail})

    # 1. MCP server answers locally
    try:
        data = _mcp_request(
            f"http://127.0.0.1:{MCP_PORT}/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            host_header=f"127.0.0.1:{MCP_PORT}",
        )
        add("test_server", True, str(len(data["result"]["tools"])))
    except Exception as exc:  # noqa: BLE001
        add("test_server", False, type(exc).__name__)

    # 2. Garmin account reachable with the saved tokens
    if not has_tokens():
        add("test_garmin", False, "@not_logged_in")
    else:
        try:
            client = Garmin()
            client.login(str(TOKEN_DIR))
            add("test_garmin", True, client.full_name or client.display_name or "")
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if isinstance(exc, GarminConnectAuthenticationError) or "password" in text.lower() or "401" in text:
                add("test_garmin", False, "@relogin")
            else:
                add("test_garmin", False, text[:160])

    # 3. The connector URL works from the internet (round trip via your
    #    public address, exactly like the AI app reaches it)
    if REMOTE.enabled:
        base = REMOTE.base_url()
        url = f"{base}/api/webhook/{REMOTE.webhook_id}" if base else ""
    else:
        public, _ = normalize_public_url(SERVICES.options.get("public_url"))
        url = f"{public}/{SERVICES.secret}/mcp" if public else ""
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
                        "clientInfo": {"name": "garmin-mcp-addon-selftest", "version": "1"},
                    },
                },
            )
            add("test_public", "result" in data, data.get("result", {}).get("serverInfo", {}).get("name", ""))
        except urllib.error.HTTPError as exc:
            add("test_public", False, f"HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001
            add("test_public", False, type(exc).__name__)
    result["ok"] = all(c["ok"] for c in result["checks"])
    return result


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


PENDING_MFA: dict = {}
LOGIN_ATTEMPTS: list[float] = []
MAX_LOGINS = 5            # per LOGIN_WINDOW – protects your Garmin account from a lockout
LOGIN_WINDOW = 15 * 60


def _throttle_login() -> None:
    now = time.time()
    LOGIN_ATTEMPTS[:] = [t for t in LOGIN_ATTEMPTS if now - t < LOGIN_WINDOW]
    if len(LOGIN_ATTEMPTS) >= MAX_LOGINS:
        raise LoginError("err_too_many_attempts")
    LOGIN_ATTEMPTS.append(now)


def expire_pending_mfa() -> None:
    """Drop a half-finished MFA login (it holds the password in memory)."""
    if PENDING_MFA and time.time() - PENDING_MFA.get("started", 0) > MFA_TIMEOUT:
        PENDING_MFA.clear()
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


def _finish_login(garmin: Garmin) -> str:
    """Store tokens, verify them and remember the account name."""
    tmp = DATA / "garmin_tokens.new"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(mode=0o700)
    garmin.client.dump(str(tmp))
    verify = Garmin()
    verify.login(str(tmp))
    name = verify.full_name or verify.display_name or ""
    shutil.rmtree(TOKEN_DIR, ignore_errors=True)
    tmp.rename(TOKEN_DIR)
    secure_dir(TOKEN_DIR)
    write_private(ACCOUNT_FILE, json.dumps({"name": name, "since": int(time.time())}))
    log.info("Logged in to Garmin Connect")
    SERVICES.reset_login_state()
    SERVICES.restart_mcp()
    return name


def start_login(email: str, password: str) -> str:
    """Returns 'done' or 'mfa'. Raises LoginError."""
    with LOGIN_LOCK:
        if has_tokens():
            # A second click while the first login was still running – don't
            # log in again (Garmin rate-limits repeated logins).
            return "done"
        PENDING_MFA.clear()
        _throttle_login()
        try:
            garmin = Garmin(email=email, password=password, return_on_mfa=True)
            result, _state = garmin.client.login(email, password, return_on_mfa=True)
            if result == "needs_mfa":
                PENDING_MFA.update(
                    {"garmin": garmin, "state": _state, "started": time.time()}
                )
                return "mfa"
            _finish_login(garmin)
            return "done"
        except LoginError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Garmin login failed: %s", type(exc).__name__)
            raise _translate_login_error(exc) from exc


def finish_mfa(code: str) -> None:
    with LOGIN_LOCK:
        if not PENDING_MFA or time.time() - PENDING_MFA["started"] > MFA_TIMEOUT:
            PENDING_MFA.clear()
            raise LoginError("err_mfa_expired")
        garmin, state = PENDING_MFA["garmin"], PENDING_MFA["state"]
        try:
            garmin.resume_login(state, code.strip())
            _finish_login(garmin)
        except Exception as exc:  # noqa: BLE001
            log.warning("Garmin MFA failed: %s", type(exc).__name__)
            raise _translate_login_error(exc) from exc
        finally:
            PENDING_MFA.clear()


def logout() -> None:
    SERVICES.stop_mcp()
    shutil.rmtree(TOKEN_DIR, ignore_errors=True)
    for path in (ACCOUNT_FILE, DATA / "garmin_tokens.b64"):
        path.unlink(missing_ok=True)
    log.info("Logged out of Garmin Connect, tokens deleted")


# --------------------------------------------------------------------------
# Web UI (Home Assistant ingress)
# --------------------------------------------------------------------------
TEXT = {
    "en": {
        "title": "Garmin Connect MCP",
        "account": "Garmin account",
        "connected_as": "Connected as",
        "not_connected": "Not connected yet. Log in once – your password is not stored, only the access tokens Garmin issues (valid for about six months). Two-factor authentication is supported: if it is enabled, you will be asked for the code.",
        "email": "E-mail",
        "password": "Password",
        "login": "Log in",
        "logout": "Log out and delete tokens",
        "logout_confirm": "Log out and delete the stored Garmin tokens?",
        "mfa_title": "Two-factor authentication",
        "mfa_hint": "Garmin has sent you a security code. Enter it here.",
        "mfa_code": "Code",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "server": "Server",
        "state": "Status",
        "state_ready": "Ready",
        "state_pending": "Starting …",
        "state_failed": "Garmin login failed – please log in again",
        "state_stopped": "Stopped (not logged in)",
        "tools": "Active tools",
        "write_access": "Write access",
        "wa_read_only": "read only",
        "wa_create_only": "create, but never delete or overwrite",
        "wa_full": "full (incl. delete and edit)",
        "options_hint": "",
        "connection": "Connect your AI assistant",
        "connector_url": "Connector URL",
        "show": "Show",
        "hide": "Hide",
        "copy": "Copy",
        "copied": "Copied",
        "no_public_url": "Set “Public address” in the configuration to see the full address. Until then, replace the domain placeholder.",
        "internal_url": "Target for your tunnel / reverse proxy",
        "internal_hint": "Point a public HTTPS hostname (e.g. in the Cloudflared app) at this address. Never publish port 8100 without HTTPS.",
        "secret_warning": "Anyone who knows this URL can use your Garmin account through the AI tools. Treat it like a password.",
        "rotate": "Generate new secret URL",
        "rotate_confirm": "Generate a new secret URL? The old one stops working immediately and you must update your connectors.",
        "steps": "Add it in your AI app as a custom connector / remote MCP server (no authentication). Details: see the Documentation tab.",
        "err_credentials": "Wrong e-mail or password.",
        "err_mfa": "The security code was wrong or has expired.",
        "err_mfa_expired": "The login took too long. Please start again.",
        "err_rate_limit": "Garmin is rate-limiting logins. Please wait a few minutes and try again.",
        "err_connection": "Garmin Connect could not be reached or rejected the login.",
        "err_unknown": "Login failed.",
        "err_csrf": "The page was outdated. Please try again.",
        "err_too_many_attempts": "Too many login attempts. Please wait 15 minutes – this protects your Garmin account from being locked.",
        "ok_login": "Logged in successfully.",
        "ok_logout": "Logged out. Tokens deleted.",
        "ok_rotate": "New secret URL generated. Update your connectors.",
        "ok_restart": "Home Assistant is restarting. Reload this page in a minute.",
        "upload_hint": "To let the AI create workouts on your watch, Garmin needs your consent to data uploads (required for EU accounts): Garmin Connect → Settings → Privacy settings → Data → “Upload device data” must be on. If your watch already syncs to Garmin Connect, this is usually already the case.",
        "oauth_hint": "If you also use the ha-mcp app with its webhook proxy, your AI app may ask you to log in to your Home Assistant and grant access when adding the connector. That comes from ha-mcp and is harmless – just confirm it.",
        "login_busy": "Please wait …",
        "login_wait": "Logging in to Garmin – this can take up to 30 seconds. Please don't click again.",
        "restart_banner_title": "Restart of Home Assistant required",
        "restart_busy": "Restarting …",
        "custom_selection": "custom selection (app page)",
        "what_ai_may": "What the AI may do",
        "nothing": "nothing",
        "kind_read": "read",
        "kind_create": "create",
        "kind_change": "change/delete",
        "choose_tools": "Choose tools",
        "open_config": "Open configuration",
        "tools_title": "Choose tools",
        "back": "← Back",
        "search": "Search tools …",
        "selected": "selected",
        "preset": "Presets:",
        "preset_read": "Read only",
        "preset_create": "Create, never delete (recommended)",
        "preset_all": "Everything",
        "preset_none": "Nothing",
        "save": "Save and restart server",
        "reset": "Reset to configuration",
        "reset_confirm": "Discard your selection and use the areas and write access from the configuration again?",
        "tools_intro": "Tick what the AI may use. ⓘ explains each tool. Saving restarts the server; afterwards your AI app may need a moment to see the new tool list.",
        "info_name": "Technical name",
        "info_kind": "Access",
        "info_kind_read": "Only reads data from Garmin Connect.",
        "info_kind_create": "Adds something new to Garmin Connect (e.g. a workout or an entry), never deletes or overwrites.",
        "info_kind_change": "Changes, overwrites or deletes existing data – or saves files. Allow deliberately.",
        "info_original": "Original description",
        "ok_tools": "Selection saved. The server is restarting.",
        "ok_tools_reset": "Selection reset – the configuration applies again.",
        "cleaned_up": "Remote access is set to “direct”: the helper integration for the webhook was removed from Home Assistant. No restart needed.",
        "new_tools_hint": "{n} new tools since you saved your selection – they are switched off.",
        "unknown_tools": "These tool names in the configuration do not exist and are ignored (typo?):",
        "public_url_http": "The public address uses http://. Most AI apps only accept https:// connectors.",
        "public_url_invalid": "The “Public address” in the configuration is not a valid web address and is ignored. Example: https://home.example.com",
        "new_tools_banner": "An update added {n} new tools (marked “new”). They stay switched off until you tick them and save.",
        "new": "new",
        "review": "Review",
        "docs": "Documentation",
        "test_title": "Connection test",
        "test_intro": "Checks the server, your Garmin login and the connector URL from the internet – exactly the way your AI app reaches it.",
        "test_run": "Test connection",
        "test_busy": "Testing … (up to 30 s)",
        "test_ok": "Everything works.",
        "test_failed": "Something is not working:",
        "test_server": "MCP server answers (tools)",
        "test_garmin": "Garmin account reachable",
        "test_public": "Connector URL reachable from the internet",
        "detail_not_logged_in": "not logged in – log in above",
        "detail_relogin": "login no longer valid – log out and log in again",
        "detail_no_public": "public address unknown – set “Public base URL” in the configuration",
        "remote": "Remote access",
        "remote_active": "Active – via your Home Assistant address",
        "remote_setting_up": "Setting up …",
        "remote_restart_needed": "Home Assistant must be restarted once",
        "remote_error": "Error",
        "remote_disabled": "Off",
        "restart_hint": "The app has installed or updated its small helper integration for remote access. Home Assistant loads it only after a restart – until then the connector cannot work. Logging in to Garmin already works.",
        "restart_ha": "Restart Home Assistant now",
        "restart_confirm": "Restart Home Assistant now? It will be unavailable for about a minute.",
        "no_base_url": "Home Assistant has no external URL configured. Set it under Settings → System → Network, or enter it as “Public address” in the app configuration – until then, replace the placeholder.",
    },
    "de": {
        "title": "Garmin Connect MCP",
        "account": "Garmin-Konto",
        "connected_as": "Verbunden als",
        "not_connected": "Noch nicht verbunden. Melde dich einmal an – dein Passwort wird nicht gespeichert, nur die Zugangstokens von Garmin (gültig ca. sechs Monate). Zwei-Faktor-Anmeldung wird unterstützt: Ist sie aktiv, wirst du nach dem Code gefragt.",
        "email": "E-Mail",
        "password": "Passwort",
        "login": "Anmelden",
        "logout": "Abmelden und Tokens löschen",
        "logout_confirm": "Abmelden und die gespeicherten Garmin-Tokens löschen?",
        "mfa_title": "Zwei-Faktor-Anmeldung",
        "mfa_hint": "Garmin hat dir einen Sicherheitscode geschickt. Gib ihn hier ein.",
        "mfa_code": "Code",
        "confirm": "Bestätigen",
        "cancel": "Abbrechen",
        "server": "Server",
        "state": "Status",
        "state_ready": "Bereit",
        "state_pending": "Startet …",
        "state_failed": "Garmin-Anmeldung fehlgeschlagen – bitte neu anmelden",
        "state_stopped": "Gestoppt (nicht angemeldet)",
        "tools": "Aktive Tools",
        "write_access": "Schreibrechte",
        "wa_read_only": "nur lesen",
        "wa_create_only": "anlegen, aber nie löschen oder überschreiben",
        "wa_full": "voll (inkl. Löschen und Bearbeiten)",
        "options_hint": "",
        "connection": "KI-Assistent verbinden",
        "connector_url": "Connector-URL",
        "show": "Anzeigen",
        "hide": "Verbergen",
        "copy": "Kopieren",
        "copied": "Kopiert",
        "no_public_url": "Trage in der Konfiguration die „Öffentliche Adresse“ ein, dann siehst du hier die vollständige URL. Bis dahin den Domain-Platzhalter ersetzen.",
        "internal_url": "Ziel für deinen Tunnel / Reverse Proxy",
        "internal_hint": "Leite einen öffentlichen HTTPS-Hostnamen (z. B. in der Cloudflared-App) auf diese Adresse. Port 8100 nie ohne HTTPS freigeben.",
        "secret_warning": "Wer diese URL kennt, kann über die KI-Tools auf dein Garmin-Konto zugreifen. Behandle sie wie ein Passwort.",
        "rotate": "Neue geheime URL erzeugen",
        "rotate_confirm": "Neue geheime URL erzeugen? Die alte funktioniert sofort nicht mehr und du musst deine Connectors anpassen.",
        "steps": "Trage sie in deiner KI-App als benutzerdefinierten Connector bzw. Remote-MCP-Server ein (ohne Authentifizierung). Details im Tab „Dokumentation“.",
        "err_credentials": "E-Mail oder Passwort falsch.",
        "err_mfa": "Der Sicherheitscode war falsch oder ist abgelaufen.",
        "err_mfa_expired": "Die Anmeldung hat zu lange gedauert. Bitte neu starten.",
        "err_rate_limit": "Garmin blockiert gerade zu viele Anmeldeversuche. Bitte ein paar Minuten warten.",
        "err_connection": "Garmin Connect war nicht erreichbar oder hat die Anmeldung abgelehnt.",
        "err_unknown": "Anmeldung fehlgeschlagen.",
        "err_csrf": "Die Seite war veraltet. Bitte nochmal versuchen.",
        "err_too_many_attempts": "Zu viele Anmeldeversuche. Bitte 15 Minuten warten – das schützt dein Garmin-Konto vor einer Sperre.",
        "ok_login": "Erfolgreich angemeldet.",
        "ok_logout": "Abgemeldet. Tokens gelöscht.",
        "ok_rotate": "Neue geheime URL erzeugt. Passe deine Connectors an.",
        "ok_restart": "Home Assistant startet neu. Lade diese Seite in einer Minute neu.",
        "upload_hint": "Damit die KI Workouts auf deine Uhr bringen kann, braucht Garmin deine Zustimmung zum Hochladen (Pflicht bei EU-Konten): Garmin Connect → Einstellungen → Datenschutzeinstellungen → Daten → „Gerätedaten hochladen“ muss aktiv sein. Synchronisiert deine Uhr schon mit Garmin Connect, ist das meist bereits der Fall.",
        "oauth_hint": "Nutzt du zusätzlich die App ha-mcp mit seinem Webhook-Proxy, fragt deine KI-App beim Hinzufügen des Connectors eventuell nach einer Anmeldung bei deinem Home Assistant und einer Zugriffsfreigabe. Das kommt von ha-mcp und ist unbedenklich – einfach bestätigen.",
        "login_busy": "Bitte warten …",
        "login_wait": "Anmeldung bei Garmin läuft – das kann bis zu 30 Sekunden dauern. Bitte nicht erneut klicken.",
        "restart_banner_title": "Neustart von Home Assistant erforderlich",
        "restart_busy": "Startet neu …",
        "custom_selection": "eigene Auswahl (App-Seite)",
        "what_ai_may": "Was die KI darf",
        "nothing": "nichts",
        "kind_read": "lesen",
        "kind_create": "anlegen",
        "kind_change": "ändern/löschen",
        "choose_tools": "Tools auswählen",
        "open_config": "Konfiguration öffnen",
        "tools_title": "Tools auswählen",
        "back": "← Zurück",
        "search": "Tools durchsuchen …",
        "selected": "ausgewählt",
        "preset": "Vorlagen:",
        "preset_read": "Nur lesen",
        "preset_create": "Anlegen, nie löschen (empfohlen)",
        "preset_all": "Alles",
        "preset_none": "Nichts",
        "save": "Speichern und Server neu starten",
        "reset": "Auf Konfiguration zurücksetzen",
        "reset_confirm": "Deine Auswahl verwerfen und wieder Bereiche und Schreibrechte aus der Konfiguration verwenden?",
        "tools_intro": "Hake an, was die KI nutzen darf. ⓘ erklärt jedes Tool. Beim Speichern startet der Server neu; deine KI-App braucht danach eventuell einen Moment, bis sie die neue Liste kennt.",
        "info_name": "Technischer Name",
        "info_kind": "Zugriff",
        "info_kind_read": "Liest nur Daten aus Garmin Connect.",
        "info_kind_create": "Legt etwas Neues in Garmin Connect an (z. B. ein Workout oder einen Eintrag), löscht oder überschreibt nie etwas.",
        "info_kind_change": "Ändert, überschreibt oder löscht vorhandene Daten – oder speichert Dateien. Bewusst freigeben.",
        "info_original": "Originalbeschreibung",
        "ok_tools": "Auswahl gespeichert. Der Server startet neu.",
        "ok_tools_reset": "Auswahl zurückgesetzt – es gilt wieder die Konfiguration.",
        "cleaned_up": "Fernzugriff steht auf „direct“: Die Hilfs-Integration für den Webhook wurde aus Home Assistant entfernt. Ein Neustart ist nicht nötig.",
        "new_tools_hint": "{n} neue Tools seit deiner gespeicherten Auswahl – sie sind ausgeschaltet.",
        "unknown_tools": "Diese Tool-Namen aus der Konfiguration gibt es nicht, sie werden ignoriert (Tippfehler?):",
        "public_url_http": "Die öffentliche Adresse beginnt mit http://. Die meisten KI-Apps akzeptieren nur https://-Connectoren.",
        "public_url_invalid": "Die „Öffentliche Adresse“ in der Konfiguration ist keine gültige Webadresse und wird ignoriert. Beispiel: https://home.example.com",
        "new_tools_banner": "Ein Update hat {n} neue Tools gebracht (markiert mit „neu“). Sie bleiben aus, bis du sie anhakst und speicherst.",
        "new": "neu",
        "review": "Ansehen",
        "docs": "Dokumentation",
        "test_title": "Verbindungstest",
        "test_intro": "Prüft den Server, deine Garmin-Anmeldung und die Connector-URL aus dem Internet – genau so, wie deine KI-App sie erreicht.",
        "test_run": "Verbindung testen",
        "test_busy": "Teste … (bis zu 30 s)",
        "test_ok": "Alles funktioniert.",
        "test_failed": "Etwas funktioniert nicht:",
        "test_server": "MCP-Server antwortet (Tools)",
        "test_garmin": "Garmin-Konto erreichbar",
        "test_public": "Connector-URL aus dem Internet erreichbar",
        "detail_not_logged_in": "nicht angemeldet – oben anmelden",
        "detail_relogin": "Anmeldung nicht mehr gültig – abmelden und neu anmelden",
        "detail_no_public": "öffentliche Adresse unbekannt – „Öffentliche Adresse“ in der Konfiguration eintragen",
        "remote": "Fernzugriff",
        "remote_active": "Aktiv – über deine Home-Assistant-Adresse",
        "remote_setting_up": "Wird eingerichtet …",
        "remote_restart_needed": "Home Assistant muss einmal neu gestartet werden",
        "remote_error": "Fehler",
        "remote_disabled": "Aus",
        "restart_hint": "Die App hat ihre kleine Hilfs-Integration für den Fernzugriff installiert bzw. aktualisiert. Home Assistant lädt sie erst nach einem Neustart – bis dahin kann der Connector nicht funktionieren. Die Anmeldung bei Garmin geht schon.",
        "restart_ha": "Home Assistant jetzt neu starten",
        "restart_confirm": "Home Assistant jetzt neu starten? Es ist dann etwa eine Minute nicht erreichbar.",
        "no_base_url": "In Home Assistant ist keine externe Adresse hinterlegt. Trage sie unter Einstellungen → System → Netzwerk ein oder in der App-Konfiguration als „Öffentliche Adresse“ – bis dahin den Platzhalter ersetzen.",
    },
}

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
    """Link to this add-on's configuration tab in the Home Assistant UI."""
    slug = socket.gethostname().replace("-", "_")
    return f"/config/app/{slug}/config"


def _lang(request: Request) -> str:
    accept = request.headers.get("accept-language", "").lower()
    return "de" if accept.startswith("de") else "en"


def _guard(request: Request) -> Response | None:
    client = request.client.host if request.client else ""
    if ALLOW_ANY_UI_CLIENT or client in (INGRESS_PROXY_IP, "127.0.0.1"):
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


async def index(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    t = TEXT[_lang(request)]
    services = SERVICES
    csrf = f'<input type="hidden" name="csrf" value="{CSRF_TOKEN}">'
    parts = [f"<h1>{t['title']}</h1>"]

    if FLASH:
        kind, key = FLASH.get("kind", "ok"), FLASH.get("key", "")
        detail = FLASH.get("detail", "")
        msg = t.get(key, key) + (f" <span class='muted'>({html.escape(detail)})</span>" if detail else "")
        parts.append(f'<div class="flash {kind}">{msg}</div>')
        FLASH.clear()

    # Restart banner – shown above everything else
    if REMOTE.enabled and REMOTE.state == "restart_needed":
        parts.append(
            f'<div class="banner"><b>{t["restart_banner_title"]}</b><p>{t["restart_hint"]}</p>'
            f'<form method="post" action="restart-ha" onsubmit="return confirm(\'{t["restart_confirm"]}\') && busy(this)">{csrf}'
            f'<button type="submit" data-busy="{t["restart_busy"]}">{t["restart_ha"]}</button></form></div>'
        )

    # Account card
    account = read_account()
    parts.append(f'<div class="card"><h2>{t["account"]}</h2>')
    if PENDING_MFA:
        parts.append(
            f'<p>{t["mfa_hint"]}</p><form method="post" action="mfa" onsubmit="return busy(this)">{csrf}'
            f'<label>{t["mfa_code"]}</label><input name="code" inputmode="numeric" autocomplete="one-time-code" required autofocus>'
            f'<div class="row"><button type="submit" data-busy="{t["login_busy"]}">{t["confirm"]}</button>'
            f'<button type="submit" class="secondary" formaction="cancel" formnovalidate>{t["cancel"]}</button></div></form>'
        )
    elif has_tokens():
        name = html.escape(account.get("name") or "–")
        parts.append(
            f'<p>{t["connected_as"]} <b>{name}</b></p>'
            + (f'<p class="muted">{t["upload_hint"]}</p>' if services.options.get("write_access") != "read_only" else "")
            + f'<form method="post" action="logout" onsubmit="return confirm(\'{t["logout_confirm"]}\')">{csrf}'
            f'<button type="submit" class="secondary">{t["logout"]}</button></form>'
        )
    else:
        parts.append(
            f'<p class="muted">{t["not_connected"]}</p><form method="post" action="login" onsubmit="return busy(this)">{csrf}'
            f'<label>{t["email"]}</label><input name="email" type="email" autocomplete="username" required>'
            f'<label>{t["password"]}</label><input name="password" type="password" autocomplete="current-password" required>'
            f'<button type="submit" data-busy="{t["login_busy"]}">{t["login"]}</button>'
            f'<p class="muted busy-note">{t["login_wait"]}</p></form>'
        )
    parts.append("</div>")

    # Server card
    state = await anyio.to_thread.run_sync(services.mcp_state)
    state_cls = {"ready": "ok", "failed": "err", "pending": "warn"}.get(state, "muted")
    custom = SELECTION_FILE.exists()
    wa = services.options.get("write_access", "create_only")
    rights = t["custom_selection"] if custom else t.get("wa_" + wa, wa)
    lang = _lang(request)
    rows = []
    for module, (_, en, de) in sorted(tool_texts.CATEGORIES.items(), key=lambda kv: kv[1][0]):
        tools_in = [e for e in CATALOG if e["module"] == module]
        if not tools_in:
            continue
        on = [e for e in tools_in if e["name"] in services.active_tools]
        kinds = {e["kind"] for e in on}
        badges = "".join(
            f'<span class="badge {k}">{t["kind_" + k]}</span>' for k in ("read", "create", "change") if k in kinds
        ) or f'<span class="muted">{t["nothing"]}</span>'
        rows.append(
            f'<tr><td>{de if lang == "de" else en}</td><td class="num">{len(on)}/{len(tools_in)}</td><td>{badges}</td></tr>'
        )
    parts.append(
        f'<div class="card"><h2>{t["server"]}</h2><table>'
        f'<tr><td class="muted">{t["state"]}</td><td class="{state_cls}">{t["state_" + state]}</td></tr>'
        f'<tr><td class="muted">{t["tools"]}</td><td>{len(services.active_tools)} / {len(ALL_TOOLS)}</td></tr>'
        f'<tr><td class="muted">{t["write_access"]}</td><td>{rights}</td></tr>'
        f'</table>'
        + (f'<p class="warn">{t["new_tools_hint"].format(n=len(fresh))} <a href="tools">{t["review"]}</a></p>' if (fresh := new_tools()) else "")
        + (
            f'<p class="warn">{t["unknown_tools"]} <code>{html.escape(", ".join(unknown))}</code></p>'
            if not custom and (unknown := unknown_tool_names(services.options))
            else ""
        )
        + f'<h3>{t["what_ai_may"]}</h3><table class="cats">{"".join(rows)}</table>'
        f'<div class="row links"><a class="btn" href="tools">{t["choose_tools"]}</a>'
        f'<a class="btn secondary" href="{_config_url()}" target="_top">{t["open_config"]}</a></div></div>'
    )

    # Connection test card
    test_html = ""
    if TEST_RESULT:
        items = "".join(
            f'<tr><td>{"✅" if c["ok"] else "❌"}</td><td>{t[c["key"]]}</td>'
            f'<td class="muted">{t.get("detail_" + c["detail"][1:], "") if c["detail"].startswith("@") else html.escape(c["detail"])}</td></tr>'
            for c in TEST_RESULT["checks"]
        )
        test_html = (
            f'<p class="{"ok" if TEST_RESULT["ok"] else "err"}">'
            f'{t["test_ok"] if TEST_RESULT["ok"] else t["test_failed"]} ({TEST_RESULT["time"]})</p>'
            f'<table>{items}</table>'
        )
    parts.append(
        f'<div class="card"><h2>{t["test_title"]}</h2><p class="muted">{t["test_intro"]}</p>{test_html}'
        f'<form method="post" action="test" onsubmit="return busy(this)">{csrf}'
        f'<button type="submit" class="secondary" data-busy="{t["test_busy"]}">{t["test_run"]}</button></form></div>'
    )

    # Connection card
    remote = REMOTE
    direct_public, url_problem = normalize_public_url(services.options.get("public_url"))
    direct_url = f"{direct_public or 'https://<your-domain>'}/{services.secret}/mcp"
    internal = f"http://{socket.gethostname()}:{PUBLIC_PORT}"
    rotate_form = (
        f'<form method="post" action="rotate" onsubmit="return confirm(\'{t["rotate_confirm"]}\')">{csrf}'
        f'<button type="submit" class="secondary">{t["rotate"]}</button></form>'
    )
    parts.append(f'<div class="card"><h2>{t["connection"]}</h2>')
    if url_problem:
        parts.append(f'<p class="warn">{t["public_url_" + url_problem]}</p>')
    if remote.enabled:
        base = await anyio.to_thread.run_sync(remote.base_url)
        url = f"{base or 'https://<your-home-assistant>'}/api/webhook/{remote.webhook_id}"
        rstate = remote.state
        rcls = {"active": "ok", "error": "err", "restart_needed": "warn"}.get(rstate, "muted")
        parts.append(
            f'<table><tr><td class="muted">{t["remote"]}</td>'
            f'<td class="{rcls}">{t["remote_" + rstate]}'
            + (f' <span class="muted">({html.escape(remote.detail)})</span>' if rstate == "error" and remote.detail else "")
            + "</td></tr></table>"
        )
        parts.append(
            f'<label>{t["connector_url"]}</label>{_secret_field("url", url, t)}'
            + ("" if base else f'<p class="muted">{t["no_base_url"]}</p>')
            + f'<p class="warn">{t["secret_warning"]}</p><p>{t["steps"]}</p>'
            f'<p class="muted">{t["oauth_hint"]}</p>{rotate_form}'
        )
    else:
        if remote.cleaned_up:
            parts.append(f'<p class="ok">{t["cleaned_up"]}</p>')
        parts.append(
            f'<label>{t["connector_url"]}</label>{_secret_field("url", direct_url, t)}'
            + ("" if direct_public else f'<p class="muted">{t["no_public_url"]}</p>')
            + f'<p class="warn">{t["secret_warning"]}</p><p>{t["steps"]}</p>'
            f'<label>{t["internal_url"]}</label><div class="row"><code>{html.escape(internal)}</code></div>'
            f'<p class="muted">{t["internal_hint"]}</p>{rotate_form}'
        )
    parts.append("</div>")

    parts.append(
        f'<p class="muted footer">Garmin Connect MCP {html.escape(os.environ.get("ADDON_VERSION", "dev"))}'
        f' · <a href="https://github.com/mw-hbg/ha-addons/blob/main/garmin_mcp/DOCS.md" target="_blank" rel="noopener">{t["docs"]}</a></p>'
    )
    body = "".join(parts)
    page = (
        f'<!doctype html><html lang="{_lang(request)}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{t['title']}</title><style>{CSS}</style></head>"
        f"<body><main>{body}</main><script>{JS}</script>"
        # While the server or remote access is still starting, reload the page
        # every few seconds so the status updates without user action.
        + ("<script>setTimeout(()=>location.reload(),5000)</script>"
           if (state == "pending" or REMOTE.state == "setting_up") and not PENDING_MFA else "")
        + "</body></html>"
    )
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "X-Frame-Options": "SAMEORIGIN"})


async def do_login(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    form = await _form(request)
    if form is not None:
        email = str(form.get("email", "")).strip()
        password = str(form.get("password", ""))
        try:
            result = await anyio.to_thread.run_sync(start_login, email, password)
            if result == "done":
                FLASH.update(kind="ok", key="ok_login")
        except LoginError as exc:
            FLASH.update(kind="err", key=exc.key, detail=exc.detail[:200])
        finally:
            password = ""
    return _redirect(request)


async def do_mfa(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    form = await _form(request)
    if form is not None:
        try:
            await anyio.to_thread.run_sync(finish_mfa, str(form.get("code", "")))
            FLASH.update(kind="ok", key="ok_login")
        except LoginError as exc:
            FLASH.update(kind="err", key=exc.key, detail=exc.detail[:200])
    return _redirect(request)


async def do_cancel(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        PENDING_MFA.clear()
    return _redirect(request)


async def do_logout(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        await anyio.to_thread.run_sync(logout)
        FLASH.update(kind="ok", key="ok_logout")
    return _redirect(request)


async def do_rotate(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        await anyio.to_thread.run_sync(SERVICES.rotate_secret)
        REMOTE.rotate()
        FLASH.update(kind="ok", key="ok_rotate")
    return _redirect(request)


async def do_restart_ha(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        await anyio.to_thread.run_sync(REMOTE.restart_home_assistant)
        FLASH.update(kind="ok", key="ok_restart")
    return _redirect(request)


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


async def tools_page(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    t = TEXT[_lang(request)]
    lang = _lang(request)
    active = SERVICES.active_tools
    csrf = f'<input type="hidden" name="csrf" value="{CSRF_TOKEN}">'
    parts = [f'<p><a href="./">{t["back"]}</a></p><h1>{t["tools_title"]}</h1>']
    if FLASH:
        parts.append(f'<div class="flash {FLASH.get("kind", "ok")}">{t.get(FLASH.get("key", ""), "")}</div>')
        FLASH.clear()
    fresh = set(new_tools())
    if fresh:
        parts.append(f'<div class="banner">{t["new_tools_banner"].format(n=len(fresh))}</div>')
    parts.append(
        f'<p class="muted">{t["tools_intro"]}</p>'
        f'<div class="toolbar"><input type="search" placeholder="{t["search"]}" oninput="filt(this.value)">'
        f'<div class="row" style="margin-top:8px"><span class="muted">{t["preset"]}</span>'
        f'<button type="button" class="secondary" onclick="preset([\'read\'])">{t["preset_read"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([\'read\',\'create\'])">{t["preset_create"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([\'read\',\'create\',\'change\'])">{t["preset_all"]}</button>'
        f'<button type="button" class="secondary" onclick="preset([])">{t["preset_none"]}</button></div></div>'
        f'<form method="post" action="tools" onsubmit="return busy(this)">{csrf}'
    )
    for module, (_, en, de) in sorted(tool_texts.CATEGORIES.items(), key=lambda kv: kv[1][0]):
        entries = sorted((e for e in CATALOG if e["module"] == module), key=lambda e: ("read", "create", "change").index(e["kind"]))
        if not entries:
            continue
        parts.append(f'<details class="card" open><summary>{de if lang == "de" else en} <span class="muted ccount"></span></summary>')
        for e in entries:
            label = tool_texts.DE.get(e["name"], e["doc"]) if lang == "de" else (e["doc"] or e["name"])
            search = html.escape(f'{e["name"]} {label} {e["doc"]} {de} {en}'.lower(), quote=True)
            checked = " checked" if e["name"] in active else ""
            parts.append(
                f'<div class="tool" data-search="{search}">'
                f'<input type="checkbox" name="tool" value="{e["name"]}" data-kind="{e["kind"]}" id="t_{e["name"]}"{checked}>'
                f'<div class="txt"><label for="t_{e["name"]}" style="margin:0;color:inherit;font-size:14px">{html.escape(label)}</label>'
                f' <span class="badge {e["kind"]}">{t["kind_" + e["kind"]]}</span>'
                + (f' <span class="badge new">{t["new"]}</span>' if e["name"] in fresh else "")
                +
                f'<div class="infobox"><b>{t["info_name"]}:</b> <code>{e["name"]}</code><br>'
                f'<b>{t["info_kind"]}:</b> {t["info_kind_" + e["kind"]]}'
                + (f'<br><b>{t["info_original"]}:</b> {html.escape(e["doc"])}' if lang == "de" and e["doc"] else "")
                + '</div></div>'
                '<button type="button" class="info" onclick="info(this)" aria-label="Info">i</button></div>'
            )
        parts.append("</details>")
    parts.append(
        f'<div class="savebar"><button type="submit" data-busy="{t["restart_busy"]}">{t["save"]}</button>'
        f'<span class="muted"><span id="cnt"></span> / {len(CATALOG)} {t["selected"]}</span></div></form>'
    )
    if SELECTION_FILE.exists():
        parts.append(
            f'<form method="post" action="tools/reset" onsubmit="return confirm(\'{t["reset_confirm"]}\')">{csrf}'
            f'<button type="submit" class="secondary">{t["reset"]}</button></form>'
        )
    return _page(request, t, "".join(parts), TOOLS_JS)


async def save_tools(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf", "")), CSRF_TOKEN):
        FLASH.update(kind="err", key="err_csrf")
    else:
        picked = {str(v) for v in form.getlist("tool")} & ALL_TOOLS
        save_selection(picked)
        log.info("Tool selection saved (%d tools)", len(picked))
        await anyio.to_thread.run_sync(SERVICES.reload_tools)
        FLASH.update(kind="ok", key="ok_tools")
    base = request.headers.get("x-ingress-path", "")
    return RedirectResponse(f"{base}/", status_code=303)


async def reset_tools(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        SELECTION_FILE.unlink(missing_ok=True)
        await anyio.to_thread.run_sync(SERVICES.reload_tools)
        FLASH.update(kind="ok", key="ok_tools_reset")
    base = request.headers.get("x-ingress-path", "")
    return RedirectResponse(f"{base}/tools", status_code=303)


async def do_test(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    if await _form(request) is not None:
        TEST_RESULT.clear()
        TEST_RESULT.update(await anyio.to_thread.run_sync(run_connection_test))
    return _redirect(request)


async def status(request: Request) -> Response:
    if (denied := _guard(request)) is not None:
        return denied
    state = await anyio.to_thread.run_sync(SERVICES.mcp_state)
    return JSONResponse(
        {
            "logged_in": has_tokens(),
            "server": state,
            "active_tools": sorted(SERVICES.active_tools),
            "write_access": SERVICES.options.get("write_access"),
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
        Route("/restart-ha", do_restart_ha, methods=["POST"]),
        Route("/test", do_test, methods=["POST"]),
        Route("/status.json", status),
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
    SERVICES.start_mcp()
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
