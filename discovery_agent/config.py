"""Paths and loaders for the configuration, use cases and internal estates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
SCHEMAS_DIR = PACKAGE_DIR / "schemas"


def use_case_files() -> dict[str, Path]:
    """Every use_cases/*.json spec (except templates), keyed by its "id". Add a file to add a use case."""
    found = {}
    for path in sorted((ROOT / "use_cases").glob("*.json")):
        if path.name.startswith("_"):
            continue
        found[json.loads(path.read_text(encoding="utf-8"))["id"]] = path
    return found


def load_json(rel_or_abs: str | Path) -> Any:
    path = Path(rel_or_abs)
    if not path.is_absolute():
        path = ROOT / path
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> dict:
    return load_json("config/settings.json")


def load_allowlist() -> list[str]:
    return [d.lower() for d in load_json("config/allowlist.json")["domains"]]


def load_red_flags() -> dict[str, dict]:
    return load_json("config/red_flags.json")["codes"]


def load_register(use_case_id: str | None = None) -> list[dict]:
    sources = load_json("config/external_sources_register.json")["sources"]
    if use_case_id is None:
        return sources
    return [s for s in sources if use_case_id in s.get("use_cases", [])]


def load_schema(name: str) -> dict:
    return load_json(SCHEMAS_DIR / f"{name}.schema.json")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_use_case(use_case_id: str) -> dict:
    files = use_case_files()
    if use_case_id not in files:
        raise SystemExit(f"Unknown use case {use_case_id!r}. Found: {', '.join(files) or 'none'} in use_cases/")
    uc = load_json(files[use_case_id])
    uc["brief_text"] = (ROOT / uc["brief_file"]).read_text(encoding="utf-8")
    uc["internal_path"] = ROOT / uc["internal_dir"]
    return uc
