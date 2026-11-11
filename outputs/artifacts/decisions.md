# Decisions log

## Source suggestions (Step 2b)
One row per suggestion you accepted, rejected or revised, with your reason. Use the page's own wording for the reason.

| Suggestion (publisher, URL) | Need, window | Decision | Reason |
|---|---|---|---|
| EEA AirBase v8 — https://www.eea.europa.eu/data-and-maps/data/airbase-the-european-air-quality-database-8 | N1, prototype | reject | not needed, UCI link already covers N1 |
| EEA Air Quality Download Service — https://discomap.eea.europa.eu/map/fme/AirQualityExport.htm | N1, prototype | reject | it's an interface not a dataset |
| EEA Health Risk Assessments — https://www.eea.europa.eu/en/data-and-maps/data/health-risk-assessments-of-air-pollution | N6, prototype + production | reject | Eurostat link already covers N6 |

### Gate decisions (outputs/UC1/gate_decisions.json)
Reasons dictated by the learner verbatim; written to file by Claude on 2026-11-11.

| URL | Decision | Reason |
|-----|----------|--------|
| https://archive.ics.uci.edu/dataset/360/air+quality | accept | The UCI dataset is the prescribed public hourly air-quality source for the prototype window. The smoke test returned 200 OK and the host is allowlisted. |
| https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sdg_11_52?format=JSON&lang=EN&geo=IT | accept | It's the prescribed annual PM2.5-deaths source for N6. The host is refused until you add it via G6, but you accept the link now so the pipeline can record the refusal as a finding. |
| https://catalog.data.gov/dataset/open-air-chicago-hour-aggregations | accept | Accepting it deliberately. The host (catalog.data.gov) is blocked and must never be added to the allowlist. Accepting it here lets the pipeline record the refusal as a guardrail finding — that's the point of the exercise. |

Inspected through the workflow (at least one accepted extra source):

## G1 and G3: one edge case in each function
- **G1, `extract_licence`**: The Kaggle edge case: Kaggle JSON-LD includes a `license` field with `{"name": "Unknown"}`. The code detects a dict licence in JSON-LD and returns `found_in="json-ld"` even though the name is unrecognized — so the licence field is not null but `name` is None, correctly signalling that JSON-LD was found but the licence is not known. Without this, the code would fall through to HTML text search and potentially return a false positive.
- **G3, `jsonstat_summary`**: The NON_ISO_GEO_CODES edge case: Eurostat uses `EL` for Greece and `UK` for the United Kingdom — both match the `[A-Z]{2}` regex but are not ISO 3166-1 alpha-2 codes. The code adds an explicit set `{"UK", "EL", "XK"}` to catch them before the regex check, so the summary correctly warns `NON_ISO_GEO_CODES` rather than treating them as valid ISO codes.

## G4–G5: feasible for one need or window, not another
- **Source and rule:** `link.europa_sdg_11_52_099aa6` (Eurostat SDG 11.52). Rule: `rule_temporal_coverage`.
- **Feasible for (N6, prototype window 2004–2005):** The series starts 2005 and covers the prototype window. `rule_temporal_coverage` raises no out-of-window flag for this window.
- **Not feasible for (N6, production window 2024–2025):** The series ends 2023, giving zero overlap — `COV-OUT-OF-WINDOW` fires on the production window. Because the prototype window IS served, the G5 rule "out of window with no other window served" does not trigger `not_feasible`; instead `COV-PARTIAL-WINDOW` fires and the verdict is `feasible_with_conditions`.
- **Reason for each red flag dismissed:** No flags were dismissed for this source.

## G6: Allowlist changes
Exact hosts only. For each host: what it provides and why a broader domain is not needed.

| Host added | Needed for (source, page) | Why nothing broader | Date |
|---|---|---|---|
| `ec.europa.eu` | Eurostat SDG 11.52 API — N6, prototype + production | ec.europa.eu is a reasonable host to add. This is the official EU statistical dissemination server, narrower than the full europa.eu domain, and the Eurostat SDG 11.52 indicator is exactly what N6 needs (annual PM2.5-attributable deaths for Italy). No broader domain is needed. | 2026-11-11 |

Hosts you chose **not** to add, and why:
| `catalog.data.gov` | Chicago Open Air hourly aggregations (N1, prototype) | DOMAIN_NOT_ALLOWLISTED — guardrail finding. Host must never be added: data is from a US city (Chicago), not relevant to the Italian UC1 scope. Refusal recorded as designed. |

## G5: Verdict calibration
- **What was changed:** Added a `## Verdict calibration` section to `discovery_agent/prompts/risk_assessor.md` with 10 ordered rules (stop at the first that matches). Key design decisions: (1) `ACC-UNREACHABLE` is always `not_feasible` — no workaround exists within the project. (2) `COV-OUT-OF-WINDOW` on all windows is `not_feasible` only if no window is served at all. (3) `LIC-UNKNOWN` on a non-internal source is `feasible_with_conditions` not `not_feasible` — the licence can still be read at source. (4) `LIC-NONCOMMERCIAL` on a must/should need is `not_feasible` unless a CC-BY alternative exists. (5) `FRS-STALE` alone, with no coverage flag, on a prototype or context source is `feasible_with_conditions` — historical research datasets are intentionally older.
- **Verdicts that changed after re-running `--from-stage assess`:** The Eurostat source (`link.europa_sdg_11_52_099aa6`) moved from an unclear draft verdict to `feasible_with_conditions`, driven by LIC-UNKNOWN (rule 4) — the licence was not established by the profiler and must be confirmed at source before use.

## G7: One agent failure, fixed at its cause
- **Symptom**: The Eurostat profiler (`profiler__link.europa_sdg_11_52_099aa6`) called `summarize_jsonstat` and got `NOT_IMPLEMENTED`. As a result, the dimension categories were not decoded, year coverage was unknown, and the quality note read "summarize_jsonstat returned NOT_IMPLEMENTED, so the dimension-level category decoding was not done."
- **Evidence**: `outputs/UC1/transcripts/profiler__link.europa_sdg_11_52_099aa6.json`, turn 3: `[tool ERR]: {"error": "NOT_IMPLEMENTED", "message": "jsonstat_summary is a learner TODO (G3)…"}`. Confirmed in `outputs/UC1/records/link.europa_sdg_11_52_099aa6.json` pre-fix quality_notes.
- **Root cause**: Missing tool implementation — `jsonstat_summary` in `discovery_agent/tools/formats.py` raised `NotImplementedTool`. The profiler had no fallback for JSON-stat decoding and could not extract dimension labels, time values, or cell counts.
- **Fix**: Implemented `jsonstat_summary` in `discovery_agent/tools/formats.py` (G3). Parses `dataset["id"]`/`dataset["dimension"]` to extract ordered codes and labels, counts non-null values in list or sparse-dict `value` field, counts status codes, and warns for `MISSING_CELLS` and `NON_ISO_GEO_CODES`.
- **Re-run**: `python -m discovery_agent run --use-case UC1 --from-stage profile --stop-after profile --only link.europa_sdg_11_52_099aa6 --links-file outputs/UC1/links.json --no-input`
- **Before / after**:
  - Before: year coverage "not established"; probe dates misread as data dates; dimensions not decoded; `tool_errors: 1`
  - After: "36 cells (18 years × 2 units), covering 2005 to 2023, 2006 absent"; `tool_errors: 0`
- **Decision this failure could affect**: N6 verdict. After fix, it is clear the series ends in 2023 — the production window (2024-2025) has **no coverage** and the prototype window gets only 2005. The N6 coverage gap is now precisely known, not unknown.
- **Related source or test checked**: `python -m pytest tests/test_learner_gaps.py -k g3 -q` → 2 passed.

## Other decisions
