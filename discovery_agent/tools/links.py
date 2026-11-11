"""Understand ANY dataset link a human supplies: what is behind it, what it holds, and on what terms.

inspect_dataset_link  resolves the link type and gathers metadata:
    UCI dataset page | GitHub file page | Frictionless data package | JSON-stat | JSON API |
    landing page (schema.org JSON-LD, licence, download links) | direct data file | binary/archive | login wall
sample_data_file      reads a capped sample (default 2 MB) of a data file and profiles its columns.

Neither downloads whole datasets. Sampling is for understanding structure and quality, not analysis.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from .base import NotImplementedTool, ToolContext, tool
from .formats import datapackage_summary, jsonstat_summary
from .licence import extract_licence, jsonld_datasets, summarise_jsonld_dataset
from .probe import detect_json_kind
from .summarize import date_range, html_summary, json_skeleton
from .uci import UCI_PAGE_RE, fetch_uci_raw, page_download_links, uci_metadata_summary

GITHUB_BLOB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/(.+)$")
DATA_EXT_RE = re.compile(r"\.(csv|tsv|txt|json|jsonl|ndjson|geojson|parquet|xlsx?|zip|gz|bz2|xml)(\?|$)", re.I)
LOGIN_RE = re.compile(r"/(login|signin|sign-in|account/login|auth)\b", re.I)
MAGIC = {b"PK\x03\x04": "zip (or xlsx/docx)", b"\x1f\x8b": "gzip", b"PAR1": "parquet", b"BZh": "bzip2",
         b"\xd0\xcf\x11\xe0": "legacy Excel (xls)", b"%PDF": "pdf"}
SENTINELS = {"?", "-200", "-999", "-9999", "NA", "N/A", "n/a", "null", "NULL", "None", "NaN", "nan", "", "-", "."}
PII_NAME_RE = re.compile(r"(?i)e-?mail|phone|mobile|first_?name|last_?name|full_?name|surname|address|postcode|zip_?code|"
                         r"date_?of_?birth|dob|ssn|passport|iban|card")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DATE_FORMATS = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%d/%m/%Y %H:%M",
                "%m/%d/%Y", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%Y%m%d", "%Y-%m", "%Y"]


# -- identity --------------------------------------------------------------------
def github_raw(url: str) -> str:
    m = GITHUB_BLOB_RE.match(url)
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else url


def canonical_ref(url: str) -> str:
    """A stable identity for a link, so two spellings of the same dataset compare equal."""
    url = url.strip()
    m = UCI_PAGE_RE.search(url)
    if m:
        return f"uci:{int(m.group(1))}"
    url = github_raw(url)
    p = urlsplit(url)
    query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
    return f"{(p.hostname or '').lower()}{p.path.rstrip('/')}" + (f"?{query}" if query else "")


def link_source_id(url: str) -> str:
    ref = canonical_ref(url)
    if ref.startswith("uci:"):
        return f"link.uci_{ref[4:]}"
    host = ref.split("/", 1)[0].split(".")
    label = host[-2] if len(host) >= 2 else host[0]
    last = [s for s in urlsplit("https://" + ref).path.split("/") if s][-1:] or ["root"]
    slug = re.sub(r"[^a-z0-9]+", "_", f"{label}_{last[0]}".lower()).strip("_")[:32]
    return f"link.{slug}_{hashlib.sha1(ref.encode()).hexdigest()[:6]}"


# -- sampling ----------------------------------------------------------------------
def _parse_dates(values: list[str]) -> dict | None:
    vals = [v for v in values if v]
    if len(vals) < 3:
        return None
    for fmt in DATE_FORMATS:
        try:
            [datetime.strptime(v, fmt) for v in vals[:200]]
        except ValueError:
            continue
        parsed = []
        for v in vals:
            try:
                parsed.append(datetime.strptime(v, fmt))
            except ValueError:
                pass
        return {"format": fmt, "min": min(parsed).isoformat()[:19], "max": max(parsed).isoformat()[:19],
                "unparsed": len(vals) - len(parsed)}
    return None


def _num(v: str):
    try:
        return float(v.replace(",", ".")) if re.fullmatch(r"-?\d+([.,]\d+)?([eE][-+]?\d+)?", v) else None
    except ValueError:
        return None


def profile_rows(columns: list[str], rows: list[list[str]]) -> list[dict]:
    """Per-column profile of a sample. Values of columns that look personal are never returned."""
    out = []
    for i, name in enumerate(columns):
        vals = [(r[i] if i < len(r) else "").strip() for r in rows]
        sentinel = Counter(v for v in vals if v in SENTINELS)
        real = [v for v in vals if v not in SENTINELS]
        nums = [n for n in (_num(v) for v in real) if n is not None]
        pii = bool(PII_NAME_RE.search(name)) or any(EMAIL_RE.search(v) for v in real[:200])
        col = {"name": name, "non_missing_share": round(len(real) / len(vals), 3) if vals else None,
               "sentinel_counts": dict(sentinel), "distinct_in_sample": len(set(real)), "pii_suspected": pii}
        if real and len(nums) == len(real):
            col.update(type="integer" if all(n.is_integer() for n in nums) else "number", min=min(nums), max=max(nums),
                       zero_share=round(sum(n == 0 for n in nums) / len(nums), 3), negative_count=sum(n < 0 for n in nums))
        else:
            dates = _parse_dates(real)
            col["type"] = "date/time" if dates else ("text" if real else "empty")
            if dates:
                col["sample_range"] = dates
        if not pii and 0 < col["distinct_in_sample"] <= 30:
            col["values_in_sample"] = [v for v, _ in Counter(real).most_common(12)]
        elif not pii and real:
            col["examples"] = [v[:40] for v in list(dict.fromkeys(real))[:3]]
        out.append(col)
    return out


def sample_profile(raw: bytes, truncated: bool, content_length: str | None) -> dict:
    head = raw[:8]
    for magic, fmt in MAGIC.items():
        if head.startswith(magic):
            return {"format": fmt, "sampleable": False,
                    "note": f"Binary {fmt}: cannot be profiled from a partial read. Record its size and contents from the "
                            "documentation; a full download is a later, approved step."}
    text = raw.decode("utf-8", errors="replace")
    if truncated and "\n" in text:
        text = text[: text.rfind("\n")]
    stripped = text.lstrip()
    rows: list[list[str]]
    if stripped[:1] in "[{":
        records, obj = [], None
        try:
            obj = json.loads(stripped)
            if isinstance(obj, list):
                records = obj
            elif isinstance(obj, dict):
                records = next((v for v in obj.values() if isinstance(v, list)), [])
        except json.JSONDecodeError:
            for line in stripped.splitlines():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    break
        records = [r for r in records if isinstance(r, dict)]
        if not records:
            return {"format": "json", "sampleable": False, "note": "JSON without a list of records",
                    "shape": json_skeleton(obj) if obj is not None else stripped[:500]}
        columns = list(dict.fromkeys(k for r in records[:500] for k in r))
        rows = [[str(r.get(c, "")) for c in columns] for r in records]
        fmt, delim = "json records", None
    else:
        first = text.split("\n", 1)[0]
        delim = max([",", ";", "\t", "|"], key=first.count)
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        all_rows = [r for r in reader if r]
        if not all_rows:
            return {"format": "text", "sampleable": False, "note": "empty sample"}
        columns, rows, fmt = all_rows[0], all_rows[1:], "delimited text"
    avg = len(raw) / max(len(rows), 1)
    total = int(content_length) if content_length and content_length.isdigit() else None
    return {"format": fmt, "delimiter": delim, "sampleable": True, "columns": len(columns), "rows_in_sample": len(rows),
            "estimated_total_rows": int(total / avg) if total and truncated else (len(rows) if not truncated else None),
            "sample_is_whole_file": not truncated,
            "caution": None if not truncated else "Only the first part of the file was read. Ranges, distinct values and "
                                                  "missing shares describe the SAMPLE, not the file.",
            "profile": profile_rows(columns, rows)}


@tool("sample_data_file",
      "Read the FIRST part of a data file (CSV/TSV/JSON/JSONL; capped, default 2 MB) and profile its columns: inferred type, "
      "share non-missing, sentinel values ('?', -200, NA, ...), numeric min/max, zero and negative counts, date range IN THE "
      "SAMPLE, low-cardinality values. Values of personal-looking columns are never returned. Binary files (zip, xlsx, "
      "parquet) are reported, not parsed. Use the download URL found by inspect_dataset_link, not a landing page.",
      {"url": {"type": "string"},
       "max_bytes": {"type": "integer", "minimum": 10000, "maximum": 5000000, "default": 2000000}},
      ["url"])
def sample_data_file(ctx: ToolContext, args: dict) -> dict:
    url = github_raw(args["url"])
    res = ctx.http.get(url, max_bytes=args.get("max_bytes") or 2_000_000, agent=ctx.agent)
    out = {"url": url, "status": res.status, "error": res.error, "content_type": res.content_type,
           "content_length_header": res.headers.get("content-length"), "bytes_read": len(res.body), "truncated": res.truncated}
    if res.error or not res.body:
        out["reachable"] = False
        return out
    out.update(sample_profile(res.body, res.truncated, res.headers.get("content-length")))
    return out


# -- inspection ---------------------------------------------------------------------
def _resolve_uci(ctx: ToolContext, url: str, uci_id: int) -> dict:
    meta = uci_metadata_summary(fetch_uci_raw(ctx, uci_id))
    page = ctx.http.get(meta["repository_url"] or url, max_bytes=1_500_000, agent=ctx.agent)
    html = page.text() if not page.error else ""
    out = {"link_type": "uci_dataset_page", "metadata": meta, "page_status": page.status}
    out["licence"] = _licence_or_note(html, [])
    files = ([meta["data_url"]] if meta.get("data_url") else []) + page_download_links(html)
    out["files"] = sorted(set(files))
    out["next_steps"] = ([f"sample_data_file on {meta['data_url']}"] if meta.get("data_url") else
                         ["No plain data_url: the data is only in the archive(s) above, which cannot be sampled. "
                          "Describe the schema from metadata.variables and metadata.notes."])
    return out


def _licence_or_note(html: str, jsonld: list[dict]) -> dict:
    try:
        return extract_licence(html, jsonld)
    except NotImplementedTool as exc:
        return {"licence_name": None, "licence_url": None, "snippet": None, "found_in": None, "note": str(exc)}


def _landing_page(res, html: str) -> dict:
    datasets = jsonld_datasets(html)
    summary = html_summary(html, max_chars=2500)
    meta_desc = re.search(r'(?is)<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    links = []
    for href in re.findall(r'(?i)href="([^"#]+)"', html):
        full = urljoin(res.final_url, href)
        if (DATA_EXT_RE.search(full) or "download" in full.lower()) and full.startswith("https://") and full not in links:
            links.append(full)
    jl = [summarise_jsonld_dataset(d) for d in datasets[:3]]
    gated = any(any(x.get("requiresSubscription") in (True, "True", "true") for x in d["distribution"]) for d in jl)
    return {"link_type": "landing_page", "title": summary["title"], "meta_description": meta_desc.group(1)[:500] if meta_desc else None,
            "jsonld_datasets": jl, "licence": _licence_or_note(html, datasets), "licence_snippets": summary["licence_snippets"][:4],
            "data_links": links[:20], "downloads_require_login": gated or None, "text_start": summary["text_start"][:1500],
            "next_steps": ["Pick the most specific data file from jsonld_datasets[].distribution or data_links and call "
                           "sample_data_file on it (if it is on an allowlisted host).",
                           "If downloads require a login or subscription, record ACC-RESTRICTED; do not try to get around it."]}


@tool("inspect_dataset_link",
      "Work out what is behind ANY dataset link a human supplied: a UCI dataset page, a GitHub file page, a data portal "
      "landing page (Kaggle, Zenodo, data.gov, CKAN, Hugging Face, ... read via schema.org JSON-LD), a Frictionless "
      "datapackage.json, a JSON-stat API, a JSON API, a direct data file, an archive, or a login wall. Returns the link type, "
      "metadata, licence evidence, downloadable files and next steps. Call this first for every dataset_link candidate.",
      {"url": {"type": "string"}}, ["url"])
def inspect_dataset_link(ctx: ToolContext, args: dict) -> dict:
    url = args["url"].strip()
    base = {"url": url, "canonical_ref": canonical_ref(url), "source_id": link_source_id(url)}
    m = UCI_PAGE_RE.search(url)
    if m:
        return {**base, **_resolve_uci(ctx, url, int(m.group(1)))}
    target = github_raw(url)
    res = ctx.http.get(target, max_bytes=1_500_000, agent=ctx.agent)
    base.update(resolved_url=res.final_url, status=res.status, content_type=res.content_type,
                content_length_header=res.headers.get("content-length"), last_modified_header=res.headers.get("last-modified"))
    if res.status in (401, 403) or LOGIN_RE.search(urlsplit(res.final_url).path):
        return {**base, "link_type": "login_wall", "reachable": False,
                "note": "Authentication required. Record ACC-RESTRICTED and who could grant access. Do not try to bypass it."}
    if res.error and not res.body:
        return {**base, "link_type": "unreachable", "reachable": False, "error": res.error}
    if any(res.body.startswith(mg) for mg in MAGIC):
        return {**base, "link_type": "binary_file", **sample_profile(res.body[:16], True, res.headers.get("content-length"))}
    text = res.text()
    stripped = text.lstrip()[:1]
    if "json" in res.content_type or stripped in ("{", "["):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            kind = detect_json_kind(obj)
            if kind == "frictionless_datapackage":
                try:
                    return {**base, "link_type": "frictionless_datapackage", "summary": datapackage_summary(obj, None),
                            "next_steps": ["Call summarize_datapackage with a field_filter for the use case's geography."]}
                except NotImplementedTool as exc:
                    return {**base, "link_type": "frictionless_datapackage", "note": str(exc)}
            if kind == "json_stat":
                try:
                    return {**base, "link_type": "json_stat", "summary": jsonstat_summary(obj)}
                except NotImplementedTool as exc:
                    return {**base, "link_type": "json_stat", "note": str(exc)}
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                return {**base, "link_type": "data_file", **sample_profile(res.body, res.truncated, res.headers.get("content-length"))}
            return {**base, "link_type": "json_api", "dates_found": date_range(obj), "shape": json_skeleton(obj, max_depth=4)}
    if "html" in res.content_type or stripped == "<":
        return {**base, **_landing_page(res, text)}
    return {**base, "link_type": "data_file", **sample_profile(res.body, res.truncated, res.headers.get("content-length"))}
