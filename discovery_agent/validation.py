"""Checks that need no LLM: is a use case well formed, and is a finished run internally consistent?

`check` is a self-check, not the grader. It tells you whether your outputs are complete and
consistent, not whether your verdicts are right.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .agents import REQUIRED_MEMO_HEADINGS
from .config import ROOT, load_json, load_red_flags, load_register, use_case_files

GRAINS = {"minute", "15min", "30min", "hourly", "daily", "weekly", "monthly", "quarterly", "annual", "event", "static"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _iso(v) -> date | None:
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def validate_use_case(use_case_id: str) -> list[str]:
    files = use_case_files()
    if use_case_id not in files:
        return [f"no use_cases/*.json with id {use_case_id!r} (found {sorted(files)})"]
    uc = load_json(files[use_case_id])
    errs = []
    for key in ("id", "title", "client", "brief_file", "internal_dir", "as_of", "geography", "windows", "needs"):
        if key not in uc:
            errs.append(f"missing key {key!r}")
    if errs:
        return errs
    if not _iso(uc["as_of"]):
        errs.append(f"as_of {uc['as_of']!r} is not YYYY-MM-DD")
    win_ids = set()
    for w in uc["windows"]:
        s, e = _iso(w.get("start")), _iso(w.get("end"))
        if not (s and e):
            errs.append(f"window {w.get('id')!r}: start/end must be YYYY-MM-DD")
        elif s > e:
            errs.append(f"window {w['id']!r}: start after end")
        if not w.get("purpose"):
            errs.append(f"window {w.get('id')!r}: give a purpose")
        win_ids.add(w.get("id"))
    if len(win_ids) != len(uc["windows"]):
        errs.append("window ids must be unique")
    need_ids = [n.get("id") for n in uc["needs"]]
    if len(set(need_ids)) != len(need_ids):
        errs.append("need ids must be unique")
    for n in uc["needs"]:
        if not re.fullmatch(r"N[0-9]+", n.get("id", "")):
            errs.append(f"need id {n.get('id')!r} must look like N1, N2, ...")
        if n.get("priority") not in ("must", "should", "could"):
            errs.append(f"{n.get('id')}: priority must be must/should/could")
        if n.get("min_grain") not in GRAINS:
            errs.append(f"{n.get('id')}: min_grain {n.get('min_grain')!r} not in {sorted(GRAINS)}")
        if not n.get("windows") or set(n["windows"]) - win_ids:
            errs.append(f"{n.get('id')}: windows must be a non-empty subset of {sorted(win_ids)}")
    if not any(n.get("priority") == "must" for n in uc["needs"]):
        errs.append("at least one need must have priority 'must'")
    if not (ROOT / uc["brief_file"]).exists():
        errs.append(f"brief_file {uc['brief_file']} not found")
    base = ROOT / uc["internal_dir"]
    if not (base / "catalog_export.json").exists():
        errs.append(f"{uc['internal_dir']}/catalog_export.json not found")
    else:
        entries = load_json(base / "catalog_export.json").get("entries", [])
        if not entries:
            errs.append("catalog_export.json has no entries")
        for e in entries:
            for key in ("id", "display_name", "status", "owner", "temporal_coverage", "access", "columns"):
                if key not in e:
                    errs.append(f"catalog entry {e.get('id')!r}: missing key {key!r} (use null when unknown)")
            if "id" in e and not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", e["id"]):
                errs.append(f"catalog entry id {e['id']!r} must look like schema.table (lowercase)")
    if not (base / "wiki").is_dir():
        errs.append(f"{uc['internal_dir']}/wiki/ not found")
    if not load_register(use_case_id):
        errs.append(f"no sources in config/external_sources_register.json tagged {use_case_id!r}")
    return errs


SIGNOFF_VERDICTS = {"proceed", "proceed_with_conditions", "stop"}


def _dotted(rec: dict, path: str):
    cur = rec
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _check_signoff_files(out: Path, use_case_id: str, res: dict | None) -> list[str]:
    errs = []
    if res is not None and res.get("dataset_links") and not (out / "gate_decisions.json").exists():
        errs.append("gate_decisions.json not found: record accept or reject, with a reason, for each dataset link (format: links/_TEMPLATE_gate_decisions.json)")
    review_p = ROOT / "outputs" / "artifacts" / f"review_{use_case_id}.md"
    if not review_p.exists() or not review_p.read_text(encoding="utf-8").strip():
        errs.append(f"outputs/artifacts/review_{use_case_id}.md not found or empty: write your memo review")
    sign_p = out / "signoff.json"
    if not sign_p.exists():
        errs.append("signoff.json not found: record your gate decision, reviewer, conditions and one traced conclusion (format: outputs/artifacts/_TEMPLATE_signoff.json)")
    else:
        errs += _check_signoff(json.loads(sign_p.read_text(encoding="utf-8")), out, res)
    return errs


def _check_signoff(sig: dict, out: Path, res: dict | None) -> list[str]:
    errs = []
    if not str(sig.get("reviewer", "")).strip():
        errs.append("signoff.json: reviewer is empty")
    verdict = sig.get("verdict")
    if verdict not in SIGNOFF_VERDICTS:
        errs.append(f"signoff.json: verdict must be one of {sorted(SIGNOFF_VERDICTS)}")
    if verdict == "proceed_with_conditions":
        conds = sig.get("conditions") or []
        if not conds or any(not all(str(c.get(k, "")).strip() for k in ("text", "owner", "due")) for c in conds):
            errs.append("signoff.json: proceed_with_conditions needs conditions, each with text, owner and due")
    if not (sig.get("agreements") or sig.get("overrides")):
        errs.append("signoff.json: list at least one agreement or override, each with a reason")
    tc = sig.get("traced_conclusion") or {}
    for key in ("source_id", "record_field", "could_change_if"):
        if not str(tc.get(key, "")).strip():
            errs.append(f"signoff.json: traced_conclusion.{key} is empty")
    if len(str(tc.get("could_change_if", "")).strip()) < 20:
        errs.append("signoff.json: traced_conclusion.could_change_if needs at least 20 characters")
    sid = tc.get("source_id")
    if sid:
        if res is not None and sid not in {s["source_id"] for s in res["sources"]}:
            errs.append(f"signoff.json: traced_conclusion source {sid} is not in discovery_results.json")
        rec_p = out / "records" / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', sid)}.json"
        if not rec_p.exists():
            errs.append(f"signoff.json: no record file for {sid}")
        elif tc.get("record_field") and _dotted(json.loads(rec_p.read_text()), tc["record_field"]) is None:
            errs.append(f"signoff.json: field {tc['record_field']} is not in the record for {sid}")
    return errs


def check_run(use_case_id: str, out_dir: Path | None = None) -> tuple[list[str], dict]:
    out = out_dir or ROOT / "outputs" / use_case_id
    errs, stats = [], {}
    res_p = out / "discovery_results.json"
    if not res_p.exists():
        # Report every missing item at once, so the learner sees the whole list.
        errs.append(f"{res_p} not found: run the full pipeline through the assess stage to produce it")
        return errs + _check_signoff_files(out, use_case_id, None), stats
    res = json.loads(res_p.read_text())
    uc = load_json(use_case_files()[use_case_id])
    codes = load_red_flags()
    cands = json.loads((out / "candidates_final.json").read_text())["candidates"]
    assessed = {s["source_id"] for s in res["sources"]}
    for c in cands:
        if c["source_id"] not in assessed:
            errs.append(f"candidate {c['source_id']} has no assessment")
    for s in res["sources"]:
        for code in s["red_flags"]:
            if code not in codes:
                errs.append(f"{s['source_id']}: invalid code {code}")
        rec_p = out / "records" / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', s['source_id'])}.json"
        if rec_p.exists():
            rec = json.loads(rec_p.read_text())
            if len(rec.get("provenance", [])) < 3:
                errs.append(f"{s['source_id']}: fewer than 3 provenance entries")
            if "PROFILING FAILED" in rec.get("quality_notes", []):
                errs.append(f"{s['source_id']}: profiling failed")
    covered = {c["need_id"] for c in res["need_coverage"]}
    for n in uc["needs"]:
        if n["id"] not in covered:
            errs.append(f"need {n['id']} missing from need_coverage")
    if uc.get("links_expected", True) and not res.get("dataset_links"):
        errs.append("no dataset links assessed: supply links at the candidate gate (README section 4)")
    # A refused link is a finding, not an error: the distractor is refused on purpose.
    unreachable = [s["source_id"] for s in res["sources"] if s["kind"] == "dataset_link" and "ACC-UNREACHABLE" in s["red_flags"]]
    if res.get("rule_warnings"):
        errs.append(f"rules skipped (learner gaps not done?): {res['rule_warnings']}")
    errs += _check_signoff_files(out, use_case_id, res)
    memo_p = out / "feasibility_memo.md"
    if memo_p.exists():
        memo = memo_p.read_text()
        errs += [f"memo missing heading {h!r}" for h in REQUIRED_MEMO_HEADINGS if h not in memo]
    else:
        errs.append("feasibility_memo.md not found")
    for p in [res_p, memo_p, *sorted((out / "records").glob("*.json"))]:
        if p.exists() and EMAIL_RE.search(p.read_text()):
            errs.append(f"{p.name}: contains something that looks like an email address (personal data must not appear)")
    trace_p = out / "trace.jsonl"
    if trace_p.exists():
        events = [json.loads(line) for line in trace_p.read_text().splitlines() if line.strip()]
        refused = [e for e in events if e["kind"] == "http" and e.get("refused")]
        stats = {"llm_calls": sum(e["kind"] == "llm_call" for e in events),
                 "input_tokens": sum(e.get("input_tokens", 0) for e in events if e["kind"] == "llm_call"),
                 "output_tokens": sum(e.get("output_tokens", 0) for e in events if e["kind"] == "llm_call"),
                 "tool_calls": sum(e["kind"] == "tool_call" for e in events),
                 "tool_errors": sum(e["kind"] == "tool_call" and not e.get("ok") for e in events),
                 "http_live": sum(e["kind"] == "http" and not e.get("refused") and not e.get("from_cache") for e in events),
                 "http_refused": len(refused),
                 "refused_hosts": sorted({re.sub(r"^https?://([^/]+).*$", r"\1", e["url"]) for e in refused})}
        repeats = {}
        for e in refused:
            repeats[e["url"]] = repeats.get(e["url"], 0) + 1
        for url, n in repeats.items():
            if n > 2:
                errs.append(f"guardrail: refused URL retried {n} times ({url}); the agent should record it, not retry")
    stats = {**stats, "unreachable_links": unreachable}
    return errs, stats
