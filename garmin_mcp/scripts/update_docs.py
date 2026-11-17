"""Regenerate the tool tables in DOCS.md from the code.

DOCS.md holds every language in one file (Home Assistant shows only DOCS.md):
a section "## English", "## Deutsch", … each with its own table between
<!-- tools:<lang>:start --> and <!-- tools:<lang>:end -->.

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

DOCS = APP / "DOCS.md"


def markers(lang: str) -> tuple[str, str]:
    return f"<!-- tools:{lang}:start -->", f"<!-- tools:{lang}:end -->"


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


def languages_in(text: str) -> list[str]:
    """Languages that have a tool table in the text (English must be one)."""
    return [lang for lang in i18n.LANGUAGES if markers(lang)[0] in text]


def render(text: str) -> str:
    if "en" not in languages_in(text):
        raise SystemExit("DOCS.md: markers <!-- tools:en:start --> / <!-- tools:en:end --> missing")
    for lang in languages_in(text):
        start, end = markers(lang)
        pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.S)
        if not pattern.search(text):
            raise SystemExit(f"DOCS.md: {end} missing")
        text = pattern.sub(lambda _m: f"{start}\n{table(lang)}\n{end}", text)
    return text


def main() -> None:
    old = DOCS.read_text(encoding="utf-8")
    new = render(old)
    if new != old:
        DOCS.write_text(new, encoding="utf-8")
        print("updated", DOCS.relative_to(ROOT))


if __name__ == "__main__":
    main()
