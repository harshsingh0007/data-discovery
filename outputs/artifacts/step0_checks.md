# Step 0 checks — UC1 (run 2026-11-11)

## Gateway variables
All three set: ANTHROPIC_BASE_URL ✅  ANTHROPIC_AUTH_TOKEN ✅  ANTHROPIC_MODEL ✅
Model in use: **claude-haiku-5-5** (from ANTHROPIC_MODEL; never print the token)

## Test results

| File | Result | Notes |
|------|--------|-------|
| tests/test_tools_offline.py | ✅ passed | |
| tests/test_agent_loop.py | ✅ passed | |
| tests/test_learner_gaps.py | ❌ 20 failed | Expected — gaps G1, G3, G4, G5, G6 not yet implemented |

Failing gap tests (do not implement here — these are your tasks):
- **G1** (extract_licence): test_g1_uci_page_link_or_text, test_g1_zenodo_jsonld_url, test_g1_kaggle_unknown_is_not_a_licence, test_g1_jsonld_variants (×3), test_g1_no_commercial_flag
- **G3** (JSON-stat profiler): test_g3_* (JSON-stat tool not yet implemented)
- **G4** (risk rules): test_g4_temporal_coverage, test_g4_grain, test_g4_metadata_contradiction
- **G5** (verdict): test_g5_*
- **G6** (allowlist enforcement): test_g6_*

## Tool smoke tests (no LLM calls)

| Tool | Input | Result |
|------|-------|--------|
| search_internal_catalog | "air quality pollution hourly measurements" | ✅ JSON — 2 catalog hits (airq.station_readings, traffic.hourly_counts), 1 wiki hit |
| inspect_dataset_link | https://archive.ics.uci.edu/dataset/360/air+quality | ✅ JSON — UCI metadata retrieved; licence field null (G1 TODO) |
| list_external_register | {} | ✅ JSON — 4 sources returned (1 expired: vendor.atmosdata_pro) |

A `DOMAIN_NOT_ALLOWLISTED` on a refused host is the guardrail working, not a bug.
