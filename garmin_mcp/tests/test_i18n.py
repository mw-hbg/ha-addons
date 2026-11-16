"""Every language is complete, consistent and safe to put into the page.

Adding a language = adding files; these tests then check it automatically."""

import json
import re
from pathlib import Path

import pytest

import i18n
import launcher as L

ROOT = Path(__file__).resolve().parent.parent  # the app folder
APP = ROOT
CODES = sorted(i18n.LANGUAGES)
OTHER = [c for c in CODES if c != "en"]


def raw(code):
    return json.loads((i18n.I18N_DIR / f"{code}.json").read_text(encoding="utf-8"))


def test_at_least_english_and_german():
    assert {"en", "de"} <= set(CODES)


@pytest.mark.parametrize("code", OTHER)
def test_language_has_every_text(code):
    en, other = raw("en"), raw(code)
    for section in ("ui", "categories", "tools"):
        missing = sorted(set(en[section]) - set(other[section]))
        extra = sorted(set(other[section]) - set(en[section]))
        assert not missing, f"{code}.json {section}: missing {missing}"
        assert not extra, f"{code}.json {section}: unknown keys {extra}"


@pytest.mark.parametrize("code", CODES)
def test_placeholders_match_english(code):
    en, other = raw("en")["ui"], raw(code)["ui"]
    for key, value in other.items():
        assert set(re.findall(r"{\w*}", value)) == set(re.findall(r"{\w*}", en[key])), (code, key)


def test_every_tool_and_category_is_described_in_english():
    en = raw("en")
    assert not [e["name"] for e in L.CATALOG if e["name"] not in en["tools"]]
    assert set(en["categories"]) == set(i18n.CATEGORY_ORDER)


@pytest.mark.parametrize("code", CODES)
def test_every_language_has_ha_translations(code):
    """Configuration tab and helper integration exist in every page language."""
    assert (APP / "translations" / f"{code}.yaml").exists()
    integration = APP / "rootfs" / "app" / "integration" / "garmin_mcp_webhook" / "translations"
    assert (integration / f"{code}.json").exists()
    docs = raw(code)["ui"]["docs_file"]
    assert (APP / docs).exists(), docs


def test_ha_translations_have_the_same_structure():
    def keys(text):
        return re.findall(r"^(\s*[a-z0-9_/]+):(?=\s|$)", text, re.M)

    base = keys((APP / "translations" / "en.yaml").read_text())
    for path in (APP / "translations").glob("*.yaml"):
        assert keys(path.read_text()) == base, path.name

    integration = APP / "rootfs" / "app" / "integration" / "garmin_mcp_webhook"

    def flat(d, prefix=""):
        out = set()
        for k, v in d.items():
            out |= flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
        return out

    base = flat(json.loads((integration / "strings.json").read_text()))
    for path in (integration / "translations").glob("*.json"):
        assert flat(json.loads(path.read_text())) == base, path.name


@pytest.mark.parametrize(
    "header, expected",
    [
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("en-US,en;q=0.9,de;q=0.8", "en"),
        ("fr-FR,fr;q=0.9,de;q=0.8", "de"),
        ("de;q=0.1,en;q=0.5", "en"),
        ("fr", None),
        ("", None),
        ("de;q=0", None),
    ],
)
def test_browser_language(header, expected):
    assert i18n.from_accept_language(header) == expected


def test_language_order_and_fallback():
    assert i18n.pick(None, "de-CH", "en") == "de"
    assert i18n.pick("xx", None, "") == "en"
    assert i18n.pick("de_DE") == "de"


def test_missing_texts_fall_back_to_english(monkeypatch, tmp_path):
    (tmp_path / "en.json").write_text(json.dumps({"language": "English", "ui": {"a": "A", "b": "B"}, "categories": {}, "tools": {}}))
    (tmp_path / "xx.json").write_text(json.dumps({"language": "X", "ui": {"a": "Ax"}, "categories": {}, "tools": {}}))
    (tmp_path / "broken.json").write_text("{")
    monkeypatch.setattr(i18n, "I18N_DIR", tmp_path)
    langs = i18n._load()
    assert langs["xx"]["ui"] == {"a": "Ax", "b": "B"}
    assert "broken" not in langs


def test_page_falls_back_to_the_language_reported_by_home_assistant(monkeypatch):
    remote = L.RemoteAccess(L.Services())
    monkeypatch.setattr(L, "REMOTE", remote, raising=False)
    remote.receive_report({"language": "de"})
    assert L.ha_language() == "de"
    assert i18n.pick(None, None, L.ha_language()) == "de"


def test_page_language_switch(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setattr(L, "ALLOW_ANY_UI_CLIENT", True)
    monkeypatch.setattr(L, "ha_language", lambda: "")
    with TestClient(L.app) as client:
        resp = client.get("/lang?l=de", follow_redirects=False)
        assert resp.status_code == 303
        assert "garmin_mcp_lang=de" in resp.headers["set-cookie"]
        resp = client.get("/lang?l=<script>", follow_redirects=False)
        assert "set-cookie" not in resp.headers


def test_documentation_tool_tables_are_current():
    import importlib.util

    spec = importlib.util.spec_from_file_location("update_docs", ROOT / "scripts" / "update_docs.py")
    update_docs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(update_docs)
    for lang, path in update_docs.docs_files().items():
        assert update_docs.render(path.read_text(), lang) == path.read_text(), (
            f"{path.name} is out of date – run: python scripts/update_docs.py"
        )


def test_translating_guide_matches_the_files():
    guide = (APP / "TRANSLATING.md").read_text()
    for path in ("rootfs/app/i18n/xx.json", "translations/xx.yaml", "garmin_mcp_webhook/translations/xx.json"):
        assert path in guide
