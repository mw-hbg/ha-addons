"""Regenerate the tool tables in DOCS.md / DOCS.<lang>.md from the code.

Run after a server update or a translation change (in the app folder):
    python scripts/update_docs.py
The tests fail if a table is out of date.
"""

import os
import re
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ROOT = APP.parent
sys.path.insert(0, str(APP / "rootfs" / "app"))
os.environ.setdefault("APP_DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("HA_CONFIG_DIR", tempfile.mkdtemp())

import logging  # noqa: E402

logging.disable(logging.WARNING)

import i18n  # noqa: E402
import launcher as L  # noqa: E402
from garmin_mcp.tool_profiles import TOOL_PROFILES  # noqa: E402

START, END = "<!-- tools:start -->", "<!-- tools:end -->"


def areas_of(name: str) -> list[str]:
    return [
        area for area, tools in TOOL_PROFILES.items()
        if tools is not None and (name in tools or name in L.AREA_EXTRAS.get(area, set()))
    ]


def table(lang: str) -> str:
    t = i18n.ui(lang)
    head = t["docs_table_head"]
    rows = [head, "|---|---|---|---|"]
    for e in sorted(L.CATALOG, key=lambda e: e["name"]):
        desc = i18n.tool(lang, e["name"], e["doc"]).replace("|", "\\|")
        rows.append(f'| `{e["name"]}` | {desc} | {t["kind_" + e["kind"]]} | {", ".join(areas_of(e["name"])) or "–"} |')
    return "\n".join(rows)


def render(text: str, lang: str) -> str:
    pattern = re.compile(re.escape(START) + ".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit(f"markers {START} / {END} missing")
    return pattern.sub(f"{START}\n{table(lang)}\n{END}", text)


def docs_files() -> dict[str, Path]:
    return {code: APP / i18n.ui(code)["docs_file"] for code in i18n.LANGUAGES}


def main() -> None:
    for lang, path in docs_files().items():
        new = render(path.read_text(), lang)
        if new != path.read_text():
            path.write_text(new)
            print("updated", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
