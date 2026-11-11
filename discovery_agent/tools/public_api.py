"""The client's external sources register, and calls to the public APIs on it."""
from __future__ import annotations

import json
from urllib.parse import quote, urlencode

from ..config import load_register
from .base import ToolContext, ToolError, tool
from .summarize import date_range, json_skeleton


@tool("list_external_register",
      "List the client's register of external sources for this use case: public APIs, vendor feeds and repositories, with "
      "agreement status, approved purposes, endpoint templates and terms URLs. Being listed is not approval for every "
      "purpose: check agreement_status and approved_purposes.",
      {})
def list_external_register(ctx: ToolContext, args: dict) -> dict:
    return {"use_case": ctx.use_case["id"], "sources": load_register(ctx.use_case["id"])}


def _register_entry(ctx: ToolContext, source_id: str) -> dict:
    for s in load_register(ctx.use_case["id"]):
        if s["id"] == source_id:
            return s
    raise ToolError(f"{source_id!r} is not in the external register for {ctx.use_case['id']}. Call list_external_register.")


@tool("call_public_api",
      "Make ONE small, read-only GET call to a public API on the external register, to check that it responds, what shape "
      "it returns and what period it covers. Fill the endpoint's {path_params}; query overrides default_query. Keep "
      "date ranges to a few days, because this is a probe, not a download. Vendor feeds are refused unless an agreement is active.",
      {"source_id": {"type": "string", "description": "Register id, e.g. 'api.open_meteo_archive'"},
       "path_params": {"type": "object", "additionalProperties": {"type": "string"}},
       "query": {"type": "object", "additionalProperties": {"type": "string"}}},
      ["source_id"])
def call_public_api(ctx: ToolContext, args: dict) -> dict:
    entry = _register_entry(ctx, args["source_id"])
    if entry["kind"] != "public_api":
        return {"source_id": entry["id"], "called": False,
                "reason": f"kind={entry['kind']}, agreement_status={entry.get('agreement_status')}. "
                          "No active agreement or credentials: do not attempt access. Record it as restricted.",
                "agreement_detail": entry.get("agreement_detail")}
    path_params = args.get("path_params") or {}
    missing = [p for p in entry.get("path_params", []) if p not in path_params]
    if missing:
        raise ToolError(f"Missing path_params {missing} for {entry['id']}. "
                        f"Endpoint: {entry['endpoint']}. Notes: {entry.get('param_notes')}")
    url = entry["endpoint"]
    for k, v in path_params.items():
        url = url.replace("{" + k + "}", quote(str(v), safe=";.:"))
    query = {**entry.get("default_query", {}), **(args.get("query") or {})}
    if query:
        url += "?" + urlencode(query, safe=",:;")
    res = ctx.http.get(url, max_bytes=1_500_000, agent=ctx.agent)
    out = {"source_id": entry["id"], "url": url, "status": res.status, "error": res.error,
           "content_type": res.content_type, "bytes": len(res.body), "truncated": res.truncated,
           "from_cache": res.from_cache}
    if res.error:
        out["body_start"] = res.text()[:500]
        return out
    try:
        payload = json.loads(res.text())
    except json.JSONDecodeError:
        out["body_start"] = res.text()[:1500]
        return out
    out["dates_found"] = date_range(payload)
    out["shape"] = json_skeleton(payload)
    return out
