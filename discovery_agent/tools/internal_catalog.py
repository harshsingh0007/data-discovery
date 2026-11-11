"""Natural-language search over the client's internal catalog export and wiki.

Lexical BM25 on purpose: it is fast, transparent and fails in realistic ways
(undocumented tables score badly). The agent has to rephrase and read what it finds.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .base import ToolContext, ToolError, tool

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were will with".split())


def _tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall((text or "").lower()):
        if t in _STOP:
            continue
        if len(t) > 4 and t.endswith("s"):
            t = t[:-1]
        out.append(t)
    return out


def _parse_wiki(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return {"page_id": meta.get("page_id", path.stem), "title": meta.get("title", path.stem),
            "owner": meta.get("owner"), "last_edited": meta.get("last_edited"), "body": body.strip()}


@lru_cache(maxsize=4)
def _load_estate(internal_dir: str) -> dict:
    base = Path(internal_dir)
    catalog = json.loads((base / "catalog_export.json").read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in catalog["entries"]}
    wiki = {p["page_id"]: p for p in (_parse_wiki(f) for f in sorted((base / "wiki").glob("*.md")))}
    docs = []
    for e in entries.values():
        text = " ".join([e["id"].replace(".", " ").replace("_", " "), e.get("display_name") or "", e.get("description") or "",
                         e.get("domain") or "", " ".join(e.get("tags") or []),
                         " ".join(f"{c['name']} {c.get('description') or ''}" for c in e.get("columns") or [])])
        docs.append(("entry", e["id"], e.get("display_name") or e["id"], text))
    for p in wiki.values():
        docs.append(("wiki", p["page_id"], p["title"], p["title"] + " " + p["body"]))
    tokenised = [Counter(_tokens(d[3])) for d in docs]
    df = Counter(t for tf in tokenised for t in tf)
    avgdl = sum(sum(tf.values()) for tf in tokenised) / max(len(tokenised), 1)
    return {"catalog": catalog, "entries": entries, "wiki": wiki, "docs": docs, "tf": tokenised, "df": df, "avgdl": avgdl}


def estate(ctx: ToolContext) -> dict:
    return _load_estate(str(ctx.use_case["internal_path"]))


def _bm25(est: dict, query: str, k1: float = 1.4, b: float = 0.75) -> list[tuple[float, int]]:
    q = _tokens(query)
    n = len(est["docs"])
    scores = []
    for i, tf in enumerate(est["tf"]):
        dl = sum(tf.values())
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - est["df"][t] + 0.5) / (est["df"][t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / est["avgdl"]))
        if s > 0:
            scores.append((s, i))
    return sorted(scores, reverse=True)


def _snippet(text: str, query: str, width: int = 220) -> str:
    low = text.lower()
    for t in _tokens(query):
        pos = low.find(t)
        if pos >= 0:
            start = max(0, pos - width // 3)
            return ("…" if start else "") + re.sub(r"\s+", " ", text[start:start + width]) + "…"
    return re.sub(r"\s+", " ", text[:width]) + "…"


@tool("search_internal_catalog",
      "Search the client's internal data catalog AND wiki in plain language. Lexical (BM25) matching on names, "
      "descriptions, tags, column names and wiki text. Undocumented tables score poorly, so rephrase with synonyms "
      "and read the wiki hits. Returns ids you can open with get_catalog_entry or read_wiki_page.",
      {"query": {"type": "string", "description": "Plain-language question or keywords"},
       "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6}},
      ["query"])
def search_internal_catalog(ctx: ToolContext, args: dict) -> dict:
    est = estate(ctx)
    query = args["query"]
    hits = []
    for score, i in _bm25(est, query)[: int(args.get("top_k") or 6)]:
        kind, doc_id, title, text = est["docs"][i]
        hits.append({"type": "catalog_entry" if kind == "entry" else "wiki_page", "id": doc_id,
                     "source_id": f"internal.{doc_id}" if kind == "entry" else None,
                     "title": title, "score": round(score, 2), "snippet": _snippet(text, query)})
    return {"query": query, "hits": hits, "note": "No hits means no lexical match, not that no data exists." if not hits else None}


@tool("get_catalog_entry",
      "Open one internal catalog entry by id (for example 'airq.station_readings' or 'internal.airq.station_readings'). "
      "Returns every catalog field and lists the wiki pages that mention this entry (backlinks), which the catalog "
      "itself may not link.",
      {"entry_id": {"type": "string"}}, ["entry_id"])
def get_catalog_entry(ctx: ToolContext, args: dict) -> dict:
    est = estate(ctx)
    entry_id = args["entry_id"].removeprefix("internal.")
    if entry_id not in est["entries"]:
        close = [e for e in est["entries"] if entry_id.split(".")[-1][:4] in e]
        raise ToolError(f"No catalog entry {entry_id!r}. Similar ids: {close[:5]}")
    backlinks = [p["page_id"] for p in est["wiki"].values() if entry_id in p["body"]]
    return {"source_id": f"internal.{entry_id}", "entry": est["entries"][entry_id],
            "wiki_backlinks": backlinks, "catalog_exported_at": est["catalog"].get("exported_at")}


@tool("read_wiki_page",
      "Read a full internal wiki page by page_id. Wiki pages often correct, restrict or contradict catalog entries; "
      "check last_edited dates.",
      {"page_id": {"type": "string"}}, ["page_id"])
def read_wiki_page(ctx: ToolContext, args: dict) -> dict:
    est = estate(ctx)
    page_id = args["page_id"]
    if page_id not in est["wiki"]:
        raise ToolError(f"No wiki page {page_id!r}. Available: {sorted(est['wiki'])}")
    return est["wiki"][page_id]
