"""Provided functionality. These should pass on a fresh checkout, with no network and no LLM."""
import json
import re

import pytest

from discovery_agent import risk_rules
from discovery_agent.config import load_allowlist, use_case_files
from discovery_agent.tools import ToolContext, execute
from discovery_agent.tools.http_client import HttpClient, HttpRefused, _check_url, host_allowed
from discovery_agent.tools.probe import detect_json_kind
from discovery_agent.tools.summarize import csv_summary, date_range, html_summary
from discovery_agent.trace import Trace
from discovery_agent.validation import validate_use_case


# -- guardrails ----------------------------------------------------------------
def test_allowlist_matches_host_and_subdomains_only():
    assert host_allowed("archive.ics.uci.edu", ["archive.ics.uci.edu"])
    assert host_allowed("api.open-meteo.com", ["open-meteo.com"])
    assert not host_allowed("evilarchive.ics.uci.edu.attacker.io", ["archive.ics.uci.edu"])
    assert not host_allowed("notworldbank.org", ["worldbank.org"])


@pytest.mark.parametrize("url,code", [
    ("http://archive.ics.uci.edu/api", "SCHEME_NOT_ALLOWED"),
    ("https://127.0.0.1/admin", "IP_LITERAL_REFUSED"),
    ("https://example.com/data.csv", "DOMAIN_NOT_ALLOWLISTED"),
])
def test_check_url_refusals(url, code):
    with pytest.raises(HttpRefused) as exc:
        _check_url(url, ["archive.ics.uci.edu"])
    assert exc.value.code == code


def test_http_client_refuses_without_network(settings, tmp_path):
    trace = Trace(tmp_path / "t.jsonl")
    client = HttpClient(settings, ["archive.ics.uci.edu"], trace)
    with pytest.raises(HttpRefused):
        client.get("https://not-allowed.example/x")
    assert trace.totals["http_refused"] == 1
    events = [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert events[0]["refused"] == "DOMAIN_NOT_ALLOWLISTED"


def test_hard_byte_cap_cannot_be_exceeded(settings, tmp_path):
    client = HttpClient(settings, load_allowlist(), Trace(None))
    assert client.hard_cap <= 5_000_000


# -- summarisers ---------------------------------------------------------------
def test_date_range_finds_values_keys_and_years():
    obj = {"events": [{"date": "2019-01-01"}, {"date": "2028-12-26"}], "rates": {"2010-01-04": {"EUR": 1.1}},
           "rows": [{"date": "2012"}, {"date": "2014"}]}
    r = date_range(obj)
    assert r["min_date"] == "2010-01-04" and r["max_date"] == "2028-12-26"
    assert r["min_year"] == 2012 and r["max_year"] == 2014


def test_csv_summary_semicolon():
    s = csv_summary("Date;Time;Global_active_power\n16/12/2006;17:24:00;4.216\n16/12/2006;17:25:00;?\n")
    assert s["delimiter"] == ";" and s["columns"] == ["Date", "Time", "Global_active_power"]


def test_html_summary_licence_snippets():
    s = html_summary("<html><title>T</title><body><p>This dataset is licensed under a Creative Commons "
                     "Attribution 4.0 International (CC BY 4.0) license.</p></body></html>")
    assert s["title"] == "T" and any("CC BY 4.0" in x for x in s["licence_snippets"])


def test_detect_json_kind(fixture_json):
    assert detect_json_kind(fixture_json("opsd_time_series_2019-06-05_datapackage_trimmed.json")) == "frictionless_datapackage"
    assert detect_json_kind(fixture_json("eurostat_isoc_ec_ibuy_2009_2011.json")) == "json_stat"
    assert detect_json_kind({"a": 1}) == "json"


# -- internal catalog tools ------------------------------------------------------
def _ctx(uc, settings):
    return ToolContext(use_case=uc, settings=settings, http=None, trace=Trace(None), agent="test")


def test_internal_search_and_backlinks(uc1, settings):
    ok, res = execute("search_internal_catalog", {"query": "hourly air pollution station readings"}, _ctx(uc1, settings))
    assert ok and res["hits"][0]["id"] == "airq.station_readings"
    ok, entry = execute("get_catalog_entry", {"entry_id": "traffic.hourly_counts"}, _ctx(uc1, settings))
    assert ok and "counter_replacement_2024" in entry["wiki_backlinks"]
    ok, err = execute("get_catalog_entry", {"entry_id": "nope.table"}, _ctx(uc1, settings))
    assert not ok and err["error"] == "TOOL_ERROR"


def test_wiki_page_read(uc2, settings):
    ok, page = execute("read_wiki_page", {"page_id": "till_migration_2024"}, _ctx(uc2, settings))
    assert ok and "2024" in page["body"]


def test_vendor_feed_is_never_called(uc1, settings):
    ok, res = execute("call_public_api", {"source_id": "vendor.atmosdata_pro"}, _ctx(uc1, settings))
    assert ok and res["called"] is False and "expired" in res["reason"]


def test_uci_metadata_summary_reports_blank_variables(fixture_json):
    from discovery_agent.tools.uci import uci_metadata_summary
    res = uci_metadata_summary(fixture_json("uci_502_api.json")["data"])
    assert res["variables_with_blank_names"] > 0 and res["variables"] == []
    assert res["licence_in_api"] is None and "Online Retail" in res["name"]


# -- dataset links ------------------------------------------------------------------
def test_canonical_ref_and_source_id():
    from discovery_agent.tools.links import canonical_ref, link_source_id
    assert canonical_ref("https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014") == "uci:321"
    assert canonical_ref("https://archive.ics.uci.edu/dataset/321") == "uci:321"
    assert link_source_id("https://archive.ics.uci.edu/dataset/502/online+retail+ii") == "link.uci_502"
    assert canonical_ref("https://Example.org/a/b/?y=2&x=1") == canonical_ref("https://example.org/a/b?x=1&y=2")
    assert canonical_ref("https://github.com/o/r/blob/main/d.csv") == "raw.githubusercontent.com/o/r/main/d.csv"
    sid = link_source_id("https://www.kaggle.com/datasets/carrie1/ecommerce-data")
    assert re.fullmatch(r"link\.[a-z0-9_]+", sid) and sid.startswith("link.kaggle_")


def test_sample_profile_csv(fixture_text):
    from discovery_agent.tools.links import sample_profile
    raw = fixture_text("seattle_weather_head.csv").encode()
    out = sample_profile(raw, truncated=False, content_length=None)
    cols = {c["name"]: c for c in out["profile"]}
    assert out["sample_is_whole_file"] and out["rows_in_sample"] == 40
    assert cols["date"]["type"] == "date/time" and cols["date"]["sample_range"]["min"].startswith("2012-01-01")
    assert cols["temp_min"]["negative_count"] > 0 and "rain" in cols["weather"]["values_in_sample"]


def test_sample_profile_sentinels_pii_and_truncation():
    from discovery_agent.tools.links import sample_profile
    raw = b"Date;Power;email\n16/12/2006;4.2;a@b.com\n17/12/2006;?;c@d.com\n18/12/2006;3.1;e@f.com\n19/12/2006;?;g@h.co"
    out = sample_profile(raw, truncated=True, content_length="100000")
    cols = {c["name"]: c for c in out["profile"]}
    assert out["delimiter"] == ";" and out["caution"] and out["rows_in_sample"] == 3
    assert cols["Power"]["sentinel_counts"] == {"?": 1}
    assert cols["email"]["pii_suspected"] and "values_in_sample" not in cols["email"] and "examples" not in cols["email"]
    assert sample_profile(b"PK\x03\x04rest", True, None)["sampleable"] is False


def test_jsonld_from_real_portal_pages(fixture_text):
    from discovery_agent.tools.licence import jsonld_datasets, summarise_jsonld_dataset
    kaggle = [summarise_jsonld_dataset(d) for d in jsonld_datasets(fixture_text("kaggle_ecommerce_landing_page.html"))]
    assert kaggle and kaggle[0]["name"] == "E-Commerce Data"
    assert any(x.get("requiresSubscription") for x in kaggle[0]["distribution"])
    zenodo = jsonld_datasets(fixture_text("zenodo_record_landing_page.html"))
    assert zenodo and "creativecommons.org/licenses/by/4.0" in str(zenodo[0]["license"])


class _Res:
    def __init__(self, url, body, status=200, ctype="text/html", final=None):
        self.url, self.final_url, self.status, self.body = url, final or url, status, body.encode() if isinstance(body, str) else body
        self.headers, self.truncated, self.from_cache = {"content-type": ctype}, False, False
        self.error = None if status == 200 else f"HTTP {status}"

    @property
    def content_type(self):
        return self.headers["content-type"]

    def text(self):
        return self.body.decode()


class _FakeHttp:
    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def get(self, url, max_bytes=None, agent=""):
        self.seen.append(url)
        return self.routes[url]

    def get_json(self, url, max_bytes=None, agent=""):
        return json.loads(self.routes[url].text()), self.routes[url]


def _link_ctx(uc, settings, routes):
    return ToolContext(use_case=uc, settings=settings, http=_FakeHttp(routes), trace=Trace(None))


def test_inspect_landing_page_with_jsonld(uc2, settings, fixture_text):
    url = "https://www.kaggle.com/datasets/carrie1/ecommerce-data"
    ctx = _link_ctx(uc2, settings, {url: _Res(url, fixture_text("kaggle_ecommerce_landing_page.html"))})
    ok, out = execute("inspect_dataset_link", {"url": url}, ctx)
    assert ok and out["link_type"] == "landing_page" and out["downloads_require_login"] is True
    assert out["jsonld_datasets"][0]["name"] == "E-Commerce Data" and "licence" in out


def test_inspect_login_wall_and_datapackage_and_github(uc1, settings, fixture_json, fixture_text):
    wall = "https://portal.example.org/data/x"
    dp = "https://data.example.org/pkg/datapackage.json"
    gh = "https://github.com/o/r/blob/main/w.csv"
    raw = "https://raw.githubusercontent.com/o/r/main/w.csv"
    ctx = _link_ctx(uc1, settings, {
        wall: _Res(wall, "", status=403),
        dp: _Res(dp, json.dumps(fixture_json("opsd_time_series_2019-06-05_datapackage_trimmed.json")), ctype="application/json"),
        raw: _Res(raw, fixture_text("seattle_weather_head.csv"), ctype="text/plain")})
    assert execute("inspect_dataset_link", {"url": wall}, ctx)[1]["link_type"] == "login_wall"
    assert execute("inspect_dataset_link", {"url": dp}, ctx)[1]["link_type"] == "frictionless_datapackage"
    out = execute("inspect_dataset_link", {"url": gh}, ctx)[1]
    assert out["link_type"] == "data_file" and ctx.http.seen[-1] == raw and out["rows_in_sample"] == 40


# -- provided rules ------------------------------------------------------------
def _record(**over):
    base = {"source_id": "x", "kind": "internal", "status": "active", "licence": {"name": "internal"},
            "access": {"method": "warehouse_sql", "auth_required": False, "reachable": True},
            "ownership": {"owner": "Team"}, "schema": {"fields": []}, "temporal": {"start": None, "end": None, "grain": "static"},
            "declared_metadata": {}, "documentation_excerpts": [], "quality_notes": []}
    base.update(over)
    return base


def test_provided_rules(uc1, settings):
    cand = {"need_ids": ["N1"], "target_windows": ["production"]}

    def run(rec):
        return {f["code"] for f in sum((r(rec, cand, uc1, settings) for r in risk_rules.RULES[:7]), [])}

    assert run(_record(ownership={"owner": None})) == {"GOV-OWNER-UNKNOWN"}
    assert run(_record(status="archived")) == {"GOV-DEPRECATED"}
    assert "GOV-PII" in run(_record(schema={"fields": [{"name": "email", "pii": True}]}))
    assert run(_record(kind="uci", licence={"name": None, "evidence": None})) == {"LIC-UNKNOWN"}
    assert run(_record(kind="uci", licence={"name": "CC BY 4.0"})) == {"LIC-ATTRIBUTION"}
    assert run(_record(kind="uci", licence={"name": "CC BY-NC 4.0"})) == {"LIC-NONCOMMERCIAL"}
    assert "LIC-AGREEMENT-NOT-ACTIVE" in run(_record(kind="vendor_feed", licence={"name": None, "agreement_status": "expired"}))
    assert "OPS-LARGE-PAYLOAD" in run(_record(access={"method": "file_download", "approx_size_bytes": 230_000_000}))
    assert "ACC-MANUAL" in run(_record(access={"method": "manual_export"}))


def test_evaluate_skips_unimplemented_rules_with_warning(uc1, settings):
    flags, warnings = risk_rules.evaluate(_record(), {"need_ids": ["N1"], "target_windows": ["production"]}, uc1, settings)
    assert isinstance(flags, list) and isinstance(warnings, list)


# -- use-case contract ------------------------------------------------------------
def test_shipped_use_cases_validate():
    assert set(use_case_files()) >= {"UC1", "UC2"}
    assert validate_use_case("UC1") == []
    assert validate_use_case("UC2") == []


def test_template_is_ignored():
    assert all(not p.name.startswith("_") for p in use_case_files().values())
