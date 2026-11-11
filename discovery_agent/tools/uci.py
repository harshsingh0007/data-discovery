"""Resolver for UCI Machine Learning Repository dataset pages: one of several link types
inspect_dataset_link understands. Use it as a worked example when you add resolvers for other portals.

A UCI page link (https://archive.ics.uci.edu/dataset/<id>/<slug>) resolves to:
  - structured metadata from the UCI API (which has NO licence field),
  - the licence from the human page (via extract_licence, gap G1),
  - the downloadable files (data_url and the zip linked from the page).
"""
from __future__ import annotations

import re

from .base import ToolContext, ToolError

UCI_API = "https://archive.ics.uci.edu/api"
UCI_PAGE_RE = re.compile(r"archive\.ics\.uci\.edu/(?:dataset|ml/datasets)/(\d+)", re.I)


def _clip(text: str | None, n: int = 2500) -> str | None:
    if text is None:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + f"… [clipped, {len(text)} chars]"


def fetch_uci_raw(ctx: ToolContext, uci_id: int) -> dict:
    data, _ = ctx.http.get_json(f"{UCI_API}/dataset?id={int(uci_id)}", max_bytes=800_000, agent=ctx.agent)
    if data.get("status") != 200 or not data.get("data"):
        raise ToolError(f"UCI dataset {uci_id} not found: {data.get('message')}")
    return data["data"]


def uci_metadata_summary(d: dict) -> dict:
    """Trim the UCI API record to what discovery needs. Note: last_updated is the metadata page date."""
    info = d.get("additional_info") or {}
    variables = d.get("variables") or []
    named = [v for v in variables if (v.get("name") or "").strip()]
    return {
        "name": d.get("name"),
        "repository_url": d.get("repository_url"),
        "data_url": d.get("data_url"),
        "abstract": _clip(d.get("abstract"), 800),
        "area": d.get("area"),
        "characteristics": d.get("characteristics"),
        "num_instances": d.get("num_instances"),
        "num_features": d.get("num_features"),
        "declared": {"has_missing_values": d.get("has_missing_values"),
                     "missing_values_symbol": d.get("missing_values_symbol"),
                     "demographics": d.get("demographics"),
                     "target_col": d.get("target_col")},
        "year_of_dataset_creation": d.get("year_of_dataset_creation"),
        "metadata_last_updated": d.get("last_updated"),
        "creators": d.get("creators"),
        "doi": d.get("dataset_doi"),
        "variables": [{k: v.get(k) for k in ("name", "role", "type", "description", "units", "missing_values")} for v in named][:80],
        "variables_listed": len(variables),
        "variables_with_blank_names": len(variables) - len(named),
        "notes": {k: _clip(info.get(k)) for k in ("summary", "variable_info", "purpose", "instances_represent",
                                                  "sensitive_data", "preprocessing_description", "funded_by")},
        "licence_in_api": None,
    }


def page_download_links(html: str, base: str = "https://archive.ics.uci.edu") -> list[str]:
    links = re.findall(r'href="(/static/public/[^"]+)"', html)
    return sorted({base + link for link in links})
