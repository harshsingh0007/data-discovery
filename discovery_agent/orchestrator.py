"""Runs the discovery pipeline stage by stage, saving every artifact.

    plan -> scout -> [candidate gate: human adds dataset links] -> profile (fan-out) -> assess (rules + agent) -> memo -> human gate

Each stage reads the previous stage's artifact from the output folder, so you can re-run
from any stage (--from-stage) after changing a prompt, tool or rule, without paying for
the earlier stages again.
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from . import risk_rules
from .agent import AgentFailed, run_agent
from .agents import memo_spec, planner_spec, profiler_spec, risk_spec, scout_spec
from .config import ROOT, load_allowlist, load_red_flags, load_settings, load_use_case
from .llm import LLM, say
from .tools import ToolContext
from .tools.http_client import HttpClient, host_allowed
from .tools.links import canonical_ref, link_source_id
from .trace import Trace

STAGES = ["plan", "scout", "profile", "assess", "memo"]


@dataclass
class RunOptions:
    use_case_id: str
    out_dir: Path | None = None
    from_stage: str = "plan"
    stop_after: str = "memo"
    links: list[dict] = field(default_factory=list)  # [{"url", "need_ids", "target_windows"}], from --link / --links-file
    interactive: bool = True
    use_cache: bool = True
    only_sources: list[str] = field(default_factory=list)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _read(path: Path, stage_hint: str):
    if not path.exists():
        raise SystemExit(f"{path} not found. Run the '{stage_hint}' stage first (or start from an earlier --from-stage).")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe(source_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", source_id)


def spec_view(uc: dict) -> dict:
    return {k: uc[k] for k in ("id", "title", "client", "as_of", "geography", "windows", "needs")}


class Pipeline:
    def __init__(self, opts: RunOptions, llm=None):
        self.opts = opts
        self.uc = load_use_case(opts.use_case_id)
        self.settings = load_settings()
        self.out = opts.out_dir or (ROOT / "outputs" / self.uc["id"])
        self.out.mkdir(parents=True, exist_ok=True)
        self.trace = Trace(self.out / "trace.jsonl")
        self.http = HttpClient(self.settings, load_allowlist(), self.trace, use_cache=opts.use_cache)
        self.ctx = ToolContext(use_case=self.uc, settings=self.settings, http=self.http, trace=self.trace)
        self.llm = llm or LLM(self.trace)
        self.warnings: list[str] = []
        self.timings: dict[str, float] = {}
        self._ran_scout = False

    # -- helpers ---------------------------------------------------------------
    def _agent(self, spec, task: str, name: str):
        return run_agent(spec, task, llm=self.llm, ctx=self.ctx, settings=self.settings,
                         transcript_path=self.out / "transcripts" / f"{_safe(name)}.json", label=name)

    def _brief_block(self) -> str:
        return (f"<use_case_spec>\n{json.dumps(spec_view(self.uc), indent=1)}\n</use_case_spec>\n\n"
                f"<business_brief>\n{self.uc['brief_text']}\n</business_brief>")

    # -- stages ------------------------------------------------------------------
    def plan(self) -> dict:
        task = f"{self._brief_block()}\n\nProduce the search plan for every need, then call submit_search_plan."
        plan = self._agent(planner_spec(self.uc, self.settings), task, "planner")
        _write(self.out / "search_plan.json", plan)
        return plan

    def scout(self) -> dict:
        plan = _read(self.out / "search_plan.json", "plan")
        task = (f"{self._brief_block()}\n\n<search_plan>\n{json.dumps(plan, indent=1)}\n</search_plan>\n\n"
                f"Execute the plan and submit at most {self.settings['agents']['max_candidates']} candidates with submit_candidates.")
        cands = self._agent(scout_spec(self.uc, self.settings), task, "scout")
        _write(self.out / "candidates.json", cands)
        self._ran_scout = True
        return cands

    def _require_gate_decisions(self, links: list[dict]) -> list[dict]:
        """Keep only the links the learner accepted. Every link needs an explicit decision and a reason."""
        if not links:
            return links
        p = self.out / "gate_decisions.json"
        if not p.exists():
            raise SystemExit(f"Missing {p}. Record accept or reject, with a reason, for each dataset link before profiling. Format and rules: README section 9, template links/_TEMPLATE_gate_decisions.json.")
        decided = {d.get("url", "").strip(): d for d in json.loads(p.read_text(encoding="utf-8")).get("decisions", [])}
        kept = []
        for link in links:
            url = link["url"].strip()
            d = decided.get(url)
            if d is None:
                raise SystemExit(f"No decision for {url} in {p}. Add accept or reject with a reason.")
            if d.get("decision") not in ("accept", "reject"):
                raise SystemExit(f"Decision for {url} must be 'accept' or 'reject'.")
            if len((d.get("reason") or "").strip()) < 20:
                raise SystemExit(f"Reason for {url} is too short: give at least 20 characters, in your own words.")
            if d["decision"] == "accept":
                kept.append(link)
        return kept

    def candidate_gate(self) -> list[dict]:
        """Human checkpoint between scouting and profiling: drop candidates, add dataset links (any URL)."""
        cands = _read(self.out / "candidates.json", "scout")
        unmet, cands = cands.get("unmet_needs", []), cands["candidates"]
        links = self._require_gate_decisions(list(self.opts.links))
        if self.opts.interactive and sys.stdin.isatty():
            say("\nCandidate gate: the Scout proposes these sources:")
            for i, c in enumerate(cands, 1):
                say(f"  {i:>2}. {c['source_id']:<42} needs={','.join(c['need_ids'])} windows={','.join(c['target_windows'])}")
            drop = input("Numbers to drop before profiling (comma-separated, Enter for none): ").strip()
            if drop:
                idx = {int(x) for x in drop.split(",") if x.strip().isdigit()}
                cands = [c for i, c in enumerate(cands, 1) if i not in idx]
            say("\nNeeds the Scout could not meet internally: " + ("; ".join(unmet) or "none"))
            plan_p = self.out / "search_plan.json"
            if plan_p.exists():
                for np_ in json.loads(plan_p.read_text())["need_plans"]:
                    if np_.get("external_data_hints"):
                        say(f"  {np_['need_id']} look for: {' | '.join(np_['external_data_hints'][:2])}")
            say(f"\nAdd dataset links (any URL: a dataset page, portal record, data file, API). {self.uc.get('links_hint', '')}")
            while True:
                url = input("Dataset link (Enter to finish): ").strip()
                if not url:
                    break
                needs = [n.strip() for n in input("  Need ids it should fill (e.g. N1,N6): ").split(",") if n.strip()]
                windows = [w.strip() for w in input(f"  Target windows {[w['id'] for w in self.uc['windows']]}: ").split(",") if w.strip()]
                links.append({"url": url, "need_ids": needs, "target_windows": windows})
        valid_needs = {n["id"] for n in self.uc["needs"]}
        valid_windows = {w["id"] for w in self.uc["windows"]}
        added = []
        for link in links:
            url = link["url"].strip()
            if not url.startswith("https://"):
                raise SystemExit(f"Dataset links must be https:// URLs: {url!r}")
            if not link.get("need_ids") or set(link["need_ids"]) - valid_needs:
                raise SystemExit(f"{url}: need_ids must be from {sorted(valid_needs)}")
            if not link.get("target_windows") or set(link["target_windows"]) - valid_windows:
                raise SystemExit(f"{url}: target_windows must be from {sorted(valid_windows)}")
            host = re.sub(r"^https?://([^/]+).*$", r"\1", url).lower()
            sid = link_source_id(url)
            # With --only, warn only about the links that will actually be profiled.
            profiled = not self.opts.only_sources or sid in self.opts.only_sources
            if profiled and not host_allowed(host, self.http.allowlist):
                self.warnings.append(f"dataset link host {host!r} is not allowlisted; inspection will be refused (gap G6)")
                say(f"  WARNING: {host} is not in config/allowlist.json. The profiler will record the link as unreachable.")
            if sid in {c["source_id"] for c in cands + added}:
                continue
            added.append({"source_id": sid, "kind": "dataset_link", "title": f"Dataset link: {url[:90]}", "location": url,
                          "canonical_ref": canonical_ref(url), "need_ids": link["need_ids"],
                          "target_windows": link["target_windows"],
                          "why_relevant": link.get("note") or "Supplied by the human at the candidate gate",
                          "found_via": "human input", "suspected_issues": []})
        if not added:
            self.warnings.append("no dataset links supplied; external datasets were not assessed (README section 4)")
        cands = [c for c in cands if c["kind"] != "dataset_link"] + added
        _write(self.out / "candidates_final.json", {"candidates": cands, "links": [a["location"] for a in added]})
        return cands

    def profile(self) -> list[dict]:
        final = self.out / "candidates_final.json"
        if self._ran_scout or self.opts.links or not final.exists():
            cands = self.candidate_gate()
        else:
            cands = _read(final, "scout")["candidates"]
            say(f"  reusing {final.name} ({len(cands)} candidates); pass --link or --links-file to redo the candidate gate")
        if self.opts.only_sources:
            cands = [c for c in cands if c["source_id"] in self.opts.only_sources]
        spec = spec_view(self.uc)

        def one(c: dict) -> dict:
            task = (f"<use_case_spec>\n{json.dumps(spec, indent=1)}\n</use_case_spec>\n\n"
                    f"<candidate>\n{json.dumps(c, indent=1)}\n</candidate>\n\n"
                    "Profile this one source and call submit_catalog_record.")
            try:
                rec = self._agent(profiler_spec(self.uc, self.settings, c), task, f"profiler__{c['source_id']}")
            except AgentFailed as exc:
                self.warnings.append(f"profiling failed for {c['source_id']}: {exc}")
                rec = failed_record(c, str(exc))
            _write(self.out / "records" / f"{_safe(c['source_id'])}.json", rec)
            return rec

        say(f"  profiling {len(cands)} sources ({self.settings['agents']['profiler_parallelism']} in parallel)")
        records = []
        with ThreadPoolExecutor(max_workers=self.settings["agents"]["profiler_parallelism"]) as pool:
            for fut in as_completed([pool.submit(one, c) for c in cands]):
                records.append(fut.result())
        return records

    def _load_records_and_candidates(self) -> tuple[list[dict], dict[str, dict]]:
        cands = {c["source_id"]: c for c in _read(self.out / "candidates_final.json", "profile")["candidates"]}
        records = []
        for p in sorted((self.out / "records").glob("*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            if rec["source_id"] in cands:
                records.append(rec)
        if not records:
            raise SystemExit("No records found. Run the 'profile' stage first.")
        return records, cands

    def assess(self) -> dict:
        records, cands = self._load_records_and_candidates()
        rule_flags, rule_warnings = {}, set()
        for rec in records:
            flags, warns = risk_rules.evaluate(rec, cands[rec["source_id"]], self.uc, self.settings)
            rule_flags[rec["source_id"]] = flags
            rule_warnings.update(warns)
        self.warnings.extend(sorted(rule_warnings))
        _write(self.out / "rule_flags.json", {"flags": rule_flags, "warnings": sorted(rule_warnings)})
        codes = load_red_flags()
        bundle = [{"candidate": {k: cands[r["source_id"]].get(k) for k in ("need_ids", "target_windows", "why_relevant")},
                   "record": r, "rule_flags": rule_flags[r["source_id"]]} for r in records]
        task = (f"<use_case_spec>\n{json.dumps(spec_view(self.uc), indent=1)}\n</use_case_spec>\n\n"
                f"<red_flag_codes>\n{json.dumps(codes, indent=1)}\n</red_flag_codes>\n\n"
                f"<sources>\n{json.dumps(bundle, indent=1, default=str)}\n</sources>\n\n"
                "Assess every source, then call submit_risk_assessment.")
        risk = self._agent(risk_spec(self.uc, self.settings, records, rule_flags), task, "risk_assessor")
        _write(self.out / "risk_assessment.json", risk)
        results = merge_results(self.uc, records, cands, rule_flags, risk, codes, self.llm,
                                sorted(rule_warnings))
        _write(self.out / "discovery_results.json", results)
        return results

    def memo(self) -> str:
        results = _read(self.out / "discovery_results.json", "assess")
        records, _ = self._load_records_and_candidates()
        compact = [{"source_id": r["source_id"], "title": r["title"], "summary": r["summary"], "temporal": r["temporal"],
                    "licence": (r.get("licence") or {}).get("name"), "owner": (r.get("ownership") or {}).get("owner")} for r in records]
        task = (f"{self._brief_block()}\n\n<discovery_results>\n{json.dumps(results, indent=1)}\n</discovery_results>\n\n"
                f"<record_summaries>\n{json.dumps(compact, indent=1)}\n</record_summaries>\n\nWrite the memo and call submit_memo.")
        ids = [s["source_id"] for s in results["sources"]]
        memo = self._agent(memo_spec(self.uc, self.settings, ids), task, "memo_writer")
        text = memo["markdown"].rstrip() + "\n\n" + human_gate(self.uc, results, memo["open_questions_for_human"])
        (self.out / "feasibility_memo.md").write_text(text, encoding="utf-8")
        return text

    # -- driver ----------------------------------------------------------------
    def run(self) -> None:
        start, stop = STAGES.index(self.opts.from_stage), STAGES.index(self.opts.stop_after)
        say(f"Discovery run {self.uc['id']} | model={self.llm.model} | stages {STAGES[start]}..{STAGES[stop]} | out={self.out}")
        try:
            for stage in STAGES[start:stop + 1]:
                say(f"[{stage}]")
                t0 = time.time()
                getattr(self, stage)()
                self.timings[stage] = round(time.time() - t0, 1)
        finally:
            self._summary()
        if stop == STAGES.index("scout"):
            say(f"\nStopped after scout. Review {self.out / 'candidates.json'}, then run --from-stage profile.")
        if stop == len(STAGES) - 1:
            say(f"\nHUMAN REVIEW GATE: read {self.out / 'feasibility_memo.md'} and sign off before any profiling or pipeline work.")

    def _summary(self) -> None:
        summary = {"use_case": self.uc["id"], "model": self.llm.model, "stages": self.timings, "totals": self.trace.totals,
                   "warnings": self.warnings, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _write(self.out / "run_summary.json", summary)
        with (self.out / "run_history.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary) + "\n")
        say(f"  totals: {self.trace.totals}")
        for w in self.warnings:
            say(f"  warning: {w}")


def failed_record(c: dict, error: str) -> dict:
    return {"source_id": c["source_id"], "kind": c["kind"], "title": c.get("title", c["source_id"]), "location": c.get("location"),
            "status": None, "summary": f"Profiling failed, so no record could be built: {error[:300]}",
            "schema": {"documented": "none", "fields": []}, "temporal": {"start": None, "end": None, "grain": "unknown"},
            "spatial": {"coverage": []}, "ownership": {"owner": None},
            "licence": {"name": None, "evidence": None, "commercial_use": "unknown"},
            "access": {"method": "unknown", "auth_required": None, "reachable": None},
            "declared_metadata": {}, "documentation_excerpts": [], "quality_notes": ["PROFILING FAILED"],
            "provenance": [{"claim": "profiling failed", "evidence": "orchestrator"}], "unknowns": ["everything"]}


def merge_results(uc, records, cands, rule_flags, risk, codes, llm, rule_warnings) -> dict:
    by_id = {a["source_id"]: a for a in risk["assessments"]}
    sources = []
    for rec in records:
        sid = rec["source_id"]
        a = by_id[sid]
        rule_codes = {f["code"] for f in rule_flags.get(sid, [])}
        details = [{"code": f["code"], "severity": f.get("severity") or codes.get(f["code"], {}).get("severity"),
                    "evidence": f["evidence"], "raised_by": "rule" if f["code"] in rule_codes else "judgement"}
                   for f in a["red_flags"]]
        sources.append({"source_id": sid, "kind": rec["kind"], "title": rec["title"], "location": cands[sid].get("location"),
                        "canonical_ref": cands[sid].get("canonical_ref"),
                        "need_ids": cands[sid].get("need_ids"), "target_windows": cands[sid].get("target_windows"),
                        "verdict": a["verdict"], "red_flags": sorted({d["code"] for d in details}), "red_flag_details": details,
                        "dismissed_rule_flags": a.get("dismissed_rule_flags", []), "conditions": a["conditions"],
                        "who_can_resolve": a.get("who_can_resolve", []), "rationale": a["rationale"]})
    return {"use_case": uc["id"], "as_of": uc["as_of"], "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": llm.model, "overall_verdict": risk["overall_verdict"], "overall_rationale": risk["overall_rationale"],
            "need_coverage": risk["need_coverage"], "sources": sources, "rule_warnings": rule_warnings,
            "dataset_links": [{"source_id": c["source_id"], "url": c["location"], "canonical_ref": c.get("canonical_ref"),
                               "need_ids": c["need_ids"], "target_windows": c["target_windows"]}
                              for c in cands.values() if c["kind"] == "dataset_link"]}


def human_gate(uc: dict, results: dict, questions: list[str]) -> str:
    blockers = sorted({f"{s['source_id']}: {d['code']}" for s in results["sources"] for d in s["red_flag_details"]
                       if d.get("severity") == "blocker" and s["verdict"] != "not_feasible"})
    lines = ["---", "", "## Human review gate", "",
             f"Draft generated by the discovery agents for {uc['id']} on {results['generated_at']} (model {results['model']}). "
             "It is a draft for review, not a decision.", "",
             "Before any profiling or pipeline work, the reviewer confirms:", "",
             "- [ ] Each verdict is supported by the evidence cited",
             "- [ ] Every licence was read at its source, and the attribution text is recorded",
             "- [ ] Access requests for the feasible-with-conditions sources are raised with the named owners",
             "- [ ] Consent and purpose limits are understood, and the target population is filtered accordingly"]
    if blockers:
        lines += ["", "**Blocker flags on sources not rejected (resolve or justify):**", ""] + [f"- {b}" for b in blockers]
    lines += ["", "**Open questions:**", ""] + [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    lines += ["", "Reviewer: ____________________   Date: __________   Decision: proceed / proceed with conditions / stop", ""]
    return "\n".join(lines)
