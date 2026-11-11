"""Acceptance tests for the learner gaps. These FAIL on a fresh checkout. Make them pass.

    python -m pytest tests/test_learner_gaps.py -q
    python -m pytest tests/test_learner_gaps.py -q -k g3      # one gap at a time
"""
import re

import pytest

from discovery_agent import risk_rules
from discovery_agent.config import PROMPTS_DIR, load_allowlist
from discovery_agent.tools.formats import jsonstat_summary
from discovery_agent.tools.http_client import host_allowed
from discovery_agent.tools.licence import extract_licence


# -- G1: licence of any dataset from its landing page ----------------------------------
G1_KEYS = {"licence_name", "licence_url", "snippet", "found_in"}


def test_g1_uci_page_link_or_text(fixture_text):
    out = extract_licence(fixture_text("uci_321_repository_page.html"))
    assert set(out) == G1_KEYS and out["licence_name"] == "CC BY 4.0" and out["found_in"] in ("link", "text")
    assert out["snippet"] and len(out["snippet"]) <= 400


def test_g1_zenodo_jsonld_url(fixture_text):
    out = extract_licence(fixture_text("zenodo_record_landing_page.html"))
    assert out["licence_name"] == "CC BY 4.0" and out["found_in"] == "json-ld"
    assert "creativecommons.org/licenses/by/4.0" in out["licence_url"]


def test_g1_kaggle_unknown_is_not_a_licence(fixture_text):
    out = extract_licence(fixture_text("kaggle_ecommerce_landing_page.html"))
    assert out["licence_name"] is None and out["found_in"] == "json-ld" and "Unknown" in (out["snippet"] or "")


@pytest.mark.parametrize("jsonld,expected", [
    ([{"@type": "Dataset", "license": "http://opendatacommons.org/licenses/odbl/1.0/"}], "ODbL 1.0"),
    ([{"@type": "Dataset", "license": "https://choosealicense.com/licenses/cc0-1.0/"}], "CC0 1.0"),
    ([{"@type": "Dataset", "license": {"@type": "CreativeWork", "name": "CC BY-NC-SA 4.0", "url": ""}}], "CC BY-NC-SA 4.0"),
])
def test_g1_jsonld_variants(jsonld, expected):
    assert extract_licence("<html></html>", jsonld)["licence_name"] == expected


@pytest.mark.parametrize("html,expected", [
    ('<p>Released under the <a href="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/">'
     "Open Government Licence v3.0</a>.</p>", "OGL v3.0"),
    ('<p>This dataset is licensed under a <a href="https://creativecommons.org/licenses/by-nc/4.0/legalcode">'
     "Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)</a> license.</p>", "CC BY-NC 4.0"),
    ("<p>No terms are given on this page.</p>", None),
])
def test_g1_text_and_links(html, expected):
    out = extract_licence(html, [])
    assert out["licence_name"] == expected
    if expected is None:
        assert out == {"licence_name": None, "licence_url": None, "snippet": None, "found_in": None}


# -- G3: JSON-stat ------------------------------------------------------------------
G3_KEYS = {"label", "updated", "source", "dimensions", "time", "geo_codes", "expected_cells", "value_count",
           "missing_cells", "status_counts", "warnings"}


def test_g3_eurostat_response(fixture_json):
    out = jsonstat_summary(fixture_json("eurostat_isoc_ec_ibuy_2009_2011.json"))
    assert set(out) == G3_KEYS
    assert [d["id"] for d in out["dimensions"]] == ["freq", "indic_is", "ind_type", "unit", "geo", "time"]
    assert out["time"]["first"] == "2009" and out["time"]["last"] == "2011"
    assert "UK" in out["geo_codes"] and "GB" not in out["geo_codes"]
    assert out["expected_cells"] == 24 and out["value_count"] == 24 and out["missing_cells"] == 0
    assert "NON_ISO_GEO_CODES" in out["warnings"] and "MISSING_CELLS" not in out["warnings"]


def test_g3_list_values_missing_cells_and_status():
    ds = {"version": "2.0", "class": "dataset", "label": "L", "id": ["geo", "time"], "size": [2, 2],
          "dimension": {"geo": {"category": {"index": ["FR", "EL"], "label": {"FR": "France", "EL": "Greece"}}},
                        "time": {"category": {"index": {"2011": 1, "2010": 0}}}},
          "value": [1.0, None, 2.0, 3.0], "status": {"3": "p"}}
    out = jsonstat_summary(ds)
    assert out["geo_codes"] == ["FR", "EL"] and out["time"]["values"] == ["2010", "2011"]
    assert out["value_count"] == 3 and out["missing_cells"] == 1 and out["status_counts"] == {"p": 1}
    assert set(out["warnings"]) == {"MISSING_CELLS", "NON_ISO_GEO_CODES"}


# -- G4: rules ----------------------------------------------------------------------
def rec(start, end, grain="15min", **over):
    r = {"source_id": "x", "kind": "uci", "temporal": {"start": start, "end": end, "grain": grain},
         "declared_metadata": {}, "documentation_excerpts": [], "quality_notes": []}
    r.update(over)
    return r


def codes(flags):
    return {f["code"] for f in flags}


def test_g4_out_of_window_and_stale(uc1, settings):
    cand = {"need_ids": ["N1"], "target_windows": ["prototype"]}
    flags = risk_rules.rule_temporal_coverage(rec("1990-01-01", "1998-12-31"), cand, uc1, settings)
    assert codes(flags) == {"COV-OUT-OF-WINDOW", "FRS-STALE"}
    assert all("prototype" in f["evidence"] or "1998-12-31" in f["evidence"] for f in flags)


def test_g4_partial_window_across_two_windows(uc1, settings):
    cand = {"need_ids": ["N6"], "target_windows": ["prototype", "production"]}
    assert codes(risk_rules.rule_temporal_coverage(rec("2005-01-01", "2023-12-31", "annual"), cand, uc1, settings)) == {
        "COV-PARTIAL-WINDOW"}


def test_g4_open_ended_source_starting_late(uc1, settings):
    cand = {"need_ids": ["N2"], "target_windows": ["production"]}
    assert codes(risk_rules.rule_temporal_coverage(rec("2024-06-01", None, "hourly"), cand, uc1, settings)) == {"COV-PARTIAL-WINDOW"}


def test_g4_full_coverage_and_static_raise_nothing(uc1, settings):
    cand = {"need_ids": ["N1"], "target_windows": ["prototype"]}
    # Full coverage of the prototype window: the only flag allowed is staleness (2005 data, as-of 2026).
    assert codes(risk_rules.rule_temporal_coverage(rec("2004-03-10", "2005-04-04", "hourly"), cand, uc1, settings)) == {"FRS-STALE"}
    assert risk_rules.rule_temporal_coverage(rec(None, None, "static"), cand, uc1, settings) == []


def test_g4_grain(uc1, settings):
    assert codes(risk_rules.rule_grain(rec("2004-01-01", None, "monthly"), {"need_ids": ["N1"]}, uc1, settings)) == {"COV-GRAIN-MISMATCH"}
    assert codes(risk_rules.rule_grain(rec("2004-01-01", None, "annual"), {"need_ids": ["N1"]}, uc1, settings)) == {"COV-GRAIN-MISMATCH"}
    assert risk_rules.rule_grain(rec("2022-01-01", None, "daily"), {"need_ids": ["N4"]}, uc1, settings) == []
    assert risk_rules.rule_grain(rec("2019-01-01", None, "event"), {"need_ids": ["N5"]}, uc1, settings) == []
    assert risk_rules.rule_grain(rec("2004-03-10", None, "15min"), {"need_ids": ["N1"]}, uc1, settings) == []
    assert risk_rules.rule_grain(rec("2004-03-10", None, "hourly"), {"need_ids": ["N99"]}, uc1, settings) == []


def test_g4_metadata_contradiction(uc1, settings):
    c = {"need_ids": ["N1"], "target_windows": ["prototype"]}
    r235 = rec("2006-12-16", "2010-11-26", declared_metadata={"has_missing_values": "no"},
               documentation_excerpts=["The dataset contains some missing values in the measurements (nearly 1,25% of the rows)."])
    assert codes(risk_rules.rule_metadata_contradiction(r235, c, uc1, settings)) == {"DQ-METADATA-CONTRADICTION"}
    r321 = rec("2011-01-01", "2014-12-31", declared_metadata={"has_missing_values": "no"},
               documentation_excerpts=["Data set has no missing values.", "In these cases consumption were considered zero."])
    assert risk_rules.rule_metadata_contradiction(r321, c, uc1, settings) == []
    r360 = rec("2004-03-10", "2005-04-04", declared_metadata={"has_missing_values": "no"},
               quality_notes=["Missing values are tagged with -200 value."])
    assert codes(risk_rules.rule_metadata_contradiction(r360, c, uc1, settings)) == {"DQ-METADATA-CONTRADICTION"}
    honest = rec("2006-12-16", "2010-11-26", declared_metadata={"has_missing_values": "yes"},
                 documentation_excerpts=["missing values present"])
    assert risk_rules.rule_metadata_contradiction(honest, c, uc1, settings) == []


def test_g4_evaluate_has_no_skipped_rules(uc1, settings):
    _, warnings = risk_rules.evaluate(rec("2004-03-10", "2005-04-04", "hourly"), {"need_ids": ["N1"], "target_windows": ["prototype"]}, uc1, settings)
    assert warnings == []


# -- G5: verdict calibration written into the Risk Assessor prompt -----------------------
def test_g5_calibration_rules_written():
    prompt = (PROMPTS_DIR / "risk_assessor.md").read_text()
    assert "LEARNER TODO (G5)" not in prompt, "replace the G5 comment with your calibration rules"
    m = re.search(r"(?ims)^#+ .*calibration.*?$(.*?)(?=^#+ |\Z)", prompt)
    assert m, "add a heading containing the word 'calibration'"
    rules = [ln for ln in m.group(1).splitlines() if re.match(r"\s*(\d+\.|[-*])\s+\S", ln)]
    assert len(rules) >= 6, f"write at least 6 calibration rules (found {len(rules)})"


# -- G6: allowlist for the supplementary URLs ---------------------------------------------
@pytest.mark.parametrize("host", ["ec.europa.eu"])
def test_g6_supplementary_hosts_allowlisted(host):
    assert host_allowed(host, load_allowlist()), f"add {host} to config/allowlist.json and justify it in outputs/artifacts/decisions.md"


def test_g6_allowlist_not_wildcarded():
    domains = load_allowlist()
    assert all("*" not in d and d.count(".") >= 1 for d in domains)
    assert not any(d in ("com", "org", "eu", "europa.eu", "github.io") for d in domains), "too broad"
