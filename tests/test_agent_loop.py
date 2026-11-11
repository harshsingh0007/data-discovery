"""The agent loop and the whole pipeline, driven by a scripted fake LLM (no gateway needed)."""
import itertools
import json
import re
from types import SimpleNamespace

import pytest

from discovery_agent.agent import AgentFailed, run_agent, validate
from discovery_agent.agents import REQUIRED_MEMO_HEADINGS, planner_spec, risk_spec
from discovery_agent.orchestrator import Pipeline, RunOptions
from discovery_agent.tools import ToolContext
from discovery_agent.trace import Trace

_ids = itertools.count(1)


def tool_use(name, inp):
    block = SimpleNamespace(type="tool_use", id=f"tu_{next(_ids)}", name=name, input=inp)
    block.model_dump = lambda **_: {"type": "tool_use", "id": block.id, "name": name, "input": inp}
    return block


def text(t):
    block = SimpleNamespace(type="text", text=t)
    block.model_dump = lambda **_: {"type": "text", "text": t}
    return block


def reply(*blocks, stop="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=SimpleNamespace(input_tokens=10, output_tokens=5))


class FakeLLM:
    """script: {agent label prefix: [response or callable(messages) -> response, ...]}"""

    model = "fake-model"

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def complete(self, *, agent, system, messages, tools, max_tokens, turn):
        self.calls.append(agent)
        key = next(k for k in self.script if agent.startswith(k))
        step = self.script[key].pop(0) if len(self.script[key]) > 1 else self.script[key][0]
        return step(messages) if callable(step) else step


def plan_payload(uc):
    return {"use_case": uc["id"], "objective_summary": "Find data to explain poor-air days and warn clinic patients in time.",
            "need_plans": [{"need_id": n["id"], "interpretation": n["name"], "internal_queries": [n["name"]],
                            "external_data_hints": [], "register_ids": [], "acceptance_criteria": ["covers window"]} for n in uc["needs"]],
            "open_questions": []}


def record(source_id, kind, **over):
    rec = {"source_id": source_id, "kind": kind, "title": source_id, "location": None, "status": "active",
           "summary": "A test record that is long enough to pass the minimum length check.",
           "schema": {"documented": "structured", "fields": []},
           "temporal": {"start": "2012-01-01", "end": None, "grain": "monthly"},
           "spatial": {"coverage": ["PT"]}, "ownership": {"owner": "Billing"},
           "licence": {"name": "internal", "evidence": "catalog", "commercial_use": "not_applicable"},
           "access": {"method": "warehouse_sql", "auth_required": True, "reachable": True},
           "declared_metadata": {}, "documentation_excerpts": [], "quality_notes": [],
           "provenance": [{"claim": "c", "evidence": "get_catalog_entry"}] * 3, "unknowns": []}
    rec.update(over)
    return rec


def risk_from_task(messages):
    """Keep every rule flag the orchestrator passed in, as a well-behaved Risk Assessor must."""
    task = messages[0]["content"]
    sources = json.loads(re.search(r"<sources>\n(.*)\n</sources>", task, re.S).group(1))
    needs = json.loads(re.search(r"<use_case_spec>\n(.*?)\n</use_case_spec>", task, re.S).group(1))["needs"]
    return reply(tool_use("submit_risk_assessment", {
        "assessments": [{"source_id": s["record"]["source_id"], "verdict": "feasible_with_conditions",
                         "red_flags": [{"code": f["code"], "evidence": f["evidence"]} for f in s["rule_flags"]],
                         "conditions": ["raise an access ticket"], "rationale": "test"} for s in sources],
        "need_coverage": [{"need_id": n["id"], "status": "partially_met", "best_sources": []} for n in needs],
        "overall_verdict": "feasible_with_conditions", "overall_rationale": "test"}))


def memo_from_task(messages):
    ids = re.findall(r'"source_id": "([^"]+)"', messages[0]["content"])
    md = "\n\n".join(REQUIRED_MEMO_HEADINGS) + "\n\n" + " ".join(sorted(set(ids))) + "\n\n" + ("Body text. " * 100)
    return reply(tool_use("submit_memo", {"markdown": md, "open_questions_for_human": ["Who owns the clinic extract?"]}))


@pytest.fixture
def ctx(uc1, settings, tmp_path):
    return ToolContext(use_case=uc1, settings=settings, http=None, trace=Trace(tmp_path / "trace.jsonl"))


def test_agent_uses_tool_then_submits(uc1, settings, ctx, tmp_path):
    llm = FakeLLM({"planner": [reply(tool_use("list_external_register", {})),
                               reply(tool_use("submit_search_plan", plan_payload(uc1)))]})
    out = run_agent(planner_spec(uc1, settings), "task", llm=llm, ctx=ctx, settings=settings,
                    transcript_path=tmp_path / "t.json")
    assert out["use_case"] == "UC1" and llm.calls == ["planner", "planner"]
    transcript = json.loads((tmp_path / "t.json").read_text())
    assert any(isinstance(m["content"], list) and m["content"][0].get("type") == "tool_result" for m in transcript["messages"])


def test_invalid_submission_is_rejected_then_fixed(uc1, settings, ctx):
    bad = plan_payload(uc1)
    bad["need_plans"] = bad["need_plans"][:2]
    llm = FakeLLM({"planner": [reply(tool_use("submit_search_plan", bad)),
                               reply(tool_use("submit_search_plan", plan_payload(uc1)))]})
    out = run_agent(planner_spec(uc1, settings), "task", llm=llm, ctx=ctx, settings=settings)
    assert len(out["need_plans"]) == len(uc1["needs"]) and len(llm.calls) == 2


def test_text_only_reply_is_nudged_then_fails(uc1, settings, ctx):
    llm = FakeLLM({"planner": [reply(text("I think..."), stop="end_turn")]})
    with pytest.raises(AgentFailed):
        run_agent(planner_spec(uc1, settings), "task", llm=llm, ctx=ctx, settings=settings)
    assert len(llm.calls) == 3


def test_tools_outside_the_agent_toolset_are_refused(uc1, settings, ctx):
    llm = FakeLLM({"planner": [reply(tool_use("probe_url", {"url": "https://example.com"})),
                               reply(tool_use("submit_search_plan", plan_payload(uc1)))]})
    run_agent(planner_spec(uc1, settings), "task", llm=llm, ctx=ctx, settings=settings)
    assert ctx.trace.totals["http_refused"] == 0


def test_risk_validator_blocks_silently_dropped_rule_flags(uc1, settings):
    recs = [record("internal.billing.monthly_invoices", "internal")]
    spec = risk_spec(uc1, settings, recs, {"internal.billing.monthly_invoices": [{"code": "GOV-PII", "evidence": "e"}]})
    payload = {"assessments": [{"source_id": "internal.billing.monthly_invoices", "verdict": "not_feasible",
                                "red_flags": [], "conditions": [], "rationale": "r"}],
               "need_coverage": [{"need_id": n["id"], "status": "unmet", "best_sources": []} for n in uc1["needs"]],
               "overall_verdict": "not_feasible", "overall_rationale": "r"}
    assert any("GOV-PII" in e for e in validate(payload, spec))
    payload["assessments"][0]["dismissed_rule_flags"] = [{"code": "GOV-PII", "reason": "aggregated only"}]
    assert validate(payload, spec) == []


def test_full_pipeline_with_fake_llm(uc1, tmp_path):
    cands = [{"source_id": "internal.clinic.patient_visits", "kind": "internal", "title": "Clinic visits",
              "need_ids": ["N5"], "target_windows": ["production"], "why_relevant": "patient level visits", "found_via": "search"},
             {"source_id": "api.open_meteo_archive", "kind": "public_api", "title": "Weather",
              "need_ids": ["N3"], "target_windows": ["prototype", "production"], "why_relevant": "temperature", "found_via": "register"}]
    billing_rec = record("internal.clinic.patient_visits", "internal",
                         schema={"documented": "structured", "fields": [{"name": "postcode", "pii": True}]})
    nager_rec = record("api.open_meteo_archive", "public_api",
                       temporal={"start": "1940-01-01", "end": None, "grain": "hourly"},
                       licence={"name": "CC BY 4.0", "evidence": "terms page", "commercial_use": "yes"},
                       access={"method": "rest_api", "auth_required": False, "reachable": True})
    link_rec = record("link.uci_360", "dataset_link", canonical_ref="uci:360",
                      temporal={"start": "2004-03-10", "end": "2005-04-04", "grain": "hourly"},
                      licence={"name": "CC BY 4.0", "evidence": "repository page", "commercial_use": "yes"},
                      access={"method": "file_download", "auth_required": False, "reachable": True})
    llm = FakeLLM({
        "planner": [reply(tool_use("submit_search_plan", plan_payload(uc1)))],
        "scout": [reply(tool_use("submit_candidates", {"candidates": cands, "searches_run": ["x"], "unmet_needs": []}))],
        "profiler__internal": [reply(tool_use("submit_catalog_record", billing_rec))],
        "profiler__api": [reply(tool_use("submit_catalog_record", nager_rec))],
        "profiler__link": [reply(tool_use("submit_catalog_record", link_rec))],
        "risk_assessor": [risk_from_task],
        "memo_writer": [memo_from_task],
    })
    out = tmp_path / "UC1"
    out.mkdir(parents=True, exist_ok=True)
    link = "https://archive.ics.uci.edu/dataset/360/air+quality"
    (out / "gate_decisions.json").write_text(json.dumps({"decisions": [{"url": link, "decision": "accept",
        "reason": "Public hourly air-quality readings; the city and missing-value coding need checking."}]}))
    Pipeline(RunOptions(use_case_id="UC1", out_dir=out, interactive=False,
                        links=[{"url": link, "need_ids": ["N1"], "target_windows": ["prototype"]}]), llm=llm).run()
    results = json.loads((out / "discovery_results.json").read_text())
    assert {s["source_id"] for s in results["sources"]} == {c["source_id"] for c in cands} | {"link.uci_360"}
    assert results["dataset_links"][0]["canonical_ref"] == "uci:360"
    linked = next(s for s in results["sources"] if s["source_id"] == "link.uci_360")
    assert linked["kind"] == "dataset_link" and linked["location"].endswith("air+quality")
    billing = next(s for s in results["sources"] if s["source_id"] == "internal.clinic.patient_visits")
    assert "GOV-PII" in billing["red_flags"]
    memo = (out / "feasibility_memo.md").read_text()
    assert "## Human review gate" in memo and "Who owns the clinic extract?" in memo
    for name in ("search_plan.json", "candidates.json", "candidates_final.json", "rule_flags.json", "risk_assessment.json",
                 "run_summary.json", "trace.jsonl"):
        assert (out / name).exists(), name
    assert (out / "transcripts").is_dir()


def test_links_need_a_recorded_gate_decision(uc1, tmp_path):
    out = tmp_path / "UC1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates.json").write_text(json.dumps({"candidates": [], "unmet_needs": []}))
    link = {"url": "https://archive.ics.uci.edu/dataset/360/air+quality", "need_ids": ["N1"], "target_windows": ["prototype"]}
    with pytest.raises(SystemExit, match="Missing"):
        Pipeline(RunOptions(use_case_id="UC1", out_dir=out, interactive=False, links=[link]), llm=FakeLLM({})).candidate_gate()
    (out / "gate_decisions.json").write_text(json.dumps({"decisions": [{"url": link["url"], "decision": "accept", "reason": "short"}]}))
    with pytest.raises(SystemExit, match="too short"):
        Pipeline(RunOptions(use_case_id="UC1", out_dir=out, interactive=False, links=[link]), llm=FakeLLM({})).candidate_gate()
