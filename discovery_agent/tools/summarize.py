"""Turn raw responses into compact, model-friendly summaries (shape, not bulk values)."""
from __future__ import annotations

import csv
import html
import io
import re
from typing import Any

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
LICENCE_RE = re.compile(r"(?i)licen[cs]e|creative commons|\bcc[ -]by\b|attribution|open government|copyright"
                        r"|terms of use|public domain|\bMIT\b")


def json_skeleton(obj: Any, max_items: int = 3, depth: int = 0, max_depth: int = 5) -> Any:
    """Keep structure, cut breadth: lists show the first few items plus a count."""
    if depth >= max_depth:
        return f"<{type(obj).__name__}>"
    if isinstance(obj, dict):
        items = list(obj.items())
        out = {k: json_skeleton(v, max_items, depth + 1, max_depth) for k, v in items[:25]}
        if len(items) > 25:
            out["…"] = f"{len(items) - 25} more keys"
        return out
    if isinstance(obj, list):
        out = [json_skeleton(v, max_items, depth + 1, max_depth) for v in obj[:max_items]]
        if len(obj) > max_items:
            out.append(f"… {len(obj) - max_items} more items (total {len(obj)})")
        return out
    if isinstance(obj, str) and len(obj) > 300:
        return obj[:300] + "…"
    return obj


def date_range(obj: Any) -> dict:
    """Find ISO dates in values and keys, and 4-digit years in date/year/time fields."""
    dates: list[str] = []
    years: list[int] = []

    def walk(node: Any, key: str | None = None) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and DATE_RE.match(k):
                    dates.append(k[:10])
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            if DATE_RE.match(node):
                dates.append(node[:10])
            elif key and key.lower() in ("date", "year", "time", "period") and YEAR_RE.match(node):
                years.append(int(node))
        elif isinstance(node, int) and key and key.lower() in ("year",) and 1900 < node < 2100:
            years.append(node)

    walk(obj)
    out: dict = {}
    if dates:
        out.update(min_date=min(dates), max_date=max(dates), n_dates=len(dates))
    if years:
        out.update(min_year=min(years), max_year=max(years), n_years=len(set(years)))
    return out


def csv_summary(text: str, sample_rows: int = 3) -> dict:
    head = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(head.split("\n", 1)[0] + "\n", delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(head), delimiter=delim)
    rows = [r for _, r in zip(range(sample_rows + 1), reader)]
    header = rows[0] if rows else []
    sample = rows[1:]
    types = []
    for i, _ in enumerate(header):
        vals = [r[i] for r in sample if i < len(r)]
        types.append(_infer_type(vals))
    return {"delimiter": delim, "columns": header[:200], "column_count": len(header),
            "inferred_types_from_sample": types[:200], "sample_rows": [r[:20] for r in sample]}


def _infer_type(vals: list[str]) -> str:
    vals = [v for v in vals if v not in ("", "?", "NA", "NaN", "null")]
    if not vals:
        return "unknown"
    if all(re.fullmatch(r"-?\d+", v) for v in vals):
        return "integer"
    if all(re.fullmatch(r"-?\d+([.,]\d+)?([eE]-?\d+)?", v) for v in vals):
        return "number"
    if all(DATE_RE.match(v) or re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", v) for v in vals):
        return "date-like"
    return "string"


def html_summary(raw: str, max_chars: int = 3500) -> dict:
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    title_m = re.search(r"(?is)<title>(.*?)</title>", raw)
    links = re.findall(r'(?i)href="([^"]*(?:licen[cs]e|creativecommons|copyright|terms)[^"]*)"', raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    snippets = []
    for m in LICENCE_RE.finditer(text):
        s = text[max(0, m.start() - 160): m.end() + 220]
        if not any(s[:60] in prev for prev in snippets):
            snippets.append(s)
        if len(snippets) >= 8:
            break
    return {"title": html.unescape(title_m.group(1).strip()) if title_m else None,
            "text_start": text[:max_chars], "text_chars": len(text),
            "licence_snippets": snippets, "licence_links": sorted(set(links))[:15]}
