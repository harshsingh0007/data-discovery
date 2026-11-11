"""The five agents: what each may use, what each must return, and how its output is checked."""
from __future__ import annotations

from .agent import AgentSpec
from .config import load_prompt, load_red_flags, load_register, load_schema
from .tools.internal_catalog import _load_estate

SCOUT_TOOLS = ["search_internal_catalog", "get_catalog_entry", "read_wiki_page", "list_external_register"]
PROFILER_TOOLS = ["get_catalog_entry", "read_wiki_page", "search_internal_catalog", "list_external_register", "call_public_api",
                  "inspect_dataset_link", "sample_data_file", "probe_url", "summarize_datapackage", "summarize_jsonstat"]
RISK_TOOLS = ["read_wiki_page", "get_catalog_entry"]


def _with_shared(name: str) -> str:
    """System prompt = shared operating rules + agent-specific prompt."""
    return load_prompt("_shared_rules") + "\n\n" + load_prompt(name)


def planner_spec(uc: dict, settings: dict) -> AgentSpec:
    need_ids = {n["id"] for n in uc["needs"]}

    def covers_all_needs(p: dict) -> list[str]:
        got = {n["need_id"] for n in p["need_plans"]}
        return [f"need_plans is missing {sorted(need_ids - got)}"] if need_ids - got else []

    return AgentSpec("planner", _with_shared("planner"), ["list_external_register"], "submit_search_plan",
                     "Submit the search plan. Call exactly once, when complete.", load_schema("search_plan"),
                     settings["agents"]["max_turns"]["planner"], [covers_all_needs])


def scout_spec(uc: dict, settings: dict) -> AgentSpec:
    est = _load_estate(str(uc["internal_path"]))
    register_ids = {s["id"] for s in load_register(uc["id"]) if s["kind"] in ("public_api", "vendor_feed")}
    windows = {w["id"] for w in uc["windows"]}
    needs = {n["id"] for n in uc["needs"]}
    max_c = settings["agents"]["max_candidates"]

    def ids_exist(p: dict) -> list[str]:
        errs, seen = [], set()
        for c in p["candidates"]:
            sid = c["source_id"]
            if sid in seen:
                errs.append(f"duplicate candidate {sid}")
            seen.add(sid)
            if sid.startswith("internal.") and sid.removeprefix("internal.") not in est["entries"]:
                errs.append(f"{sid}: no such internal catalog entry (use the exact id from search_internal_catalog)")
            if sid.startswith(("api.", "vendor.")) and sid not in register_ids:
                errs.append(f"{sid}: not in the external register for {uc['id']}")
            if sid.startswith("link."):
                errs.append(f"{sid}: do not add dataset links yourself; the human supplies them at the candidate gate. "
                            "Describe what is missing in unmet_needs instead")
            kind_ok = {"internal.": "internal", "api.": "public_api", "vendor.": "vendor_feed"}
            for prefix, kind in kind_ok.items():
                if sid.startswith(prefix) and c["kind"] != kind:
                    errs.append(f"{sid}: kind must be {kind!r}")
            if set(c["target_windows"]) - windows:
                bad = sorted(set(c["target_windows"]) - windows)
                errs.append(f"{sid}: unknown target_windows {bad}; use {sorted(windows)}")
            if set(c["need_ids"]) - needs:
                errs.append(f"{sid}: unknown need_ids {sorted(set(c['need_ids']) - needs)}")
        if len(p["candidates"]) > max_c:
            errs.append(f"too many candidates ({len(p['candidates'])} > {max_c}). "
                        "Keep the strongest; list the rest in rejected_without_profiling")
        return errs

    return AgentSpec("scout", _with_shared("scout"), SCOUT_TOOLS, "submit_candidates",
                     "Submit the candidate source list. Call exactly once, when your search is complete.",
                     load_schema("candidates"), settings["agents"]["max_turns"]["scout"], [ids_exist])


def profiler_spec(uc: dict, settings: dict, candidate: dict) -> AgentSpec:
    def matches_candidate(r: dict) -> list[str]:
        errs = []
        if r["source_id"] != candidate["source_id"]:
            errs.append(f"source_id must be {candidate['source_id']!r}")
        if r["kind"] != candidate["kind"]:
            errs.append(f"kind must be {candidate['kind']!r}")
        t = r["temporal"]
        if t.get("start") and t.get("end") and t["start"] > t["end"]:
            errs.append("temporal.start is after temporal.end")
        return errs

    return AgentSpec("profiler", _with_shared("profiler"), PROFILER_TOOLS, "submit_catalog_record",
                     "Submit the catalog record for this one source. Call exactly once.",
                     load_schema("catalog_record"), settings["agents"]["max_turns"]["profiler"], [matches_candidate])


def risk_spec(uc: dict, settings: dict, records: list[dict], rule_flags: dict[str, list[dict]]) -> AgentSpec:
    valid_codes = set(load_red_flags())
    expected = {r["source_id"] for r in records}
    needs = {n["id"] for n in uc["needs"]}

    def complete_and_consistent(p: dict) -> list[str]:
        errs = []
        got = [a["source_id"] for a in p["assessments"]]
        if set(got) != expected or len(got) != len(set(got)):
            errs.append(f"assess every source exactly once. Missing: {sorted(expected - set(got))}; "
                        f"unexpected: {sorted(set(got) - expected)}")
        for a in p["assessments"]:
            raised = {f["code"] for f in a["red_flags"]}
            for code in raised | {d["code"] for d in a.get("dismissed_rule_flags", [])}:
                if code not in valid_codes:
                    errs.append(f"{a['source_id']}: invalid red-flag code {code!r}")
            dismissed = {d["code"] for d in a.get("dismissed_rule_flags", [])}
            for rf in rule_flags.get(a["source_id"], []):
                if rf["code"] not in raised and rf["code"] not in dismissed:
                    errs.append(f"{a['source_id']}: rule flag {rf['code']} must be kept in red_flags or listed in "
                                "dismissed_rule_flags with a reason")
            if a["verdict"] == "feasible_with_conditions" and not a["conditions"]:
                errs.append(f"{a['source_id']}: feasible_with_conditions needs at least one condition")
        cov = {c["need_id"] for c in p["need_coverage"]}
        if needs - cov:
            errs.append(f"need_coverage is missing {sorted(needs - cov)}")
        return errs

    return AgentSpec("risk_assessor", _with_shared("risk_assessor"), RISK_TOOLS, "submit_risk_assessment",
                     "Submit verdicts, red flags and need coverage for ALL sources. Call exactly once.",
                     load_schema("risk_assessment"), settings["agents"]["max_turns"]["risk_assessor"],
                     [complete_and_consistent])


REQUIRED_MEMO_HEADINGS = ["## 1. Executive summary", "## 2. Need coverage", "## 3. Source assessments",
                          "## 4. Red-flag register", "## 5. Conditions and owners", "## 6. Recommended next steps",
                          "## 7. Open questions for the human reviewer"]


def memo_spec(uc: dict, settings: dict, source_ids: list[str]) -> AgentSpec:
    def has_structure(p: dict) -> list[str]:
        md = p["markdown"]
        errs = [f"missing heading {h!r}" for h in REQUIRED_MEMO_HEADINGS if h not in md]
        missing = [s for s in source_ids if s not in md]
        if missing:
            errs.append(f"memo must mention every assessed source id; missing {missing}")
        return errs

    return AgentSpec("memo_writer", _with_shared("memo_writer"), [], "submit_memo",
                     "Submit the feasibility memo as Markdown. Call exactly once.", load_schema("memo"),
                     settings["agents"]["max_turns"]["memo_writer"], [has_structure])
