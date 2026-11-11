"""Generic probe for any allowlisted URL: what is it, how big, how structured, what does it say about its licence."""
from __future__ import annotations

import json

from .base import ToolContext, tool
from .summarize import csv_summary, date_range, html_summary, json_skeleton


def detect_json_kind(obj) -> str:
    if isinstance(obj, dict):
        if "resources" in obj and ("profile" in obj or "datapackage" in json.dumps(obj.get("profile", ""))):
            return "frictionless_datapackage"
        if obj.get("class") == "dataset" and "dimension" in obj and "id" in obj and "size" in obj:
            return "json_stat"
    return "json"


@tool("probe_url",
      "Fetch the first part of any allowlisted https URL (capped, read-only) and describe it: HTTP status, headers "
      "(content-length, last-modified), detected format, structure summary, dates found, and licence snippets for HTML "
      "pages. Use it on data files, metadata documents and terms or licence pages. It does not download whole datasets. "
      "If it reports a frictionless_datapackage or json_stat document, call summarize_datapackage or summarize_jsonstat.",
      {"url": {"type": "string"},
       "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 5000000, "default": 1500000}},
      ["url"])
def probe_url(ctx: ToolContext, args: dict) -> dict:
    res = ctx.http.get(args["url"], max_bytes=args.get("max_bytes"), agent=ctx.agent)
    out = {"url": res.url, "final_url": res.final_url, "status": res.status, "error": res.error,
           "content_type": res.content_type, "content_length_header": res.headers.get("content-length"),
           "last_modified_header": res.headers.get("last-modified"), "bytes_read": len(res.body),
           "truncated": res.truncated, "from_cache": res.from_cache}
    if res.error and not res.body:
        out["format"] = "unreachable"
        return out
    text = res.text()
    ctype = res.content_type
    stripped = text.lstrip()[:1]
    if "json" in ctype or stripped in ("{", "["):
        try:
            obj = json.loads(text)
            kind = detect_json_kind(obj)
            out.update(format=kind, dates_found=date_range(obj), shape=json_skeleton(obj, max_depth=4))
            if kind != "json":
                tool_name = "summarize_datapackage" if kind == "frictionless_datapackage" else "summarize_jsonstat"
                out["next_step"] = f"Call {tool_name} on this URL."
            return out
        except json.JSONDecodeError:
            out["json_parse_error"] = "truncated or invalid JSON" if res.truncated else "invalid JSON"
    if "html" in ctype or stripped == "<":
        out.update(format="html", **html_summary(text))
        return out
    if "csv" in ctype or "text/plain" in ctype or "," in text[:2000] or ";" in text[:2000]:
        out.update(format="delimited_text", **csv_summary(text))
        return out
    out.update(format="other", body_start=text[:600])
    return out
