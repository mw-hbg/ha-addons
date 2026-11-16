"""Information about the apps in this repository, for the GitHub workflows.

An app is every top-level folder that contains a config.yaml. Nothing in the
workflows is specific to one app – adding a folder is enough (see the
"Adding an app" section in the repository README).

  python .github/scripts/apps.py matrix          GitHub outputs: apps, builds
  python .github/scripts/apps.py info <app>      GitHub outputs for one app
  python .github/scripts/apps.py check           consistency checks
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLATFORMS = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
    "armv7": "linux/arm/v7",
    "armhf": "linux/arm/v6",
    "i386": "linux/386",
}


def apps() -> list[str]:
    return sorted(p.parent.name for p in ROOT.glob("*/config.yaml") if not p.parent.name.startswith("."))


def config(app: str) -> dict:
    return yaml.safe_load((ROOT / app / "config.yaml").read_text())


def info(app: str) -> dict:
    cfg = config(app)
    image = str(cfg.get("image", ""))
    archs = list(cfg.get("arch", []))
    return {
        "app": app,
        "name": cfg["name"],
        "version": str(cfg["version"]),
        "image": image,
        "archs": archs,
        "builds": [{"app": app, "arch": a, "platform": PLATFORMS[a]} for a in archs],
    }


def output(values: dict) -> None:
    for key, value in values.items():
        text = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
        print(f"{key}={text}")


def check() -> list[str]:
    problems = []
    found = apps()
    if not found:
        problems.append("no app folder with a config.yaml found")
    release = yaml.safe_load((ROOT / ".github/workflows/release.yaml").read_text())
    trigger = release.get("on") or release.get(True)
    options = trigger["workflow_dispatch"]["inputs"]["app"]["options"]
    if sorted(options) != found:
        problems.append(f"release.yaml: app choices {sorted(options)} must be exactly the apps {found}")
    readme = (ROOT / "README.md").read_text()
    for app in found:
        cfg = config(app)
        for name in ("README.md", "DOCS.md", "CHANGELOG.md", "icon.png", "logo.png", "Dockerfile"):
            if not (ROOT / app / name).exists():
                problems.append(f"{app}: {name} is missing")
        if cfg.get("slug") != app:
            problems.append(f"{app}: slug in config.yaml must be the folder name")
        image = str(cfg.get("image", ""))
        if not re.fullmatch(r"ghcr\.io/[a-z0-9-]+/\{arch\}-app-[a-z0-9-]+", image):
            problems.append(f"{app}: image must look like ghcr.io/<owner>/{{arch}}-app-<name>")
        for arch in cfg.get("arch", []):
            if arch not in PLATFORMS:
                problems.append(f"{app}: unknown arch {arch}")
        if not (ROOT / ".github/ISSUE_TEMPLATE" / f"{app}_bug.yml").exists():
            problems.append(f"{app}: bug report template .github/ISSUE_TEMPLATE/{app}_bug.yml is missing")
        if f"({app}/README.md)" not in readme:
            problems.append(f"README.md: {app} is not listed")
    return problems


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    if command == "matrix":
        found = apps()
        output({"apps": found, "builds": [b for a in found for b in info(a)["builds"]]})
    elif command == "info":
        app = sys.argv[2]
        if app not in apps():
            sys.exit(f"::error::{app} is not an app folder")
        output(info(app))
    elif command == "check":
        problems = check()
        for problem in problems:
            print(f"::error::{problem}")
        if problems:
            sys.exit(1)
        print("Apps:", ", ".join(apps()))
    else:
        sys.exit(f"unknown command {command}")


if __name__ == "__main__":
    main()
